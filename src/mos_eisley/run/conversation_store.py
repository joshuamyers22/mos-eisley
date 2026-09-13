"""Private, locked, atomically replaced local conversation snapshots."""

from __future__ import annotations

import fcntl
import os
import re
import stat
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from types import TracebackType
from typing import Annotated, Self
from uuid import uuid4

from pydantic import Field, TypeAdapter

from mos_eisley.conversation import ConversationState, SessionID
from mos_eisley.conversation_limits import (
    MAX_CATALOG_SCAN_BYTES,
    MAX_SNAPSHOT_BYTES,
)
from mos_eisley.conversation_name import SessionName
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest

MAX_BYTES = MAX_SNAPSHOT_BYTES
MAX_DIRECTORY_ENTRIES = 4096
MAX_CATALOG_BYTES = 8_000_000
MAX_SESSIONS = 256


class ConversationSnapshot(Contract):
    state: ConversationState
    sha256: Digest


class ConversationSummary(Contract):
    session_id: SessionID
    session_name: SessionName | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    snapshot_sha256: Digest
    revision: Annotated[int, Field(ge=0)]
    modified_ns: Annotated[int, Field(ge=0)]
    messages: Annotated[int, Field(ge=0, le=16)]
    completed: Annotated[int, Field(ge=0, le=16)]
    pending: Annotated[int, Field(ge=0, le=16)]
    active: bool
    snapshot_bytes: Annotated[int, Field(ge=0, le=MAX_SNAPSHOT_BYTES)]
    snapshot_max_bytes: Annotated[int, Field(ge=1, le=MAX_SNAPSHOT_BYTES)]


class ConversationDeletion(Contract):
    session_id: SessionID
    snapshot_sha256: Digest
    removed_temporary_files: Annotated[int, Field(ge=0)]


def validate_private_storage(fd: int, *, directory: bool = False) -> None:
    info = os.fstat(fd)
    correct_type = (
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    )
    if (
        not correct_type
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or (not directory and info.st_nlink != 1)
    ):
        raise ValueError("conversation storage must be private and owned by this user")


def _names(root: int) -> tuple[str, ...]:
    names: list[str] = []
    with os.scandir(root) as entries:
        for entry in entries:
            if len(names) == MAX_DIRECTORY_ENTRIES:
                raise ValueError("conversation directory exceeds entry limit")
            names.append(entry.name)
    return tuple(names)


def _snapshot(
    root: int, session_id: str, *, byte_limit: int = MAX_BYTES
) -> tuple[ConversationSnapshot, int, int]:
    validate_private_storage(root, directory=True)
    fd = os.open(
        f"{session_id}.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root
    )
    with os.fdopen(fd, "rb") as stream:
        validate_private_storage(stream.fileno())
        modified_ns = os.fstat(stream.fileno()).st_mtime_ns
        payload = stream.read(byte_limit + 1)
    if len(payload) > byte_limit:
        if byte_limit < MAX_BYTES:
            raise ValueError(
                "conversation catalog scan exceeds byte limit; "
                "use --catalog-max-bytes BYTES to change the scan budget"
            )
        raise ValueError("conversation snapshot exceeds byte limit")
    snapshot = ConversationSnapshot.model_validate_json(payload)
    state = snapshot.state
    if len(payload) > state.snapshot_byte_limit:
        raise ValueError("conversation snapshot exceeds its saved byte limit")
    if (
        state.owner_uid != os.getuid()
        or state.session_id != session_id
        or snapshot.sha256 != digest(canonical_bytes(state))
    ):
        raise ValueError("conversation ownership or integrity mismatch")
    return snapshot, modified_ns, len(payload)


def list_conversations(
    root: Path, workspace: Path, *, max_bytes: int | None = None
) -> tuple[ConversationSummary, ...]:
    """Read bounded snapshots; return only metadata for this user's workspace.

    Listing does not write directories, lock files, snapshots or recency metadata.
    A bad candidate aborts the catalog rather than silently selecting an older one.
    """
    maximum = MAX_CATALOG_BYTES if max_bytes is None else max_bytes
    if type(maximum) is not int or not 1 <= maximum <= MAX_CATALOG_SCAN_BYTES:
        raise ValueError("invalid conversation catalog byte limit")
    if workspace.exists() and not workspace.is_dir():
        raise ValueError("conversation workspace must be a directory")
    selected_workspace = str(workspace.resolve())
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        validate_private_storage(root_fd, directory=True)
        candidates = tuple(
            name[:-5]
            for name in _names(root_fd)
            if re.fullmatch(r"[0-9a-f]{32}\.json", name)
        )
        if len(candidates) > MAX_SESSIONS:
            raise ValueError("conversation catalog exceeds session limit")
        summaries: list[ConversationSummary] = []
        total_bytes = 0
        for session_id in candidates:
            snapshot, modified_ns, size = _snapshot(
                root_fd,
                session_id,
                byte_limit=min(MAX_BYTES, maximum - total_bytes),
            )
            total_bytes += size
            state = snapshot.state
            if state.workspace != selected_workspace:
                continue
            lock = os.open(
                f"{session_id}.lock",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=root_fd,
            )
            try:
                validate_private_storage(lock)
                try:
                    fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    active = False
                except BlockingIOError:
                    active = True
            finally:
                os.close(lock)
            summaries.append(
                ConversationSummary(
                    session_id=session_id,
                    session_name=state.session_name,
                    snapshot_sha256=snapshot.sha256,
                    revision=state.revision,
                    modified_ns=modified_ns,
                    messages=len(state.entries),
                    active=active,
                    completed=sum(e.status == "completed" for e in state.entries),
                    pending=sum(e.status == "queued" for e in state.entries),
                    snapshot_bytes=size,
                    snapshot_max_bytes=state.snapshot_byte_limit,
                )
            )
        return tuple(
            sorted(
                summaries,
                key=lambda item: (item.modified_ns, item.session_id),
                reverse=True,
            )
        )
    finally:
        os.close(root_fd)


class ConversationStore:
    """A held per-session flock rejects competing writers for this entire handle."""

    def __init__(
        self,
        root: Path,
        session_id: str,
        workspace: Path,
        *,
        create: bool = True,
        require_workspace: bool = True,
        expected_root_identity: tuple[int, int] | None = None,
    ) -> None:
        if expected_root_identity is not None and (
            type(expected_root_identity) is not tuple
            or len(expected_root_identity) != 2
            or any(
                type(value) is not int or value < 0 for value in expected_root_identity
            )
        ):
            raise ValueError("invalid expected storage directory identity")
        self.session_id = TypeAdapter[str](SessionID).validate_python(session_id)
        if not workspace.is_dir() and (require_workspace or workspace.exists()):
            raise ValueError("conversation workspace must be a directory")
        self.workspace = str(workspace.resolve(strict=require_workspace))
        self._revision = -1
        self._sha256: str | None = None
        self._deleted = False
        if create and expected_root_identity is None:
            root.mkdir(mode=0o700, exist_ok=True)
        self._root = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self._lock = -1
        try:
            validate_private_storage(self._root, directory=True)
            info = os.fstat(self._root)
            if (
                expected_root_identity is not None
                and (info.st_dev, info.st_ino) != expected_root_identity
            ):
                raise ValueError("selected storage directory changed")
            self._lock = os.open(
                f"{session_id}.lock",
                os.O_RDWR
                | (os.O_CREAT if create else 0)
                | os.O_NOFOLLOW
                | os.O_NONBLOCK,
                0o600,
                dir_fd=self._root,
            )
            validate_private_storage(self._lock)
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self._lock >= 0:
            os.close(self._lock)
            self._lock = -1
        if self._root >= 0:
            os.close(self._root)
            self._root = -1

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _read(self) -> ConversationSnapshot:
        return self.inspect_json_snapshot()[0]

    def inspect_json_snapshot(
        self, *, byte_limit: int = MAX_BYTES
    ) -> tuple[ConversationSnapshot, int, int]:
        """Read JSON and its filesystem metadata while this handle holds the lock."""
        if self._deleted:
            raise ValueError("conversation has been deleted")
        if type(byte_limit) is not int or not 1 <= byte_limit <= MAX_BYTES:
            raise ValueError("invalid JSON snapshot read limit")
        snapshot, modified_ns, size = _snapshot(
            self._root, self.session_id, byte_limit=byte_limit
        )
        state = snapshot.state
        if state.workspace != self.workspace:
            raise ValueError("conversation workspace mismatch")
        return snapshot, modified_ns, size

    def load(self) -> ConversationState:
        snapshot = self._read()
        self._revision = snapshot.state.revision
        self._sha256 = snapshot.sha256
        return snapshot.state

    def save(self, state: ConversationState) -> None:
        if self._deleted:
            raise ValueError("conversation has been deleted")
        validate_private_storage(self._root, directory=True)
        state = ConversationState.model_validate_json(state.model_dump_json())
        if (
            state.owner_uid != os.getuid()
            or state.session_id != self.session_id
            or state.workspace != self.workspace
            or state.revision != self._revision + 1
        ):
            raise ValueError("invalid conversation save identity or revision")
        try:
            current = self._read()
        except FileNotFoundError:
            if self._revision != -1:
                raise ValueError("saved conversation disappeared") from None
        else:
            if current.sha256 != self._sha256:
                raise ValueError("saved conversation changed outside this handle")
        snapshot = ConversationSnapshot(
            state=state, sha256=digest(canonical_bytes(state))
        )
        payload = canonical_bytes(snapshot)
        if len(payload) > state.snapshot_byte_limit:
            raise ValueError(
                "conversation snapshot exceeds its saved byte limit; "
                "resume with --session-max-bytes BYTES to change the budget"
            )
        temporary = f".{self.session_id}.{uuid4().hex}.tmp"
        fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=self._root
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(
                temporary,
                f"{self.session_id}.json",
                src_dir_fd=self._root,
                dst_dir_fd=self._root,
            )
            os.fsync(self._root)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=self._root)
        self._revision = state.revision
        self._sha256 = snapshot.sha256

    def publish_snapshot(
        self,
        state: ConversationState,
        modified_ns: int,
        *,
        validate_source: Callable[[], None],
    ) -> bool:
        """Publish an exact imported revision under the destination session lock.

        Existing snapshots must match. As with ordinary saves, atomic replacement
        assumes cooperative writers and trusted owner-local parent directories.
        """
        if self._deleted or self._revision != -1:
            raise ValueError("snapshot import requires a fresh destination handle")
        if type(modified_ns) is not int or modified_ns < 0:
            raise ValueError("invalid imported snapshot timestamp")
        validate_private_storage(self._root, directory=True)
        state = ConversationState.model_validate_json(state.model_dump_json())
        if (
            state.owner_uid != os.getuid()
            or state.session_id != self.session_id
            or state.workspace != self.workspace
        ):
            raise ValueError("invalid imported snapshot identity")
        snapshot = ConversationSnapshot(
            state=state, sha256=digest(canonical_bytes(state))
        )
        payload = canonical_bytes(snapshot)
        if len(payload) > min(MAX_BYTES, state.snapshot_byte_limit):
            raise ValueError("exported snapshot exceeds its saved byte limit")
        try:
            current = self.inspect_json_snapshot()[0]
        except FileNotFoundError:
            pass
        else:
            if current.sha256 != snapshot.sha256:
                raise ValueError("destination contains a different session state")
            validate_source()
            os.fsync(self._root)
            return False
        temporary = f".{self.session_id}.{uuid4().hex}.tmp"
        fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=self._root
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.utime(stream.fileno(), ns=(modified_ns, modified_ns))
                os.fsync(stream.fileno())
            validate_source()
            # Recheck immediately before publication. Cooperating writers cannot
            # create this path while the destination session lock is held.
            try:
                os.stat(
                    f"{self.session_id}.json", dir_fd=self._root, follow_symlinks=False
                )
            except FileNotFoundError:
                pass
            else:
                raise ValueError("destination snapshot appeared during export")
            os.replace(
                temporary,
                f"{self.session_id}.json",
                src_dir_fd=self._root,
                dst_dir_fd=self._root,
            )
            os.fsync(self._root)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=self._root)
        self._revision = state.revision
        self._sha256 = snapshot.sha256
        return True

    def delete(self, expected_sha256: str) -> ConversationDeletion:
        expected = TypeAdapter[str](Digest).validate_python(expected_sha256)
        snapshot = self._read()
        if snapshot.sha256 != expected:
            raise ValueError("conversation changed since deletion was selected")
        temporary = tuple(
            name
            for name in _names(self._root)
            if re.fullmatch(rf"\.{self.session_id}\.[0-9a-f]{{32}}\.tmp", name)
        )
        # Validate every targeted file before the first removal. Cooperative writers
        # cannot create/replace this session's files while this lock is held.
        for name in temporary:
            fd = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self._root
            )
            try:
                validate_private_storage(fd)
            finally:
                os.close(fd)
        for name in temporary:
            os.unlink(name, dir_fd=self._root)
        os.unlink(f"{self.session_id}.json", dir_fd=self._root)
        self._deleted = True
        os.fsync(self._root)
        # Keep the empty lock inode: removing it could allow a second writer to
        # obtain a different lock for the same session while this handle is open.
        return ConversationDeletion(
            session_id=self.session_id,
            snapshot_sha256=expected,
            removed_temporary_files=len(temporary),
        )
