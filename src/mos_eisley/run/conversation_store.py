"""Private, locked, atomically replaced local conversation snapshots."""

from __future__ import annotations

import fcntl
import os
import stat
from contextlib import suppress
from pathlib import Path
from types import TracebackType
from typing import Self
from uuid import uuid4

from mos_eisley.conversation import ConversationState, SessionID
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest

MAX_BYTES = 2_000_000


class ConversationSnapshot(Contract):
    state: ConversationState
    sha256: Digest


def _private(fd: int, *, directory: bool = False) -> None:
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


class ConversationStore:
    """A held per-session flock rejects competing writers for this entire handle."""

    def __init__(self, root: Path, session_id: str, workspace: Path) -> None:
        from pydantic import TypeAdapter

        self.session_id = TypeAdapter[str](SessionID).validate_python(session_id)
        if not workspace.is_dir():
            raise ValueError("conversation workspace must be a directory")
        self.workspace = str(workspace.resolve(strict=True))
        self._revision = -1
        self._sha256: str | None = None
        root.mkdir(mode=0o700, exist_ok=True)
        self._root = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self._lock = -1
        try:
            _private(self._root, directory=True)
            self._lock = os.open(
                f"{session_id}.lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=self._root,
            )
            _private(self._lock)
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
        _private(self._root, directory=True)
        fd = os.open(
            f"{self.session_id}.json",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=self._root,
        )
        with os.fdopen(fd, "rb") as stream:
            _private(stream.fileno())
            payload = stream.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("conversation snapshot exceeds byte limit")
        snapshot = ConversationSnapshot.model_validate_json(payload)
        state = snapshot.state
        if (
            state.owner_uid != os.getuid()
            or state.session_id != self.session_id
            or state.workspace != self.workspace
            or snapshot.sha256 != digest(canonical_bytes(state))
        ):
            raise ValueError("conversation ownership, workspace or integrity mismatch")
        return snapshot

    def load(self) -> ConversationState:
        snapshot = self._read()
        self._revision = snapshot.state.revision
        self._sha256 = snapshot.sha256
        return snapshot.state

    def save(self, state: ConversationState) -> None:
        _private(self._root, directory=True)
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
        if len(payload) > MAX_BYTES:
            raise ValueError("conversation snapshot exceeds byte limit")
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
