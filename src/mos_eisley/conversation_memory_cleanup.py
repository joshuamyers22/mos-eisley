"""Explicit review of one complete staging file or interrupted backup link."""

import json
import os
import re
import stat
from pathlib import Path
from typing import Literal

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot
from mos_eisley.conversation_memory_identity import RelocationSource
from mos_eisley.conversation_memory_migration import MemoryMigrationStore
from mos_eisley.core.models import canonical_bytes, digest

CleanupAction = Literal["discard-staging", "recover-backup-link"]


class MemoryCleanupStore(MemoryMigrationStore):
    """Validated record readers shared by explicit single and batch cleanup."""

    def __init__(self, storage: Path, identity: RelocationSource) -> None:
        identity.verify()
        self.root = storage.absolute()
        self.workspace = str(identity.path)

    def _single_link_record(
        self, root: int, name: str, record_sha256: str
    ) -> tuple[MemorySnapshot, dict[str, int]]:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_mode & 0o077
                or before.st_nlink != 1
            ):
                raise ValueError("Cleanup requires a private, single-link record.")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                payload = stream.read(RECORD_BYTES + 1)
                if len(payload) > RECORD_BYTES:
                    raise ValueError("memory record exceeds byte limit")
                snapshot = MemorySnapshot.model_validate_json(payload)
                if (
                    snapshot.sha256 != record_sha256
                    or snapshot.document.owner_uid != os.getuid()
                    or snapshot.document.scope != "project"
                    or snapshot.document.workspace != self.workspace
                    or payload != canonical_bytes(snapshot)
                ):
                    raise ValueError(
                        "Cleanup record does not match the reviewed project memory."
                    )
                identity = {
                    "device": before.st_dev,
                    "inode": before.st_ino,
                    "ctime_ns": before.st_ctime_ns,
                    "mtime_ns": before.st_mtime_ns,
                    "bytes": before.st_size,
                }
                for current in (
                    os.fstat(stream.fileno()),
                    os.stat(name, dir_fd=root, follow_symlinks=False),
                ):
                    if (
                        current.st_dev != before.st_dev
                        or current.st_ino != before.st_ino
                        or current.st_ctime_ns != before.st_ctime_ns
                        or current.st_nlink != 1
                        or current.st_size != before.st_size
                    ):
                        raise ValueError(
                            "Cleanup record changed; preview cleanup again."
                        )
        finally:
            os.close(fd)
        return snapshot, identity

    def _inspect_cleanup(
        self,
        workspace: RelocationSource,
        handles: tuple[int, int],
        temporary_name: str,
        action: CleanupAction,
        record_sha256: str,
        backup_name: str | None,
    ) -> dict[str, object]:
        root = handles[0]
        workspace.verify()
        storage = self._storage_identity(handles)
        if backup_name is None:
            snapshot, identity = self._single_link_record(
                root, temporary_name, record_sha256
            )
        else:
            snapshot, identity = self._recovery_record(
                root, temporary_name, record_sha256, record_name=backup_name
            )
            if (
                backup_name
                != "resolution-backup-" + digest(canonical_bytes(snapshot)) + ".json"
            ):
                raise ValueError("Backup filename does not match its canonical record.")
        current = self._read(root, "project")
        return {
            "schema_version": 1,
            "operation": "cleanup-project-memory-staging",
            "action": action,
            "storage": storage,
            "workspace_identity": workspace.receipt(),
            "temporary_path": str(self.root / temporary_name),
            "backup_path": str(self.root / backup_name) if backup_name else None,
            "record": snapshot.model_dump(mode="json"),
            "record_identity": identity,
            "current_project_path": str(self.path("project")),
            "current_project": current.model_dump(mode="json") if current else None,
            "current_record_identity": self._project_record_identity(root),
        }

    def cleanup(
        self,
        workspace: RelocationSource,
        temporary_name: str,
        action: CleanupAction,
        record_sha256: str,
        backup_name: str | None,
        expected_sha256: str | None,
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Cleanup requires existing memory storage.")
            root = handles[0]

            def inspect() -> dict[str, object]:
                return self._inspect_cleanup(
                    workspace,
                    handles,
                    temporary_name,
                    action,
                    record_sha256,
                    backup_name,
                )

            body = inspect()
            preview_hash = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
            if expected_sha256 is not None:
                if preview_hash != expected_sha256 or inspect() != body:
                    raise ValueError("Memory cleanup changed; preview it again.")
                os.unlink(temporary_name, dir_fd=root)
                os.fsync(root)
                if backup_name is not None:
                    snapshot = MemorySnapshot.model_validate_json(
                        json.dumps(body["record"])
                    )
                    if not self._resolution_backup(root, backup_name, snapshot):
                        raise ValueError(
                            "Recovered backup is missing; inspect storage."
                        )
            return {
                **body,
                "preview_sha256": preview_hash,
                "applied": expected_sha256 is not None,
                "removed": temporary_name if expected_sha256 is not None else None,
            }


def cleanup_memory_project(
    storage: Path,
    workspace_identity: str,
    *,
    action: CleanupAction,
    temporary_name: str,
    record_sha256: str,
    backup_name: str | None = None,
    expected_sha256: str | None = None,
) -> dict[str, object]:
    """Review one exact deletion; never scan, infer age or prune retained backups."""
    if action not in ("discard-staging", "recover-backup-link"):
        raise ValueError("Choose an explicit memory cleanup action.")
    if (action == "recover-backup-link") != (backup_name is not None):
        raise ValueError("Use --backup-name only with recover-backup-link.")
    pattern = (
        r"\.memory-migration-[0-9a-f]{32}\.tmp"
        if backup_name is not None
        else r"\.memory-(?:migration|resolution)-[0-9a-f]{32}\.tmp"
    )
    if re.fullmatch(pattern, temporary_name) is None:
        raise ValueError("Cleanup requires an exact supported staging filename.")
    if (
        backup_name is not None
        and re.fullmatch(r"resolution-backup-[0-9a-f]{64}\.json", backup_name) is None
    ):
        raise ValueError("Recovery requires an exact resolution backup filename.")
    for value in (record_sha256, expected_sha256):
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("Cleanup requires lowercase SHA-256 hashes.")
    workspace = RelocationSource.inspect(workspace_identity)
    return MemoryCleanupStore(storage, workspace).cleanup(
        workspace, temporary_name, action, record_sha256, backup_name, expected_sha256
    )
