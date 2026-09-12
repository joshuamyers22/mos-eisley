"""Explicit, bounded inspection and recovery of private mapping registry files."""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Literal

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
from mos_eisley.core.models import canonical_bytes, digest

MAX_HISTORY_ENTRIES = 1024
MAX_HISTORY_FILES = 128
MAX_HISTORY_BYTES = 8 * 1024 * 1024
_ARTIFACT = re.compile(
    r"(?:mapping-backup-[0-9a-f]{64}\.json|\.memory-mappings-[0-9a-f]{32}\.tmp)"
)


class MappingRecoveryError(ValueError):
    def __init__(self, receipt: dict[str, object]) -> None:
        super().__init__(
            "Mapping maintenance stopped; inspect history and preview again."
        )
        self.receipt = receipt


def _registry(record: RegistryFile | None) -> MemoryMappingRegistry | None:
    if record is None:
        return None
    try:
        return decode_registry(record.payload)
    except ValueError:
        return None


def _describe(name: str, record: RegistryFile) -> dict[str, object]:
    registry = _registry(record)
    addressed = not name.startswith("mapping-backup-") or name == mapping_backup_name(
        record.payload
    )
    return {
        "file_name": name,
        "kind": "backup" if name.startswith("mapping-backup-") else "staging",
        "raw_sha256": digest(record.payload),
        "file_identity": record.identity,
        "canonical_owner_registry": registry is not None,
        "content_address_matches": addressed,
        "registry": None if registry is None else registry.model_dump(mode="json"),
    }


class MemoryMappingHistory(MemoryMappingStore):
    def history(self) -> dict[str, object]:
        with self._lock_handles() as handles:
            root = None if handles is None else handles[0]
            current = read_registry_file(root, REGISTRY_NAME)
            records: list[dict[str, object]] = []
            size = 0
            if root is not None:
                names: list[str] = []
                with os.scandir(root) as entries:
                    for count, entry in enumerate(entries, 1):
                        if count > MAX_HISTORY_ENTRIES:
                            raise ValueError(
                                "Mapping history inventory exceeds 1,024 entries."
                            )
                        if _ARTIFACT.fullmatch(entry.name):
                            names.append(entry.name)
                            if len(names) > MAX_HISTORY_FILES:
                                raise ValueError(
                                    "Mapping history exceeds 128 files; "
                                    "inspect exact names."
                                )
                for name in sorted(names):
                    record = read_registry_file(root, name)
                    if record is None:
                        raise ValueError("Mapping history changed; inspect again.")
                    size += len(record.payload)
                    if size > MAX_HISTORY_BYTES:
                        raise ValueError(
                            "Mapping history exceeds 8 MiB; inspect exact names."
                        )
                    records.append(_describe(name, record))
            registry = _registry(current)
            return {
                "storage": self._storage_identity(handles),
                "current": None
                if current is None
                else {
                    "raw_sha256": digest(current.payload),
                    "file_identity": current.identity,
                    "registry": None
                    if registry is None
                    else registry.model_dump(mode="json"),
                },
                "files": records,
                "ordering": "file_name",
                "automatic_recovery": False,
            }

    def maintain(
        self,
        action: Literal["restore", "discard"],
        file_name: str,
        *,
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        if action not in ("restore", "discard") or not _ARTIFACT.fullmatch(file_name):
            raise ValueError("Select an exact mapping backup or staging basename.")
        if (
            expected_sha256 is not None
            and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise ValueError(
                "Expected SHA-256 must be 64 lowercase hexadecimal characters."
            )
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Mapping storage does not exist.")
            root = handles[0]

            def inspect() -> tuple[
                dict[str, object], RegistryFile | None, MemoryMappingRegistry | None
            ]:
                candidate = read_registry_file(root, file_name)
                if candidate is None:
                    raise ValueError("Selected mapping file does not exist.")
                current = read_registry_file(root, REGISTRY_NAME)
                before = _registry(current)
                selected = _registry(candidate)
                after = None
                if action == "restore":
                    if selected is None or (
                        file_name.startswith("mapping-backup-")
                        and file_name != mapping_backup_name(candidate.payload)
                    ):
                        raise ValueError(
                            "Restore requires a canonical owner registry "
                            "with a matching backup name."
                        )
                    if current is not None:
                        try:
                            parsed = MemoryMappingRegistry.model_validate_json(
                                current.payload
                            )
                        except ValueError:
                            parsed = None
                        if parsed is not None and parsed.owner_uid != os.getuid():
                            raise ValueError(
                                "Cannot replace another owner's mapping registry."
                            )
                    # Recover all saved mappings with their original pins, never
                    # silently recapture a directory that was moved or replaced.
                    for item in selected.mappings:
                        item.workspace.selection()
                        item.target.selection()
                    after = MemoryMappingRegistry(
                        owner_uid=os.getuid(),
                        revision=max(
                            selected.revision, 0 if before is None else before.revision
                        )
                        + 1,
                        mappings=selected.mappings,
                    )
                    if len(canonical_bytes(after)) > REGISTRY_BYTES:
                        raise ValueError("Restored mapping registry exceeds 1 MiB.")
                elif selected is not None and before is None:
                    raise ValueError(
                        "Preserve valid recovery files while the current "
                        "registry is absent or invalid."
                    )
                body: dict[str, object] = {
                    "storage": self._storage_identity(handles),
                    "action": action,
                    "selected": {
                        **_describe(file_name, candidate),
                        **candidate.review(),
                    },
                    "current": None if current is None else current.review(),
                    "before": None
                    if before is None
                    else before.model_dump(mode="json"),
                    "after": None if after is None else after.model_dump(mode="json"),
                    "backup_name": (
                        mapping_backup_name(current.payload)
                        if current is not None and action == "restore"
                        else None
                    ),
                    "source_retained": action == "restore",
                }
                if (
                    read_registry_file(root, file_name) != candidate
                    or read_registry_file(root, REGISTRY_NAME) != current
                ):
                    raise ValueError("Mapping files changed; preview again.")
                return body, current, after

            body, current, after = inspect()
            preview_hash = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            )
            receipt: dict[str, object] = {
                **body,
                "preview_sha256": preview_hash,
                "status": "planned",
                "backup_synced": False,
                "published": False,
                "removed": False,
                "synced": False,
            }
            if expected_sha256 is None:
                return receipt
            if expected_sha256 != preview_hash:
                raise ValueError("Mapping maintenance changed; preview again.")

            def verify() -> None:
                if inspect()[0] != body:
                    raise ValueError("Mapping maintenance changed; preview again.")

            verify()
            try:
                if action == "restore":
                    assert after is not None
                    self._publish(root, current, after, verify, receipt)
                else:
                    os.unlink(file_name, dir_fd=root)
                    receipt["removed"] = True
                    os.fsync(root)
                    receipt["synced"] = True
            except (OSError, ValueError, RuntimeError) as error:
                receipt["status"] = "incomplete"
                raise MappingRecoveryError(receipt) from error
            receipt["status"] = "completed"
            return receipt


def run_command(args: argparse.Namespace) -> int:
    if args.workspace is not None or args.target is not None:
        raise ValueError("Mapping history/recovery does not accept -C or --target.")
    if args.apply != (args.expected_sha256 is not None):
        raise ValueError("Use --apply and --expected-sha256 together.")
    store = MemoryMappingHistory(args.memory_storage)
    notice = None
    if args.action == "history":
        if args.file_name is not None or args.apply:
            raise ValueError("history accepts only --memory-storage and --json.")
        receipt = store.history()
    else:
        if args.file_name is None:
            raise ValueError("restore/discard requires --file-name.")
        try:
            receipt = store.maintain(
                args.action, args.file_name, expected_sha256=args.expected_sha256
            )
        except MappingRecoveryError as error:
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
