"""Exact-file disposal for backups that cannot enter canonical retention."""

import argparse
import json
import os
import re
from pathlib import Path

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot, MemoryStorage
from mos_eisley.conversation_memory_cleanup import MemoryCleanupStore
from mos_eisley.conversation_memory_identity import RelocationSource
from mos_eisley.conversation_memory_raw import (
    MemoryDiscardError,
    discard_reviewed,
    read_raw_record,
    validate_raw_review,
    verify_raw_record,
)
from mos_eisley.conversation_memory_retention import BACKUP_PATTERN
from mos_eisley.core.models import canonical_bytes, digest


class MemoryBackupDiscardError(MemoryDiscardError):
    """Deletion may have completed even when directory durability is uncertain."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Project backup review refuses duplicate JSON keys.")
        result[key] = value
    return result


class _InvalidBackupStore(MemoryStorage):
    def discard(
        self, name: str, raw_sha256: str, expected_sha256: str | None, max_bytes: int
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Discard requires existing memory storage and lock.")

            def inspect() -> dict[str, object]:
                storage = self._storage_identity(handles)
                payload, record = read_raw_record(
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
                verify_raw_record(handles[0], name, record)
                return {
                    "schema_version": 1,
                    "operation": "discard-invalid-memory-backup",
                    "scope": "storage",
                    "project_identity": None,
                    "project_identity_verified": False,
                    "current_memory_protection": "unverified-invalid-record",
                    "storage": storage,
                    "backup_name": name,
                    "backup_path": str(self.root / name),
                    **record,
                }

            return discard_reviewed(
                handles[0], name, inspect, expected_sha256, MemoryBackupDiscardError
            )


class _ProjectBackupStore(MemoryCleanupStore):
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
                payload, record = read_raw_record(root, name, raw_sha256, max_bytes)
                snapshot = MemorySnapshot.model_validate_json(payload)
                json.loads(payload, object_pairs_hook=_unique_object)
                if (
                    snapshot.document.owner_uid != os.getuid()
                    or snapshot.document.scope != "project"
                    or snapshot.document.workspace != self.workspace
                ):
                    raise ValueError("Backup record does not match this owner/project.")
                canonical = canonical_bytes(snapshot)
                canonical_name = "resolution-backup-" + digest(canonical) + ".json"
                reasons: list[str] = []
                if payload != canonical:
                    reasons.append("noncanonical-serialization")
                if name != canonical_name:
                    reasons.append("filename-mismatch")
                if len(payload) > RECORD_BYTES:
                    reasons.append("exceeds-retention-record-limit")
                if not reasons:
                    raise ValueError(
                        "Supported canonical backups require retention "
                        "or batch cleanup."
                    )
                current_identity = self._project_record_identity(root)
                current = self._read(root, "project")
                if current is None:
                    raise ValueError("Backup protected: no current project memory.")
                if current.sha256 == snapshot.sha256:
                    raise ValueError(
                        "Backup protected: matches current project memory."
                    )
                if (
                    self._project_record_identity(root) != current_identity
                    or self._storage_identity(handles) != storage
                ):
                    raise ValueError(
                        "Project memory or storage changed; preview again."
                    )
                workspace.verify()
                verify_raw_record(root, name, record)
                return {
                    "schema_version": 1,
                    "operation": "discard-unsupported-project-memory-backup",
                    "scope": "project",
                    "project_identity": self.workspace,
                    "project_identity_verified": True,
                    "current_memory_protection": "verified-distinct-current-record",
                    "workspace_identity": workspace.receipt(),
                    "storage": storage,
                    "backup_name": name,
                    "backup_path": str(self.root / name),
                    "canonical_backup_name": canonical_name,
                    "unsupported_reasons": reasons,
                    "record": snapshot.model_dump(mode="json"),
                    "current_project_path": str(self.path("project")),
                    "current_project": current.model_dump(mode="json"),
                    "current_record_identity": current_identity,
                    **record,
                }

            return discard_reviewed(
                root, name, inspect, expected_sha256, MemoryBackupDiscardError
            )


def _validate(
    name: str, raw_sha256: str, expected_sha256: str | None, max_bytes: int
) -> None:
    if re.fullmatch(BACKUP_PATTERN, name) is None:
        raise ValueError("Discard requires an exact resolution backup filename.")
    validate_raw_review(raw_sha256, expected_sha256, max_bytes)


def discard_memory_backup(
    storage: Path,
    backup_name: str,
    raw_sha256: str,
    *,
    expected_sha256: str | None = None,
    review_max_bytes: int = RECORD_BYTES,
) -> dict[str, object]:
    """Review invalid bytes without inferring project identity or recoverability."""
    _validate(backup_name, raw_sha256, expected_sha256, review_max_bytes)
    return _InvalidBackupStore(storage).discard(
        backup_name, raw_sha256, expected_sha256, review_max_bytes
    )


def discard_project_memory_backup(
    storage: Path,
    workspace_identity: str,
    backup_name: str,
    raw_sha256: str,
    *,
    expected_sha256: str | None = None,
    review_max_bytes: int = RECORD_BYTES,
) -> dict[str, object]:
    """Review unsupported valid backups while protecting current project memory."""
    _validate(backup_name, raw_sha256, expected_sha256, review_max_bytes)
    workspace = RelocationSource.inspect(workspace_identity)
    return _ProjectBackupStore(storage, workspace).discard(
        workspace, backup_name, raw_sha256, expected_sha256, review_max_bytes
    )


def add_command(command: argparse.ArgumentParser, *, project: bool) -> None:
    if project:
        command.add_argument("--workspace-identity", required=True)
    command.add_argument("--backup-name", required=True)
    command.add_argument("--raw-sha256", required=True)
    command.add_argument("--review-max-bytes", type=int, default=RECORD_BYTES)
    command.add_argument(
        "--memory-storage", type=Path, default=Path.home() / ".mos-eisley-memory"
    )
    command.add_argument("--apply", action="store_true")
    command.add_argument("--expected-sha256")
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    if args.apply != (args.expected_sha256 is not None):
        raise ValueError("Use --apply and --expected-sha256 together.")
    project = args.command == "memory-project-backup-discard"
    notice = None
    try:
        if project:
            receipt = discard_project_memory_backup(
                args.memory_storage,
                args.workspace_identity,
                args.backup_name,
                args.raw_sha256,
                expected_sha256=args.expected_sha256,
                review_max_bytes=args.review_max_bytes,
            )
        else:
            receipt = discard_memory_backup(
                args.memory_storage,
                args.backup_name,
                args.raw_sha256,
                expected_sha256=args.expected_sha256,
                review_max_bytes=args.review_max_bytes,
            )
    except MemoryBackupDiscardError as error:
        receipt = error.receipt
        notice = str(error)
    payload = {
        "type": "memory.project_backup_discard" if project else "memory.backup_discard",
        **receipt,
    }
    if notice is not None:
        payload["text"] = notice
    print(json.dumps(payload, ensure_ascii=True, indent=None if args.json else 2))
    return 0 if notice is None else 2
