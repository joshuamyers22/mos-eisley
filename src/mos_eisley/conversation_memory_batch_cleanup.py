"""Bounded explicit memory cleanup, including retained-backup age policy."""

import json
import os
import re
import stat
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_memory import MemorySnapshot
from mos_eisley.conversation_memory_cleanup import MemoryCleanupStore
from mos_eisley.conversation_memory_identity import RelocationSource
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest

MAX_CLEANUP_RECORDS = 32
MAX_CLEANUP_MANIFEST_BYTES = 64 * 1024
BackupName = Annotated[str, Field(pattern=r"^resolution-backup-[0-9a-f]{64}\.json$")]
StagingName = Annotated[
    str, Field(pattern=r"^\.memory-(?:migration|resolution)-[0-9a-f]{32}\.tmp$")
]


class MemoryCleanupSelection(Contract):
    action: Literal["discard-staging", "recover-backup-link", "prune-backup"]
    record_sha256: Digest
    temporary_name: StagingName | None = None
    backup_name: BackupName | None = None

    @model_validator(mode="after")
    def exact_names(self) -> Self:
        for name, pattern in (
            (
                self.temporary_name,
                r"\.memory-(?:migration|resolution)-[0-9a-f]{32}\.tmp",
            ),
            (self.backup_name, r"resolution-backup-[0-9a-f]{64}\.json"),
            (self.record_sha256, r"[0-9a-f]{64}"),
        ):
            if name is not None and re.fullmatch(pattern, name) is None:
                raise ValueError("Cleanup requires exact filenames and hashes.")
        if self.action == "prune-backup":
            valid = self.temporary_name is None and self.backup_name is not None
        else:
            valid = self.temporary_name is not None and (
                (self.action == "recover-backup-link") == (self.backup_name is not None)
            )
            if self.action == "recover-backup-link":
                valid = valid and str(self.temporary_name).startswith(
                    ".memory-migration-"
                )
        if not valid:
            raise ValueError("Cleanup action requires its exact supported names.")
        return self

    @property
    def removed_name(self) -> str:
        name = (
            self.backup_name if self.action == "prune-backup" else self.temporary_name
        )
        assert name is not None
        return name


class MemoryCleanupManifest(Contract):
    schema_version: Literal[1] = 1
    records: Annotated[
        tuple[MemoryCleanupSelection, ...],
        Field(min_length=1, max_length=MAX_CLEANUP_RECORDS),
    ]

    @model_validator(mode="after")
    def distinct_names(self) -> Self:
        names = [
            name
            for record in self.records
            for name in (record.temporary_name, record.backup_name)
            if name is not None
        ]
        if len(names) != len(set(names)):
            raise ValueError("Cleanup selections must not share any filename.")
        return self


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Cleanup manifest contains a duplicate JSON key.")
        result[key] = value
    return result


def read_cleanup_manifest(path: Path) -> MemoryCleanupManifest:
    """Read one bounded regular file without following a final symlink."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Cleanup manifest must be a regular file.")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            payload = stream.read(MAX_CLEANUP_MANIFEST_BYTES + 1)
    finally:
        os.close(fd)
    if len(payload) > MAX_CLEANUP_MANIFEST_BYTES:
        raise ValueError("Cleanup manifest exceeds 64 KiB.")
    json.loads(payload, object_pairs_hook=_unique_object)
    return MemoryCleanupManifest.model_validate_json(payload)


class MemoryBatchCleanupError(ValueError):
    """In-process partial progress; an interrupted process may emit no receipt."""

    def __init__(self, receipt: dict[str, object]) -> None:
        super().__init__(
            "Memory cleanup stopped; inspect selected names and preview the remainder."
        )
        self.receipt = receipt


class _BatchCleanupStore(MemoryCleanupStore):
    def _inspect_selection(
        self,
        workspace: RelocationSource,
        handles: tuple[int, int],
        selection: MemoryCleanupSelection,
        before_ns: int | None,
    ) -> dict[str, object]:
        if selection.action != "prune-backup":
            assert selection.temporary_name is not None
            return self._inspect_cleanup(
                workspace,
                handles,
                selection.temporary_name,
                selection.action,
                selection.record_sha256,
                selection.backup_name,
            )
        assert selection.backup_name is not None and before_ns is not None
        workspace.verify()
        storage = self._storage_identity(handles)
        root = handles[0]
        snapshot, identity = self._single_link_record(
            root, selection.backup_name, selection.record_sha256
        )
        if selection.backup_name != (
            "resolution-backup-" + digest(canonical_bytes(snapshot)) + ".json"
        ):
            raise ValueError("Backup filename does not match its canonical record.")
        if identity["mtime_ns"] >= before_ns:
            raise ValueError("Backup is protected by the explicit age cutoff.")
        current = self._read(root, "project")
        if current is None or current.sha256 == snapshot.sha256:
            raise ValueError("Backup pruning requires distinct current project memory.")
        return {
            "action": selection.action,
            "storage": storage,
            "workspace_identity": workspace.receipt(),
            "backup_path": str(self.root / selection.backup_name),
            "record": snapshot.model_dump(mode="json"),
            "record_identity": identity,
            "current_project_path": str(self.path("project")),
            "current_project": current.model_dump(mode="json"),
            "current_record_identity": self._project_record_identity(root),
        }

    def batch(
        self,
        workspace: RelocationSource,
        manifest: MemoryCleanupManifest,
        before_ns: int | None,
        expected_sha256: str | None,
    ) -> dict[str, object]:
        selections = tuple(sorted(manifest.records, key=lambda item: item.removed_name))
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Cleanup requires existing memory storage.")

            def inspect() -> list[dict[str, object]]:
                return [
                    self._inspect_selection(workspace, handles, item, before_ns)
                    for item in selections
                ]

            records = inspect()
            body: dict[str, object] = {
                "schema_version": 1,
                "operation": "cleanup-project-memory-batch",
                "before_ns": before_ns,
                "records": records,
            }
            preview_hash = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            )
            removed: list[str] = []
            synced: list[str] = []
            receipt: dict[str, object] = {
                **body,
                "preview_sha256": preview_hash,
                "status": "planned",
                "removed": removed,
                "synced": synced,
            }
            if expected_sha256 is None:
                return receipt
            if preview_hash != expected_sha256 or inspect() != records:
                raise ValueError("Memory cleanup batch changed; preview it again.")
            root = handles[0]
            try:
                for selection, reviewed in zip(selections, records, strict=True):
                    if (
                        self._inspect_selection(
                            workspace, handles, selection, before_ns
                        )
                        != reviewed
                    ):
                        raise ValueError("Cleanup selection changed during apply.")
                    os.unlink(selection.removed_name, dir_fd=root)
                    removed.append(selection.removed_name)
                    os.fsync(root)
                    synced.append(selection.removed_name)
                    if selection.action == "recover-backup-link":
                        assert selection.backup_name is not None
                        snapshot = MemorySnapshot.model_validate_json(
                            json.dumps(reviewed["record"])
                        )
                        if not self._resolution_backup(
                            root, selection.backup_name, snapshot
                        ):
                            raise ValueError(
                                "Recovered backup is missing; inspect storage."
                            )
            except (OSError, ValueError) as error:
                receipt["status"] = "incomplete"
                raise MemoryBatchCleanupError(receipt) from error
            receipt["status"] = "completed"
            return receipt


def cleanup_memory_batch(
    storage: Path,
    workspace_identity: str,
    manifest: MemoryCleanupManifest,
    *,
    before_ns: int | None = None,
    expected_sha256: str | None = None,
) -> dict[str, object]:
    """Review all explicit files before any deletion; never scan or auto-select."""
    manifest = MemoryCleanupManifest.model_validate_json(canonical_bytes(manifest))
    pruning = any(item.action == "prune-backup" for item in manifest.records)
    if pruning != (before_ns is not None) or (
        before_ns is not None
        and (type(before_ns) is not int or not 0 < before_ns < 2**63)
    ):
        raise ValueError(
            "Use a positive --before-ns cutoff exactly when pruning backups."
        )
    if (
        expected_sha256 is not None
        and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
    ):
        raise ValueError("Cleanup requires a lowercase SHA-256 preview hash.")
    workspace = RelocationSource.inspect(workspace_identity)
    return _BatchCleanupStore(storage, workspace).batch(
        workspace, manifest, before_ns, expected_sha256
    )
