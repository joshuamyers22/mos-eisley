"""Explicit, complete-inventory retention of private mapping-registry backups."""

import argparse
import json
import os
import re
import stat
from dataclasses import dataclass

from mos_eisley.conversation_memory_raw import raw_file_identity
from mos_eisley.conversation_memory_registry import (
    REGISTRY_BYTES,
    REGISTRY_NAME,
    MemoryMappingRegistry,
    MemoryMappingStore,
    RegistryFile,
    decode_registry,
    mapping_backup_name,
    read_registry_file,
)
from mos_eisley.conversation_memory_registry_history import (
    MAX_HISTORY_BYTES,
    MAX_HISTORY_ENTRIES,
    MAX_HISTORY_FILES,
)
from mos_eisley.core.models import digest

MAX_MAPPING_PRUNE = 32
_BACKUP = re.compile(r"mapping-backup-[0-9a-f]{64}\.json")


@dataclass(frozen=True)
class MappingBackup:
    name: str
    record: RegistryFile
    registry: MemoryMappingRegistry

    def receipt(self) -> dict[str, object]:
        return {
            "name": self.name,
            "raw_sha256": digest(self.record.payload),
            "file_identity": self.record.identity,
            "registry": self.registry.model_dump(mode="json"),
        }


class MappingRetentionError(ValueError):
    def __init__(self, receipt: dict[str, object]) -> None:
        super().__init__(
            "Mapping retention stopped; inspect history and review a fresh inventory."
        )
        self.receipt = receipt


class MemoryMappingRetention(MemoryMappingStore):
    def _inventory(self, root: int) -> tuple[tuple[MappingBackup, ...], int]:
        before = os.fstat(root)
        names: list[str] = []
        count = 0
        with os.scandir(root) as entries:
            for entry in entries:
                count += 1
                if count > MAX_HISTORY_ENTRIES:
                    raise ValueError(
                        "Mapping retention exceeds 1,024 directory entries."
                    )
                if not entry.name.startswith("mapping-backup-"):
                    continue
                if _BACKUP.fullmatch(entry.name) is None:
                    raise ValueError(
                        "Unsupported mapping backup filename blocks retention."
                    )
                names.append(entry.name)
                if len(names) > MAX_HISTORY_FILES:
                    raise ValueError("Mapping retention exceeds 128 backups.")
        records: list[MappingBackup] = []
        used = 0
        for name in sorted(names):
            record = read_registry_file(
                root, name, max_bytes=min(REGISTRY_BYTES, MAX_HISTORY_BYTES - used)
            )
            if record is None:
                raise ValueError("Mapping backup inventory changed; preview again.")
            registry = decode_registry(record.payload)
            if name != mapping_backup_name(record.payload):
                raise ValueError("Mapping backup filename does not match its bytes.")
            used += len(record.payload)
            records.append(MappingBackup(name, record, registry))
        # Recheck every selected and retained file before accepting this inventory.
        for backup in records:
            info = os.stat(backup.name, dir_fd=root, follow_symlinks=False)
            if (
                raw_file_identity(info) != backup.record.identity
                or not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_mode & 0o077
                or info.st_uid != os.getuid()
            ):
                raise ValueError("Mapping backup inventory changed; preview again.")
        after = os.fstat(root)
        if (before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError(
                "Memory directory changed during inventory; preview again."
            )
        return tuple(records), count - len(names)

    def _observe(
        self, handles: tuple[int, int]
    ) -> tuple[dict[str, object], tuple[MappingBackup, ...], RegistryFile | None]:
        root = handles[0]
        storage = self._storage_identity(handles)
        current = read_registry_file(root, REGISTRY_NAME)
        registry = None if current is None else decode_registry(current.payload)
        backups, ignored = self._inventory(root)
        if (
            read_registry_file(root, REGISTRY_NAME) != current
            or self._storage_identity(handles) != storage
        ):
            raise ValueError("Current registry or storage changed; preview again.")
        return (
            {
                "storage": storage,
                "current": None
                if current is None
                else {
                    "raw_sha256": digest(current.payload),
                    "file_identity": current.identity,
                    "registry": None
                    if registry is None
                    else registry.model_dump(mode="json"),
                },
                "ignored_entries": ignored,
                "backups": [backup.receipt() for backup in backups],
            },
            backups,
            current,
        )

    def retain(
        self,
        *,
        keep_newest: int,
        before_ns: int,
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        if type(keep_newest) is not int or not 0 <= keep_newest <= MAX_HISTORY_FILES:
            raise ValueError("--keep-newest must be between 0 and 128.")
        if type(before_ns) is not int or not 0 < before_ns < 2**63:
            raise ValueError("--before-ns must be positive and below 2**63.")
        if (
            expected_sha256 is not None
            and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise ValueError("Retention requires a lowercase SHA-256 preview hash.")
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Mapping retention requires existing private storage.")
            observation, backups, current = self._observe(handles)
            newest = {
                backup.name
                for backup in sorted(
                    backups, key=lambda b: (-b.record.identity["mtime_ns"], b.name)
                )[:keep_newest]
            }
            protected: list[dict[str, object]] = []
            eligible: list[MappingBackup] = []
            for backup in backups:
                reasons: list[str] = []
                if backup.name in newest:
                    reasons.append("keep-newest")
                if backup.record.identity["mtime_ns"] >= before_ns:
                    reasons.append("age-cutoff")
                if current is None:
                    reasons.append("no-current-registry")
                elif backup.record.payload == current.payload:
                    reasons.append("matches-current-registry")
                if reasons:
                    protected.append({"name": backup.name, "reasons": reasons})
                else:
                    eligible.append(backup)
            eligible.sort(key=lambda b: (b.record.identity["mtime_ns"], b.name))
            selected = eligible[:MAX_MAPPING_PRUNE]
            body: dict[str, object] = {
                "schema_version": 1,
                "action": "retain",
                "inventory": observation,
                "policy": {
                    "keep_newest": keep_newest,
                    "before_ns": before_ns,
                    "newest_order": "mtime_ns descending, filename ascending",
                    "prune_order": "mtime_ns ascending, filename ascending",
                    "max_prune": MAX_MAPPING_PRUNE,
                    "max_entries": MAX_HISTORY_ENTRIES,
                    "max_backups": MAX_HISTORY_FILES,
                    "max_inventory_bytes": MAX_HISTORY_BYTES,
                    "max_file_bytes": REGISTRY_BYTES,
                },
                "protected": protected,
                "selected": [backup.name for backup in selected],
                "remaining_eligible": [
                    backup.name for backup in eligible[MAX_MAPPING_PRUNE:]
                ],
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
            if expected_sha256 != preview_hash:
                raise ValueError("Mapping retention changed; preview again.")
            try:
                for backup in selected:
                    expected = {
                        **observation,
                        "backups": [
                            b.receipt() for b in backups if b.name not in removed
                        ],
                    }
                    actual, _, _ = self._observe(handles)
                    if actual != expected:
                        raise ValueError(
                            "Mapping retention inventory changed during apply."
                        )
                    os.unlink(backup.name, dir_fd=handles[0])
                    removed.append(backup.name)
                    os.fsync(handles[0])
                    synced.append(backup.name)
            except (OSError, ValueError) as error:
                receipt["status"] = "incomplete"
                raise MappingRetentionError(receipt) from error
            receipt["status"] = "completed"
            return receipt


def run_command(args: argparse.Namespace) -> int:
    if any(
        value is not None
        for value in (
            args.workspace,
            args.target,
            args.file_name,
            args.input,
            args.mode,
            args.on_conflict,
        )
    ):
        raise ValueError("retain accepts retention policy and storage options only.")
    if args.keep_newest is None or args.before_ns is None:
        raise ValueError("retain requires --keep-newest and --before-ns.")
    if args.apply != (args.expected_sha256 is not None):
        raise ValueError("Use --apply and --expected-sha256 together.")
    notice = None
    try:
        receipt = MemoryMappingRetention(args.memory_storage).retain(
            keep_newest=args.keep_newest,
            before_ns=args.before_ns,
            expected_sha256=args.expected_sha256,
        )
    except MappingRetentionError as error:
        receipt, notice = error.receipt, str(error)
    print(
        json.dumps(
            {"type": "memory.project_mapping", **receipt},
            ensure_ascii=True,
            indent=None if args.json else 2,
        )
    )
    if notice is not None:
        raise ValueError(notice)
    return 0
