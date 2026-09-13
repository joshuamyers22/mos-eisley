"""Explicit inventory-bound retention of project-memory resolution backups."""

import argparse
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot
from mos_eisley.conversation_memory_cleanup import MemoryCleanupStore
from mos_eisley.conversation_memory_identity import RelocationSource
from mos_eisley.conversation_memory_project import memory_workspace
from mos_eisley.core.models import canonical_bytes, digest

MAX_DIRECTORY_ENTRIES = 1024
MAX_BACKUPS = 128
MAX_INVENTORY_BYTES = 8 * 1024 * 1024
MAX_PRUNE = 32
BACKUP_PATTERN = r"resolution-backup-[0-9a-f]{64}\.json"


@dataclass(frozen=True)
class _Backup:
    name: str
    snapshot: MemorySnapshot
    identity: dict[str, int]

    def receipt(self, workspace: str) -> dict[str, object]:
        return {
            "name": self.name,
            "workspace": self.snapshot.document.workspace,
            "record_sha256": self.snapshot.sha256,
            "record_identity": self.identity,
            "record": self.snapshot.model_dump(mode="json")
            if self.snapshot.document.workspace == workspace
            else None,
        }


class MemoryRetentionError(ValueError):
    """Only returned unlink/fsync calls are reported; process death has no receipt."""

    def __init__(self, receipt: dict[str, object]) -> None:
        super().__init__(
            "Memory retention stopped; inspect storage and review a fresh inventory."
        )
        self.receipt = receipt


class _RetentionStore(MemoryCleanupStore):
    def _backup(self, root: int, name: str, remaining_bytes: int) -> _Backup:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_mode & 0o077
                or before.st_nlink != 1
            ):
                raise ValueError("Inventory requires private, single-link backups.")
            limit = min(RECORD_BYTES, remaining_bytes)
            with os.fdopen(fd, "rb", closefd=False) as stream:
                payload = stream.read(limit + 1)
            if len(payload) > limit:
                raise ValueError("Backup or aggregate inventory byte limit exceeded.")
            snapshot = MemorySnapshot.model_validate_json(payload)
            document = snapshot.document
            if (
                document.owner_uid != os.getuid()
                or document.scope != "project"
                or document.workspace is None
                or canonical_bytes(snapshot) != payload
                or name != "resolution-backup-" + digest(payload) + ".json"
            ):
                raise ValueError("Backup inventory requires canonical project records.")
            memory_workspace(document.workspace, None, document.workspace)
            identity = {
                "device": before.st_dev,
                "inode": before.st_ino,
                "ctime_ns": before.st_ctime_ns,
                "mtime_ns": before.st_mtime_ns,
                "bytes": before.st_size,
            }
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
                    raise ValueError("Backup changed during inventory; preview again.")
            return _Backup(name, snapshot, identity)
        finally:
            os.close(fd)

    def _inventory(self, root: int) -> tuple[tuple[_Backup, ...], int]:
        before = os.fstat(root)
        names: list[str] = []
        entries = 0
        with os.scandir(root) as listing:
            for entry in listing:
                entries += 1
                if entries > MAX_DIRECTORY_ENTRIES:
                    raise ValueError(
                        "Memory inventory exceeds 1,024 directory entries."
                    )
                if not entry.name.startswith("resolution-backup-"):
                    continue
                if re.fullmatch(BACKUP_PATTERN, entry.name) is None:
                    raise ValueError("Unrecognized backup filename blocks retention.")
                names.append(entry.name)
                if len(names) > MAX_BACKUPS:
                    raise ValueError("Memory inventory exceeds 128 backups.")
        records: list[_Backup] = []
        used = 0
        for name in sorted(names):
            record = self._backup(root, name, MAX_INVENTORY_BYTES - used)
            used += record.identity["bytes"]
            records.append(record)
        for record in records:
            info = os.stat(record.name, dir_fd=root, follow_symlinks=False)
            if (
                info.st_dev != record.identity["device"]
                or info.st_ino != record.identity["inode"]
                or info.st_ctime_ns != record.identity["ctime_ns"]
                or info.st_size != record.identity["bytes"]
                or info.st_nlink != 1
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or not stat.S_ISREG(info.st_mode)
            ):
                raise ValueError("Backup changed during inventory; preview again.")
        after = os.fstat(root)
        if (before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError(
                "Memory directory changed during inventory; preview again."
            )
        return tuple(records), entries - len(names)

    def _observe(
        self, workspace: RelocationSource, handles: tuple[int, int]
    ) -> tuple[dict[str, object], tuple[_Backup, ...], MemorySnapshot | None]:
        workspace.verify()
        storage = self._storage_identity(handles)
        root = handles[0]
        current_identity = self._project_record_identity(root)
        current = self._read(root, "project")
        records, ignored = self._inventory(root)
        if (
            self._project_record_identity(root) != current_identity
            or self._read(root, "project") != current
            or self._storage_identity(handles) != storage
        ):
            raise ValueError("Current memory or storage changed; preview again.")
        workspace.verify()
        return (
            {
                "storage": storage,
                "workspace_identity": workspace.receipt(),
                "current_project_path": str(self.path("project")),
                "current_project": current.model_dump(mode="json") if current else None,
                "current_record_identity": current_identity,
                "ignored_entries": ignored,
                "backups": [record.receipt(self.workspace) for record in records],
            },
            records,
            current,
        )

    def retain(
        self,
        workspace: RelocationSource,
        keep_newest: int,
        before_ns: int,
        expected_sha256: str | None,
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Retention requires existing private memory storage.")
            observation, records, current = self._observe(workspace, handles)
            project = tuple(
                record
                for record in records
                if record.snapshot.document.workspace == self.workspace
            )
            newest = {
                record.name
                for record in sorted(
                    project, key=lambda item: (-item.identity["mtime_ns"], item.name)
                )[:keep_newest]
            }
            protected: list[dict[str, object]] = []
            eligible: list[_Backup] = []
            for record in project:
                reasons: list[str] = []
                if record.name in newest:
                    reasons.append("keep-newest")
                if record.identity["mtime_ns"] >= before_ns:
                    reasons.append("age-cutoff")
                if current is None:
                    reasons.append("no-current-memory")
                elif current.sha256 == record.snapshot.sha256:
                    reasons.append("matches-current-memory")
                if reasons:
                    protected.append({"name": record.name, "reasons": reasons})
                else:
                    eligible.append(record)
            eligible.sort(key=lambda item: (item.identity["mtime_ns"], item.name))
            selected = eligible[:MAX_PRUNE]
            body: dict[str, object] = {
                "schema_version": 1,
                "operation": "retain-project-memory-backups",
                "inventory": observation,
                "policy": {
                    "keep_newest": keep_newest,
                    "before_ns": before_ns,
                    "newest_order": "mtime_ns descending, filename ascending",
                    "prune_order": "mtime_ns ascending, filename ascending",
                    "max_prune": MAX_PRUNE,
                    "max_entries": MAX_DIRECTORY_ENTRIES,
                    "max_backups": MAX_BACKUPS,
                    "max_bytes": MAX_INVENTORY_BYTES,
                },
                "protected": protected,
                "selected": [record.name for record in selected],
                "remaining_eligible": [record.name for record in eligible[MAX_PRUNE:]],
            }
            preview_hash = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            )
            removed: list[str] = []
            synced: list[str] = []
            receipt = {
                **body,
                "preview_sha256": preview_hash,
                "status": "planned",
                "removed": removed,
                "synced": synced,
            }
            if expected_sha256 is None:
                return receipt
            if expected_sha256 != preview_hash:
                raise ValueError("Backup inventory or policy changed; preview again.")
            # Rescan before the first deletion and after each prior deletion. This
            # binds retained backups too, without re-ranking a partially applied plan.
            try:
                for record in selected:
                    expected = {
                        **observation,
                        "backups": [
                            item.receipt(self.workspace)
                            for item in records
                            if item.name not in removed
                        ],
                    }
                    actual, _, _ = self._observe(workspace, handles)
                    if actual != expected:
                        raise ValueError("Backup inventory changed during retention.")
                    os.unlink(record.name, dir_fd=handles[0])
                    removed.append(record.name)
                    os.fsync(handles[0])
                    synced.append(record.name)
            except (OSError, ValueError) as error:
                receipt["status"] = "incomplete"
                raise MemoryRetentionError(receipt) from error
            receipt["status"] = "completed"
            return receipt


def retain_memory_backups(
    storage: Path,
    workspace_identity: str,
    *,
    keep_newest: int,
    before_ns: int,
    expected_sha256: str | None = None,
) -> dict[str, object]:
    if type(keep_newest) is not int or not 0 <= keep_newest <= MAX_BACKUPS:
        raise ValueError("--keep-newest must be between 0 and 128.")
    if type(before_ns) is not int or not 0 < before_ns < 2**63:
        raise ValueError("Use a positive --before-ns cutoff below 2**63.")
    if (
        expected_sha256 is not None
        and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
    ):
        raise ValueError("Retention requires a lowercase SHA-256 preview hash.")
    workspace = RelocationSource.inspect(workspace_identity)
    return _RetentionStore(storage, workspace).retain(
        workspace, keep_newest, before_ns, expected_sha256
    )


def add_command(command: argparse.ArgumentParser) -> None:
    command.add_argument("--workspace-identity", required=True)
    command.add_argument("--keep-newest", type=int, required=True)
    command.add_argument("--before-ns", type=int, required=True)
    command.add_argument(
        "--memory-storage", type=Path, default=Path.home() / ".mos-eisley-memory"
    )
    command.add_argument("--apply", action="store_true")
    command.add_argument("--expected-sha256")
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    if args.apply != (args.expected_sha256 is not None):
        raise ValueError("Use --apply and --expected-sha256 together.")
    notice = None
    try:
        receipt = retain_memory_backups(
            args.memory_storage,
            args.workspace_identity,
            keep_newest=args.keep_newest,
            before_ns=args.before_ns,
            expected_sha256=args.expected_sha256,
        )
    except MemoryRetentionError as error:
        receipt = error.receipt
        notice = str(error)
    payload = {"type": "memory.project_retention", **receipt}
    if notice is not None:
        payload["text"] = notice
    print(json.dumps(payload, ensure_ascii=True, indent=None if args.json else 2))
    return 0 if notice is None else 2
