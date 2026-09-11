"""Exact raw staging review, with separate invalid and verified-project paths."""

import base64
import json
import os
import re
import stat
from collections.abc import Callable
from pathlib import Path

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot, MemoryStorage
from mos_eisley.conversation_memory_cleanup import MemoryCleanupStore
from mos_eisley.conversation_memory_identity import RelocationSource
from mos_eisley.core.models import canonical_bytes, digest

MAX_STAGING_REVIEW_BYTES = 4 * 1024 * 1024


class MemoryStagingDiscardError(ValueError):
    """Report returned unlink/flush operations when an in-process apply fails."""

    def __init__(self, receipt: dict[str, object]) -> None:
        super().__init__(
            "Staging discard stopped; inspect the exact file before further action."
        )
        self.receipt = receipt


def _file_identity(info: os.stat_result) -> dict[str, int]:
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "ctime_ns": info.st_ctime_ns,
        "mtime_ns": info.st_mtime_ns,
        "bytes": info.st_size,
        "owner_uid": info.st_uid,
    }


def _verify_raw_record(root: int, name: str, record: dict[str, object]) -> None:
    info = os.stat(name, dir_fd=root, follow_symlinks=False)
    if _file_identity(info) != record["file_identity"] or info.st_nlink != 1:
        raise ValueError("Staging file changed; preview discard again.")


def _read_raw_staging(
    root: int, name: str, raw_sha256: str, max_bytes: int
) -> tuple[bytes, dict[str, object]]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_mode & 0o077
            or before.st_nlink != 1
        ):
            raise ValueError("Discard requires a private, single-link regular file.")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            payload = stream.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError(
                "Staging file exceeds the 256 KiB review limit."
                if max_bytes == RECORD_BYTES
                else "Staging file exceeds the requested review byte limit."
            )
        if digest(payload) != raw_sha256:
            raise ValueError("Staging bytes do not match the reviewed raw hash.")
        for current in (
            os.fstat(fd),
            os.stat(name, dir_fd=root, follow_symlinks=False),
        ):
            if (
                current.st_dev != before.st_dev
                or current.st_ino != before.st_ino
                or current.st_ctime_ns != before.st_ctime_ns
                or current.st_size != before.st_size
                or current.st_nlink != 1
            ):
                raise ValueError("Staging file changed; preview discard again.")
        return payload, {
            "raw_sha256": raw_sha256,
            "raw_bytes_base64": base64.b64encode(payload).decode("ascii"),
            "review_max_bytes": max_bytes,
            "file_identity": _file_identity(before),
        }
    finally:
        os.close(fd)


def _discard_reviewed(
    root: int,
    name: str,
    inspect: Callable[[], dict[str, object]],
    expected_sha256: str | None,
) -> dict[str, object]:
    body = inspect()
    preview_hash = digest(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    )
    receipt: dict[str, object] = {
        **body,
        "preview_sha256": preview_hash,
        "status": "planned",
        "removed": False,
        "synced": False,
    }
    if expected_sha256 is None:
        return receipt
    if expected_sha256 != preview_hash or inspect() != body:
        raise ValueError("Staging discard changed; preview it again.")
    try:
        os.unlink(name, dir_fd=root)
        receipt["removed"] = True
        os.fsync(root)
        receipt["synced"] = True
    except OSError as error:
        receipt["status"] = "incomplete"
        raise MemoryStagingDiscardError(receipt) from error
    receipt["status"] = "completed"
    return receipt


class _StagingDiscardStore(MemoryStorage):
    def discard(
        self, name: str, raw_sha256: str, expected_sha256: str | None, max_bytes: int
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Discard requires existing memory storage and lock.")

            def inspect() -> dict[str, object]:
                storage = self._storage_identity(handles)
                payload, record = _read_raw_staging(
                    handles[0], name, raw_sha256, max_bytes
                )
                try:
                    MemorySnapshot.model_validate_json(payload)
                except ValueError:
                    pass
                else:
                    raise ValueError(
                        "Valid snapshots require project-aware cleanup; "
                        "raw discard is refused."
                    )
                if self._storage_identity(handles) != storage:
                    raise ValueError("Memory storage changed; preview discard again.")
                _verify_raw_record(handles[0], name, record)
                return {
                    "schema_version": 1,
                    "operation": "discard-invalid-memory-staging",
                    "scope": "storage",
                    "project_identity": None,
                    "project_identity_verified": False,
                    "storage": storage,
                    "temporary_name": name,
                    "temporary_path": str(self.root / name),
                    **record,
                }

            return _discard_reviewed(handles[0], name, inspect, expected_sha256)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Project staging review refuses duplicate JSON keys.")
        result[key] = value
    return result


class _ProjectStagingDiscardStore(MemoryCleanupStore):
    def discard(
        self,
        workspace: RelocationSource,
        name: str,
        raw_sha256: str,
        expected_sha256: str | None,
        max_bytes: int,
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Discard requires existing memory storage and lock.")
            root = handles[0]

            def inspect() -> dict[str, object]:
                workspace.verify()
                storage = self._storage_identity(handles)
                payload, raw_record = _read_raw_staging(
                    root, name, raw_sha256, max_bytes
                )
                snapshot = MemorySnapshot.model_validate_json(payload)
                json.loads(payload, object_pairs_hook=_unique_object)
                document = snapshot.document
                if (
                    document.owner_uid != os.getuid()
                    or document.scope != "project"
                    or document.workspace != self.workspace
                ):
                    raise ValueError(
                        "Staging record does not match this owner/project."
                    )
                current_identity = self._project_record_identity(root)
                current = self._read(root, "project")
                if (
                    self._project_record_identity(root) != current_identity
                    or self._storage_identity(handles) != storage
                ):
                    raise ValueError(
                        "Project memory or storage changed; preview again."
                    )
                workspace.verify()
                _verify_raw_record(root, name, raw_record)
                return {
                    "schema_version": 1,
                    "operation": "discard-project-memory-staging",
                    "scope": "project",
                    "project_identity": self.workspace,
                    "project_identity_verified": True,
                    "workspace_identity": workspace.receipt(),
                    "storage": storage,
                    "temporary_name": name,
                    "temporary_path": str(self.root / name),
                    "record": snapshot.model_dump(mode="json"),
                    "serialization": "canonical"
                    if payload == canonical_bytes(snapshot)
                    else "noncanonical",
                    "current_project_path": str(self.path("project")),
                    "current_project": current.model_dump(mode="json")
                    if current
                    else None,
                    "current_record_identity": current_identity,
                    **raw_record,
                }

            return _discard_reviewed(root, name, inspect, expected_sha256)


def _validate_inputs(
    temporary_name: str, raw_sha256: str, expected_sha256: str | None, max_bytes: int
) -> None:
    if (
        re.fullmatch(
            r"\.memory-(?:migration|resolution)-[0-9a-f]{32}\.tmp", temporary_name
        )
        is None
    ):
        raise ValueError("Discard requires an exact supported staging filename.")
    for value in (raw_sha256, expected_sha256):
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("Discard requires lowercase SHA-256 hashes.")
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_STAGING_REVIEW_BYTES:
        raise ValueError("--review-max-bytes must be between 1 and 4,194,304.")


def discard_memory_staging(
    storage: Path,
    temporary_name: str,
    raw_sha256: str,
    *,
    expected_sha256: str | None = None,
    review_max_bytes: int = RECORD_BYTES,
) -> dict[str, object]:
    """Review exact raw bytes; never infer a project from an invalid record."""
    _validate_inputs(temporary_name, raw_sha256, expected_sha256, review_max_bytes)
    return _StagingDiscardStore(storage).discard(
        temporary_name, raw_sha256, expected_sha256, review_max_bytes
    )


def discard_project_memory_staging(
    storage: Path,
    workspace_identity: str,
    temporary_name: str,
    raw_sha256: str,
    *,
    expected_sha256: str | None = None,
    review_max_bytes: int = RECORD_BYTES,
) -> dict[str, object]:
    """Discard one valid project snapshot, binding its logical and exact raw forms."""
    _validate_inputs(temporary_name, raw_sha256, expected_sha256, review_max_bytes)
    workspace = RelocationSource.inspect(workspace_identity)
    return _ProjectStagingDiscardStore(storage, workspace).discard(
        workspace, temporary_name, raw_sha256, expected_sha256, review_max_bytes
    )
