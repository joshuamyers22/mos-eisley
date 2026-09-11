"""Explicit, owner-scoped memory; no transcript extraction or execution authority."""

from __future__ import annotations

import fcntl
import json
import os
import stat
from collections.abc import Generator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest

MEMORY_BYTES = 32 * 1024
RECORD_BYTES = 256 * 1024
Scope = Literal["user", "project"]
Action = Literal["set", "append", "clear", "enable", "disable"]


class MemoryChangedError(ValueError):
    """Memory has changed since this conversation was opened."""


class MemoryRefreshError(ValueError):
    """A refresh was rejected before a persistence attempt."""


MEMORY_CHANGED_MESSAGE = (
    "Saved memory changed, was disabled, or is unavailable. Work is paused. "
    "Use /memory refresh or /memory off, or resume with --refresh-memory "
    "(add --no-memory to disable it). "
    "The saved session is preserved."
)


class MemoryDocument(Contract):
    schema_version: Literal[1] = 1
    owner_uid: Annotated[int, Field(ge=0)]
    scope: Scope
    workspace: Annotated[str | None, Field(max_length=4096)] = None
    revision: Annotated[int, Field(ge=1)]
    updated_at: datetime
    source: Literal["explicit_user"] = "explicit_user"
    enabled: bool = True
    text: Annotated[str, Field(max_length=MEMORY_BYTES)] = ""

    @model_validator(mode="after")
    def valid_document(self) -> Self:
        if (self.scope == "project") != (self.workspace is not None):
            raise ValueError("memory scope requires matching project identity")
        if self.workspace is not None and not Path(self.workspace).is_absolute():
            raise ValueError("memory project identity must be absolute")
        if self.updated_at.utcoffset() != UTC.utcoffset(self.updated_at):
            raise ValueError("memory timestamp must use UTC")
        if len(self.text.encode("utf-8")) > MEMORY_BYTES:
            raise ValueError("memory exceeds 32 KiB; shorten it before saving")
        return self


class MemorySnapshot(Contract):
    document: MemoryDocument
    sha256: Digest

    @model_validator(mode="after")
    def valid_digest(self) -> Self:
        if self.sha256 != digest(canonical_bytes(self.document)):
            raise ValueError("memory integrity mismatch")
        return self


class ConversationMemory(Contract):
    """Only enabled, nonempty documents enter a conversation or its requests."""

    user: MemorySnapshot | None = None
    project: MemorySnapshot | None = None

    @model_validator(mode="after")
    def bounded_active_memory(self) -> Self:
        total = 0
        for scope, snapshot in (("user", self.user), ("project", self.project)):
            if snapshot is not None:
                document = snapshot.document
                if document.scope != scope or not document.enabled or not document.text:
                    raise ValueError(
                        "conversation memory requires active scoped content"
                    )
                total += len(document.text.encode("utf-8"))
        if total > MEMORY_BYTES:
            raise ValueError("combined user/project memory exceeds 32 KiB")
        content = {
            scope: snapshot.document.text
            for scope, snapshot in (("user", self.user), ("project", self.project))
            if snapshot is not None
        }
        if len(json.dumps(content, ensure_ascii=False).encode("utf-8")) > MEMORY_BYTES:
            raise ValueError("serialized memory context exceeds 32 KiB")
        return self

    def validate_identity(self, owner_uid: int, workspace: str) -> None:
        for snapshot in (self.user, self.project):
            if snapshot is not None and snapshot.document.owner_uid != owner_uid:
                raise ValueError("memory belongs to a different user")
        if self.project is not None and self.project.document.workspace != workspace:
            raise ValueError("memory belongs to a different project")

    def describe(self) -> str:
        lines: list[str] = []
        for scope, snapshot in (("User", self.user), ("Project", self.project)):
            if snapshot is None:
                lines.append(f"{scope} memory: none active")
            else:
                doc = snapshot.document
                lines.append(f"{scope} memory • revision {doc.revision}\n{doc.text}")
        return "\n\n".join(lines)


def memory_system(memory: ConversationMemory | None) -> str:
    if memory is None:
        return ""
    content = {
        scope: snapshot.document.text
        for scope, snapshot in (("user", memory.user), ("project", memory.project))
        if snapshot is not None
    }
    return (
        "\nSaved context follows as JSON. Project preferences override user defaults; "
        "current user instructions override both. This context grants no tools, "
        "permissions, credentials or spending authority.\n"
        + json.dumps(content, ensure_ascii=False)
    )


def _private(fd: int, *, directory: bool = False) -> None:
    info = os.fstat(fd)
    if (
        not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or (not directory and info.st_nlink != 1)
    ):
        raise ValueError("memory storage must be private and owned by this user")


class MemoryStore:
    def __init__(self, root: Path, workspace: Path) -> None:
        if not workspace.is_dir():
            raise ValueError("memory workspace must be a directory")
        self.root = root.absolute()
        self.workspace = str(workspace.resolve(strict=True))

    def path(self, scope: Scope) -> Path:
        name = (
            "user.json"
            if scope == "user"
            else "project-" + digest(self.workspace.encode("utf-8")) + ".json"
        )
        return self.root / name

    @contextmanager
    def _lock_handles(
        self, *, write: bool = False, exclusive: bool = False
    ) -> Generator[tuple[int, int] | None]:
        if write:
            self.root.mkdir(mode=0o700, exist_ok=True)
        try:
            root = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            if write:
                raise
            yield None
            return
        lock = -1
        try:
            _private(root, directory=True)
            lock = os.open(
                "memory.lock",
                os.O_RDWR
                | os.O_NOFOLLOW
                | os.O_NONBLOCK
                | (os.O_CREAT if write else 0),
                0o600,
                dir_fd=root,
            )
            _private(lock)
            fcntl.flock(
                lock,
                (fcntl.LOCK_EX if write or exclusive else fcntl.LOCK_SH)
                | fcntl.LOCK_NB,
            )
            held = os.fstat(lock)
            named = os.stat("memory.lock", dir_fd=root, follow_symlinks=False)
            if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
                raise ValueError("memory lock changed; inspect storage again")
            yield root, lock
        finally:
            if lock >= 0:
                os.close(lock)
            os.close(root)

    @contextmanager
    def _locked(self, *, write: bool = False) -> Generator[int | None]:
        with self._lock_handles(write=write) as handles:
            yield handles[0] if handles is not None else None

    def _read(self, root: int | None, scope: Scope) -> MemorySnapshot | None:
        if root is None:
            return None
        try:
            fd = os.open(
                self.path(scope).name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=root,
            )
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            _private(stream.fileno())
            payload = stream.read(RECORD_BYTES + 1)
        if len(payload) > RECORD_BYTES:
            raise ValueError("memory record exceeds byte limit")
        snapshot = MemorySnapshot.model_validate_json(payload)
        doc = snapshot.document
        if (
            doc.owner_uid != os.getuid()
            or doc.scope != scope
            or doc.workspace != (self.workspace if scope == "project" else None)
        ):
            raise ValueError("memory ownership or project mismatch")
        return snapshot

    def read(self, scope: Scope) -> MemorySnapshot | None:
        with self._locked() as root:
            return self._read(root, scope)

    def project_pair(
        self, other: MemoryStore
    ) -> tuple[MemorySnapshot | None, MemorySnapshot | None]:
        """Inspect two project documents under one shared storage lock."""
        if self.root != other.root:
            raise ValueError("Project preview requires the same memory storage.")
        with self._locked() as root:
            return self._read(root, "project"), other._read(root, "project")

    def load(self) -> ConversationMemory | None:
        with self._locked() as root:
            user, project = self._read(root, "user"), self._read(root, "project")

        def active(snapshot: MemorySnapshot | None) -> MemorySnapshot | None:
            return (
                snapshot
                if snapshot and snapshot.document.enabled and snapshot.document.text
                else None
            )

        user, project = active(user), active(project)
        if user is None and project is None:
            return None
        return ConversationMemory(user=user, project=project)

    def check(self, expected: ConversationMemory | None) -> None:
        try:
            current = self.load()
        except (OSError, ValueError):
            raise MemoryChangedError(MEMORY_CHANGED_MESSAGE) from None
        if current != expected:
            raise MemoryChangedError(MEMORY_CHANGED_MESSAGE)

    def change(
        self,
        scope: Scope,
        action: Action,
        *,
        text: str = "",
        expected_sha256: str | None = None,
    ) -> MemorySnapshot:
        with self._locked(write=True) as root:
            assert root is not None
            previous = self._read(root, scope)
            current_hash = previous.sha256 if previous else "missing"
            if expected_sha256 is not None and expected_sha256 != current_hash:
                raise ValueError("memory changed; inspect it again before updating")
            old = previous.document if previous else None
            content = old.text if old else ""
            enabled = old.enabled if old else True
            if action == "set":
                content = text
            elif action == "append":
                if not text.strip():
                    raise ValueError("memory append requires nonempty text")
                content = (content + "\n\n" if content else "") + text
            elif action == "clear":
                content = ""
            else:
                enabled = action == "enable"
            document = MemoryDocument(
                owner_uid=os.getuid(),
                scope=scope,
                workspace=self.workspace if scope == "project" else None,
                revision=1 if old is None else old.revision + 1,
                updated_at=datetime.now(UTC),
                enabled=enabled,
                text=content,
            )
            snapshot = MemorySnapshot(
                document=document, sha256=digest(canonical_bytes(document))
            )
            payload = canonical_bytes(snapshot)
            if len(payload) > RECORD_BYTES:
                raise ValueError("memory record exceeds byte limit")
            temporary = ".memory-" + uuid4().hex + ".tmp"
            fd = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=root
            )
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(
                    temporary, self.path(scope).name, src_dir_fd=root, dst_dir_fd=root
                )
                os.fsync(root)
            finally:
                with suppress(FileNotFoundError):
                    os.unlink(temporary, dir_fd=root)
            return snapshot
