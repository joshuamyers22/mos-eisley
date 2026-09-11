"""Bounded, explicitly selected cleanup of unpublished JSON staging files."""

import fcntl
import hashlib
import os
import re
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from mos_eisley.conversation_state import SessionID
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.conversation_store import (
    MAX_BYTES,
    MAX_DIRECTORY_ENTRIES,
    validate_private_storage,
)
from mos_eisley.run.conversation_transfer import (
    TransferLocation,
    inspect_storage_location,
)

MAX_TEMPORARY_FILES = 256
MAX_CLEANUP_BYTES = 64_000_000
TemporaryName = Annotated[str, Field(pattern=r"^\.[0-9a-f]{32}\.[0-9a-f]{32}\.tmp$")]


class TemporaryFileIdentity(Contract):
    device: Annotated[int, Field(ge=0)]
    inode: Annotated[int, Field(ge=0)]
    bytes: Annotated[int, Field(ge=0, le=MAX_BYTES)]
    modified_ns: Annotated[int, Field(ge=0)]
    changed_ns: Annotated[int, Field(ge=0)]


class TemporaryFileSelection(Contract):
    name: TemporaryName
    identity: TemporaryFileIdentity
    sha256: Digest


class TemporaryCleanupPlan(Contract):
    schema_version: Literal[1] = 1
    scope: Literal["storage_owner"] = "storage_owner"
    storage: TransferLocation
    owner_uid: Annotated[int, Field(ge=0)]
    session_id: SessionID
    lock_device: Annotated[int, Field(ge=0)]
    lock_inode: Annotated[int, Field(ge=0)]
    byte_limit: Literal[64_000_000] = MAX_CLEANUP_BYTES
    files: Annotated[
        tuple[TemporaryFileSelection, ...], Field(max_length=MAX_TEMPORARY_FILES)
    ]
    bytes: Annotated[int, Field(ge=0, le=MAX_CLEANUP_BYTES)]

    @model_validator(mode="after")
    def exact_selection(self) -> Self:
        names = tuple(file.name for file in self.files)
        if names != tuple(sorted(set(names))) or any(
            not name.startswith(f".{self.session_id}.") for name in names
        ):
            raise ValueError("cleanup requires sorted unique files for one session")
        if self.bytes != sum(file.identity.bytes for file in self.files):
            raise ValueError("cleanup byte count does not match its selection")
        return self


class TemporaryCleanupReceipt(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["preview", "apply"]
    status: Literal["planned", "completed", "stopped"]
    cleanup_sha256: Digest
    plan: TemporaryCleanupPlan
    removed: Annotated[tuple[TemporaryName, ...], Field(max_length=MAX_TEMPORARY_FILES)]
    removed_bytes: Annotated[int, Field(ge=0, le=MAX_CLEANUP_BYTES)]
    directory_synced: bool
    failure: (
        Literal["selection_changed", "storage_unavailable", "durability_unconfirmed"]
        | None
    ) = None
    published_sessions_retained: Literal[True] = True

    @model_validator(mode="after")
    def exact_result(self) -> Self:
        prefix = self.plan.files[: len(self.removed)]
        if (
            self.cleanup_sha256 != digest(canonical_bytes(self.plan))
            or self.removed != tuple(file.name for file in prefix)
            or self.removed_bytes != sum(file.identity.bytes for file in prefix)
        ):
            raise ValueError("cleanup receipt does not match its selected prefix")
        if self.mode == "preview":
            valid = (
                self.status == "planned"
                and not self.removed
                and not self.directory_synced
                and self.failure is None
            )
        elif self.status == "completed":
            valid = (
                len(self.removed) == len(self.plan.files)
                and self.directory_synced
                and self.failure is None
            )
        else:
            valid = self.status == "stopped" and self.failure is not None
            valid = valid and (
                self.directory_synced == (self.failure != "durability_unconfirmed")
            )
        if not valid:
            raise ValueError("inconsistent cleanup result")
        return self


class TemporaryCleanupError(ValueError):
    def __init__(self, receipt: TemporaryCleanupReceipt) -> None:
        super().__init__("temporary cleanup stopped; preview remaining files again")
        self.receipt = receipt


@contextmanager
def _locked_storage(location: TransferLocation, sid: str) -> Generator[tuple[int, int]]:
    root = os.open(location.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        validate_private_storage(root, directory=True)
        info = os.fstat(root)
        if (info.st_dev, info.st_ino) != location.identity:
            raise ValueError("selected cleanup directory changed")
        lock = os.open(
            f"{sid}.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root
        )
        try:
            validate_private_storage(lock)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield root, lock
        finally:
            os.close(lock)
    finally:
        os.close(root)


def _names(root: int, sid: str) -> tuple[str, ...]:
    names: list[str] = []
    with os.scandir(root) as entries:
        for count, entry in enumerate(entries):
            if count >= MAX_DIRECTORY_ENTRIES:
                raise ValueError("conversation directory exceeds entry limit")
            if re.fullmatch(rf"\.{sid}\.[0-9a-f]{{32}}\.tmp", entry.name):
                names.append(entry.name)
                if len(names) > MAX_TEMPORARY_FILES:
                    raise ValueError("temporary cleanup exceeds file count limit")
    return tuple(sorted(names))


def _identity(fd: int) -> TemporaryFileIdentity:
    validate_private_storage(fd)
    info = os.fstat(fd)
    return TemporaryFileIdentity(
        device=info.st_dev,
        inode=info.st_ino,
        bytes=info.st_size,
        modified_ns=info.st_mtime_ns,
        changed_ns=info.st_ctime_ns,
    )


def _inspect(root: int, name: str, remaining: int) -> TemporaryFileSelection:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
    with os.fdopen(fd, "rb") as stream:
        identity = _identity(stream.fileno())
        if identity.bytes > remaining:
            raise ValueError("temporary cleanup exceeds byte limit")
        checksum = hashlib.sha256()
        size = 0
        while block := stream.read(min(65_536, identity.bytes - size + 1)):
            size += len(block)
            if size > identity.bytes:
                raise ValueError("temporary file changed during preview")
            checksum.update(block)
        if size != identity.bytes or _identity(stream.fileno()) != identity:
            raise ValueError("temporary file changed during preview")
    return TemporaryFileSelection(
        name=name, identity=identity, sha256=checksum.hexdigest()
    )


def _check_location(root: int, lock: int, plan: TemporaryCleanupPlan) -> None:
    validate_private_storage(root, directory=True)
    validate_private_storage(lock)
    if inspect_storage_location(Path(plan.storage.path)) != plan.storage:
        raise ValueError("selected cleanup directory changed")
    current = os.open(
        f"{plan.session_id}.lock",
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=root,
    )
    try:
        validate_private_storage(current)
        info = os.fstat(current)
        if (info.st_dev, info.st_ino) != (plan.lock_device, plan.lock_inode):
            raise ValueError("selected cleanup lock changed")
    finally:
        os.close(current)


def _remove(root: int, selected: TemporaryFileSelection) -> None:
    fd = os.open(
        selected.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root
    )
    try:
        if _identity(fd) != selected.identity:
            raise ValueError("selected temporary file changed")
        # The held session lock excludes all cooperative JSON and SQLite writers.
        # Trusted owner-local directories remain the same boundary as save/delete.
        os.unlink(selected.name, dir_fd=root)
    finally:
        os.close(fd)


def _apply(root: int, lock: int, plan: TemporaryCleanupPlan) -> TemporaryCleanupReceipt:
    removed: list[str] = []
    removed_bytes = 0
    failure: (
        Literal["selection_changed", "storage_unavailable", "durability_unconfirmed"]
        | None
    ) = None
    try:
        for selected in plan.files:
            _check_location(root, lock, plan)
            _remove(root, selected)
            removed.append(selected.name)
            removed_bytes += selected.identity.bytes
    except ValueError:
        failure = "selection_changed"
    except OSError:
        failure = "storage_unavailable"
    try:
        os.fsync(root)
        synced = True
    except OSError:
        synced = False
        failure = "durability_unconfirmed"
    receipt = TemporaryCleanupReceipt(
        mode="apply",
        status="completed" if failure is None else "stopped",
        cleanup_sha256=digest(canonical_bytes(plan)),
        plan=plan,
        removed=tuple(removed),
        removed_bytes=removed_bytes,
        directory_synced=synced,
        failure=failure,
    )
    if failure is not None:
        raise TemporaryCleanupError(receipt)
    return receipt


def cleanup_temporary_files(
    root: Path,
    session_id: str,
    *,
    expected_sha256: str | None = None,
    apply: bool = False,
) -> TemporaryCleanupReceipt:
    """Select owner-local staging files, including incomplete first writes.

    No workspace attribution can be proven for truncated bytes. This is explicit
    storage-owner maintenance, never a workspace catalog or automatic retention.
    Published JSON, SQLite databases/journals and lock inodes are never removed.
    """
    try:
        sid = TypeAdapter[str](SessionID).validate_python(session_id)
        expected = (
            None
            if expected_sha256 is None
            else TypeAdapter[str](Digest).validate_python(expected_sha256)
        )
    except ValueError:
        raise ValueError("invalid cleanup session ID or expected hash") from None
    if apply and expected is None:
        raise ValueError("--apply requires --expected-sha256 from a cleanup preview")
    location = inspect_storage_location(root)
    with _locked_storage(location, sid) as (directory, lock):
        files: list[TemporaryFileSelection] = []
        size = 0
        for name in _names(directory, sid):
            selected = _inspect(directory, name, MAX_CLEANUP_BYTES - size)
            files.append(selected)
            size += selected.identity.bytes
        info = os.fstat(lock)
        plan = TemporaryCleanupPlan(
            storage=location,
            owner_uid=os.getuid(),
            session_id=sid,
            lock_device=info.st_dev,
            lock_inode=info.st_ino,
            files=tuple(files),
            bytes=size,
        )
        selection_hash = digest(canonical_bytes(plan))
        if expected is not None and selection_hash != expected:
            raise ValueError("temporary cleanup selection changed; preview again")
        _check_location(directory, lock, plan)
        if apply:
            return _apply(directory, lock, plan)
        return TemporaryCleanupReceipt(
            mode="preview",
            status="planned",
            cleanup_sha256=selection_hash,
            plan=plan,
            removed=(),
            removed_bytes=0,
            directory_synced=False,
        )
