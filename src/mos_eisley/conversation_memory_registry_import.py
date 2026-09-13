"""Reviewed bulk mapping import with explicit conflict and replacement policies."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_directory import DirectorySelection, valid_path_text
from mos_eisley.conversation_memory_registry import (
    MAX_MAPPINGS,
    REGISTRY_BYTES,
    REGISTRY_NAME,
    MappedDirectory,
    MemoryMappingRegistry,
    MemoryMappingStore,
    RegistryFile,
    SavedMemoryMapping,
    decode_registry,
    mapping_backup_name,
    read_registry_file,
)
from mos_eisley.core.models import Contract, canonical_bytes, digest

ImportMode = Literal["merge", "replace"]
ConflictPolicy = Literal["error", "keep", "replace"]


class ImportMapping(Contract):
    workspace: str
    target: str

    @model_validator(mode="after")
    def absolute_paths(self) -> Self:
        for value in (self.workspace, self.target):
            if not Path(value).is_absolute() or not valid_path_text(value):
                raise ValueError(
                    "Import paths must be absolute, printable and "
                    "at most 4,096 UTF-8 bytes."
                )
        return self


class MappingImportManifest(Contract):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    owner_uid: Annotated[int, Field(ge=0)]
    mappings: Annotated[tuple[ImportMapping, ...], Field(max_length=MAX_MAPPINGS)]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Mapping import contains a duplicate JSON key.")
        result[key] = value
    return result


def read_import_manifest(path: Path) -> tuple[MappingImportManifest, dict[str, object]]:
    """Pin the explicit parent and read one bounded private regular input file."""
    supplied = path.expanduser().absolute()
    if not valid_path_text(str(supplied)):
        raise ValueError(
            "Import requires a printable input path of at most 4,096 UTF-8 bytes."
        )
    parent = DirectorySelection.inspect(supplied.parent)
    root = os.open(parent.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        held = os.fstat(root)
        if (held.st_dev, held.st_ino) != (parent.device, parent.inode):
            raise ValueError("Import input directory changed; preview again.")
        record = read_registry_file(root, supplied.name)
        if record is None:
            raise ValueError("Import input file does not exist.")
        try:
            json.loads(record.payload, object_pairs_hook=_unique_object)
        except RecursionError:
            raise ValueError("Mapping import JSON is nested too deeply.") from None
        manifest = MappingImportManifest.model_validate_json(record.payload)
        if manifest.owner_uid != os.getuid():
            raise ValueError("Import manifest must belong to the current owner.")
        parent.verify()
        if DirectorySelection.inspect(supplied.parent) != parent:
            raise ValueError("Import input directory alias changed; preview again.")
        if read_registry_file(root, supplied.name) != record:
            raise ValueError("Import input file changed; preview again.")
        return manifest, {
            "supplied_path": str(supplied),
            "canonical_path": str(parent.path / supplied.name),
            "parent": {
                "path": str(parent.path),
                "device": parent.device,
                "inode": parent.inode,
            },
            **record.review(),
        }
    finally:
        os.close(root)


class MappingImportError(ValueError):
    def __init__(self, receipt: dict[str, object]) -> None:
        super().__init__(
            "Mapping import stopped; inspect current mappings and history, "
            "then preview again."
        )
        self.receipt = receipt


class MemoryMappingImporter(MemoryMappingStore):
    def _inspect_import(
        self,
        handles: tuple[int, int] | None,
        path: Path,
        mode: ImportMode,
        on_conflict: ConflictPolicy,
    ) -> tuple[dict[str, object], RegistryFile | None, MemoryMappingRegistry | None]:
        manifest, input_record = read_import_manifest(path)
        root = None if handles is None else handles[0]
        current = read_registry_file(root, REGISTRY_NAME)
        before = (
            MemoryMappingRegistry(owner_uid=os.getuid())
            if current is None
            else decode_registry(current.payload)
        )
        incoming: dict[str, SavedMemoryMapping] = {}
        for entry in manifest.mappings:
            selected = SavedMemoryMapping(
                workspace=MappedDirectory.inspect(Path(entry.workspace)),
                target=MappedDirectory.inspect(Path(entry.target)),
            )
            key = selected.workspace.path
            if key in incoming:
                raise ValueError(
                    "Import workspaces must be unique "
                    "after resolving directory aliases."
                )
            incoming[key] = selected
        existing = {entry.workspace.path: entry for entry in before.mappings}
        result = dict(existing) if mode == "merge" else {}
        changes: list[dict[str, object]] = []
        conflicts = 0
        for key, selected in sorted(incoming.items()):
            previous = existing.get(key)
            conflict = previous is not None and previous != selected
            if conflict:
                conflicts += 1
            keep = conflict and mode == "merge" and on_conflict in {"keep", "error"}
            if not keep:
                result[key] = selected
            disposition = (
                "conflict"
                if keep and on_conflict == "error"
                else "kept"
                if keep
                else "added"
                if previous is None
                else "unchanged"
                if previous == selected
                else "replaced"
            )
            changes.append(
                {
                    "workspace": key,
                    "disposition": disposition,
                    "before": None
                    if previous is None
                    else previous.model_dump(mode="json"),
                    "incoming": selected.model_dump(mode="json"),
                }
            )
        if mode == "replace":
            for key, previous in sorted(existing.items()):
                if key not in incoming:
                    changes.append(
                        {
                            "workspace": key,
                            "disposition": "removed",
                            "before": previous.model_dump(mode="json"),
                            "incoming": None,
                        }
                    )
        blocked = mode == "merge" and on_conflict == "error" and conflicts > 0
        after = (
            None
            if blocked
            else MemoryMappingRegistry(
                owner_uid=os.getuid(),
                revision=before.revision + 1,
                mappings=tuple(result[key] for key in sorted(result)),
            )
        )
        if after is not None and len(canonical_bytes(after)) > REGISTRY_BYTES:
            raise ValueError("Imported mapping registry exceeds 1 MiB.")
        body: dict[str, object] = {
            "action": "import",
            "mode": mode,
            "on_conflict": on_conflict,
            "storage": str(self.root.resolve()),
            # Bootstrap binds logical configuration, like reviewed set/remove.
            "storage_identity": self._storage_identity(handles)
            if current is not None
            else None,
            "input": input_record,
            "manifest": manifest.model_dump(mode="json"),
            "current": None if current is None else current.review(),
            "before": before.model_dump(mode="json"),
            "after": None if after is None else after.model_dump(mode="json"),
            "changes": changes,
            "conflict_count": conflicts,
            "can_apply": not blocked,
            "backup_name": None
            if current is None
            else mapping_backup_name(current.payload),
        }
        self._storage_identity(handles)
        if read_registry_file(root, REGISTRY_NAME) != current:
            raise ValueError("Saved mappings changed; preview import again.")
        # Parsing and directory inspection can take time; verify the input again.
        if read_import_manifest(path)[1] != input_record:
            raise ValueError("Import input changed; preview again.")
        for selected in incoming.values():
            selected.workspace.selection()
            selected.target.selection()
        return body, current, after

    def import_mappings(
        self,
        path: Path,
        *,
        mode: ImportMode = "merge",
        on_conflict: ConflictPolicy = "error",
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        if mode not in ("merge", "replace") or on_conflict not in (
            "error",
            "keep",
            "replace",
        ):
            raise ValueError("Select a supported import mode and conflict policy.")
        if mode == "replace" and on_conflict != "error":
            raise ValueError("--on-conflict applies only to merge mode.")
        if expected_sha256 is not None:
            if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
                raise ValueError("Expected SHA-256 must be lowercase hexadecimal.")
            preview = self.import_mappings(path, mode=mode, on_conflict=on_conflict)
            if preview["preview_sha256"] != expected_sha256:
                raise ValueError("Import changed; preview again.")
            if not preview["can_apply"]:
                raise ValueError(
                    "Import has conflicts; select a policy and preview again."
                )
        with self._lock_handles(write=expected_sha256 is not None) as handles:
            body, current, after = self._inspect_import(
                handles, path, mode, on_conflict
            )
            preview_hash = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            )
            receipt: dict[str, object] = {
                **body,
                "preview_sha256": preview_hash,
                "status": "planned" if body["can_apply"] else "conflicts",
                "backup_synced": False,
                "published": False,
                "synced": False,
            }
            if expected_sha256 is None:
                return receipt
            if expected_sha256 != preview_hash or after is None:
                raise ValueError("Import changed; preview again.")
            assert handles is not None

            def verify() -> None:
                if self._inspect_import(handles, path, mode, on_conflict)[0] != body:
                    raise ValueError("Import changed; preview again.")

            try:
                self._publish(handles[0], current, after, verify, receipt)
            except (OSError, ValueError, RuntimeError) as error:
                receipt["status"] = "incomplete"
                raise MappingImportError(receipt) from error
            receipt["status"] = "completed"
            return receipt


def run_command(args: argparse.Namespace) -> int:
    if (
        args.workspace is not None
        or args.target is not None
        or args.file_name is not None
    ):
        raise ValueError("import accepts --input, not -C, --target or --file-name.")
    if args.input is None or args.apply != (args.expected_sha256 is not None):
        raise ValueError(
            "import requires --input; use --apply and --expected-sha256 together."
        )
    notice = None
    try:
        receipt = MemoryMappingImporter(args.memory_storage).import_mappings(
            args.input,
            mode=args.mode or "merge",
            on_conflict=args.on_conflict or "error",
            expected_sha256=args.expected_sha256,
        )
    except MappingImportError as error:
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
