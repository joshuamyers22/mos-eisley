"""One explicitly reviewed invalid staging file, with unverified project identity."""

import base64
import json
import os
import re
import stat
from pathlib import Path

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot, MemoryStorage
from mos_eisley.core.models import digest


class MemoryStagingDiscardError(ValueError):
    """Report returned unlink/flush operations when an in-process apply fails."""

    def __init__(self, receipt: dict[str, object]) -> None:
        super().__init__(
            "Staging discard stopped; inspect the exact file before further action."
        )
        self.receipt = receipt


class _StagingDiscardStore(MemoryStorage):
    def _record(self, root: int, name: str, raw_sha256: str) -> dict[str, object]:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_mode & 0o077
                or before.st_nlink != 1
            ):
                raise ValueError(
                    "Discard requires a private, single-link regular file."
                )
            with os.fdopen(fd, "rb", closefd=False) as stream:
                payload = stream.read(RECORD_BYTES + 1)
            if len(payload) > RECORD_BYTES:
                raise ValueError("Staging file exceeds the 256 KiB review limit.")
            if digest(payload) != raw_sha256:
                raise ValueError("Staging bytes do not match the reviewed raw hash.")
            try:
                MemorySnapshot.model_validate_json(payload)
            except ValueError:
                pass
            else:
                raise ValueError(
                    "Valid snapshots require project-aware cleanup; "
                    "raw discard is refused."
                )
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
            return {
                "raw_sha256": raw_sha256,
                "raw_bytes_base64": base64.b64encode(payload).decode("ascii"),
                "file_identity": {
                    "device": before.st_dev,
                    "inode": before.st_ino,
                    "ctime_ns": before.st_ctime_ns,
                    "mtime_ns": before.st_mtime_ns,
                    "bytes": before.st_size,
                    "owner_uid": before.st_uid,
                },
            }
        finally:
            os.close(fd)

    def discard(
        self, name: str, raw_sha256: str, expected_sha256: str | None
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Discard requires existing memory storage and lock.")

            def inspect() -> dict[str, object]:
                return {
                    "schema_version": 1,
                    "operation": "discard-invalid-memory-staging",
                    "scope": "storage",
                    "project_identity": None,
                    "project_identity_verified": False,
                    "storage": self._storage_identity(handles),
                    "temporary_name": name,
                    "temporary_path": str(self.root / name),
                    **self._record(handles[0], name, raw_sha256),
                }

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
                os.unlink(name, dir_fd=handles[0])
                receipt["removed"] = True
                os.fsync(handles[0])
                receipt["synced"] = True
            except OSError as error:
                receipt["status"] = "incomplete"
                raise MemoryStagingDiscardError(receipt) from error
            receipt["status"] = "completed"
            return receipt


def discard_memory_staging(
    storage: Path,
    temporary_name: str,
    raw_sha256: str,
    *,
    expected_sha256: str | None = None,
) -> dict[str, object]:
    """Review exact raw bytes; never infer a project from an invalid record."""
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
    return _StagingDiscardStore(storage).discard(
        temporary_name, raw_sha256, expected_sha256
    )
