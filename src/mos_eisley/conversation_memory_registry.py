"""Reviewed, exact-workspace mappings used only when starting fresh sessions."""

from __future__ import annotations

import argparse
import base64
import json
import os
import stat
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import Field, model_validator

from mos_eisley.conversation_directory import (
    DirectorySelection,
    DirectorySelectionError,
)
from mos_eisley.conversation_memory import MemoryStorage
from mos_eisley.conversation_memory_project import memory_workspace
from mos_eisley.conversation_memory_raw import raw_file_identity
from mos_eisley.core.models import Contract, canonical_bytes, digest

REGISTRY_NAME = "project-mappings.json"
REGISTRY_BYTES = 1024 * 1024
MAX_MAPPINGS = 128


@dataclass(frozen=True)
class RegistryFile:
    payload: bytes
    identity: dict[str, int]

    def review(self) -> dict[str, object]:
        return {
            "raw_sha256": digest(self.payload),
            "raw_bytes_base64": base64.b64encode(self.payload).decode("ascii"),
            "file_identity": self.identity,
        }


def read_registry_file(root: int | None, name: str) -> RegistryFile | None:
    if root is None:
        return None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
        ):
            raise ValueError(
                "Saved mappings require a private single-link regular file."
            )
        payload = stream.read(REGISTRY_BYTES + 1)
        if len(payload) > REGISTRY_BYTES:
            raise ValueError("Saved memory mapping registry exceeds 1 MiB.")
        for current in (
            os.fstat(stream.fileno()),
            os.stat(name, dir_fd=root, follow_symlinks=False),
        ):
            if raw_file_identity(current) != raw_file_identity(info):
                raise ValueError("Saved mapping file changed; preview again.")
            if current.st_nlink != 1 or current.st_mode != info.st_mode:
                raise ValueError("Saved mapping file permissions changed.")
    return RegistryFile(payload, raw_file_identity(info))


def decode_registry(payload: bytes) -> MemoryMappingRegistry:
    registry = MemoryMappingRegistry.model_validate_json(payload)
    if registry.owner_uid != os.getuid() or canonical_bytes(registry) != payload:
        raise ValueError("Saved memory mappings require canonical owner-scoped data.")
    return registry


def mapping_backup_name(payload: bytes) -> str:
    return "mapping-backup-" + digest(payload) + ".json"


class MappedDirectory(Contract):
    path: str
    device: Annotated[int, Field(ge=0)]
    inode: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def canonical_path(self) -> Self:
        memory_workspace(self.path, None, self.path)
        return self

    @classmethod
    def inspect(cls, path: Path) -> MappedDirectory:
        selected = DirectorySelection.inspect(path)
        return cls(
            path=str(selected.path), device=selected.device, inode=selected.inode
        )

    def selection(self) -> DirectorySelection:
        selected = DirectorySelection(Path(self.path), self.device, self.inode)
        selected.verify()
        return selected


class SavedMemoryMapping(Contract):
    workspace: MappedDirectory
    target: MappedDirectory


class MemoryMappingRegistry(Contract):
    schema_version: Literal[1] = 1
    owner_uid: Annotated[int, Field(ge=0)]
    revision: Annotated[int, Field(ge=0)] = 0
    mappings: Annotated[
        tuple[SavedMemoryMapping, ...], Field(max_length=MAX_MAPPINGS)
    ] = ()

    @model_validator(mode="after")
    def ordered_unique(self) -> Self:
        paths = tuple(item.workspace.path for item in self.mappings)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("Saved memory mappings require unique sorted workspaces.")
        return self


class MemoryMappingStore(MemoryStorage):
    def _read(self, root: int | None) -> MemoryMappingRegistry:
        record = read_registry_file(root, REGISTRY_NAME)
        return (
            MemoryMappingRegistry(owner_uid=os.getuid())
            if record is None
            else decode_registry(record.payload)
        )

    def _backup(self, root: int, record: RegistryFile) -> RegistryFile:
        """Flush the exact previous bytes before making a replacement visible."""
        name = mapping_backup_name(record.payload)
        try:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=root,
            )
        except FileExistsError:
            existing = read_registry_file(root, name)
            if existing is None or existing.payload != record.payload:
                raise ValueError(
                    "Mapping backup is incomplete or changed; review it first."
                ) from None
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
            try:
                if raw_file_identity(os.fstat(fd)) != existing.identity:
                    raise ValueError("Mapping backup changed; preview again.")
                os.fsync(fd)
                synced_identity = raw_file_identity(os.fstat(fd))
            finally:
                os.close(fd)
        else:
            # An interrupted write may leave an incomplete private backup. Never
            # overwrite it on retry; explicit history/discard exposes those bytes.
            with os.fdopen(fd, "wb") as stream:
                stream.write(record.payload)
                stream.flush()
                os.fsync(stream.fileno())
                synced_identity = raw_file_identity(os.fstat(stream.fileno()))
        os.fsync(root)
        existing = read_registry_file(root, name)
        if (
            existing is None
            or existing.payload != record.payload
            or existing.identity != synced_identity
        ):
            raise ValueError("Mapping backup changed before publication.")
        return existing

    def _publish(
        self,
        root: int,
        before: RegistryFile | None,
        after: MemoryMappingRegistry,
        verify: Callable[[], None],
        progress: dict[str, object],
    ) -> None:
        payload = canonical_bytes(after)
        if len(payload) > REGISTRY_BYTES:
            raise ValueError("Saved memory mapping registry exceeds 1 MiB.")
        verify()
        backup = None
        if before is not None:
            backup = self._backup(root, before)
            progress["backup_synced"] = True
        verify()
        temporary = ".memory-mappings-" + uuid4().hex + ".tmp"
        fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=root
        )
        created = os.fstat(fd)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            verify()
            if before is not None:
                retained = read_registry_file(root, mapping_backup_name(before.payload))
                if retained != backup:
                    raise ValueError("Mapping backup changed before publication.")
            staged = read_registry_file(root, temporary)
            if (
                staged is None
                or staged.payload != payload
                or staged.identity["device"] != created.st_dev
                or staged.identity["inode"] != created.st_ino
            ):
                raise ValueError("Staged mapping registry changed before publication.")
            os.replace(temporary, REGISTRY_NAME, src_dir_fd=root, dst_dir_fd=root)
            progress["published"] = True
            os.fsync(root)
            progress["synced"] = True
        finally:
            with suppress(FileNotFoundError):
                named = os.stat(temporary, dir_fd=root, follow_symlinks=False)
                if (named.st_dev, named.st_ino) == (created.st_dev, created.st_ino):
                    os.unlink(temporary, dir_fd=root)

    def read(self) -> MemoryMappingRegistry:
        with self._lock_handles() as handles:
            registry = self._read(None if handles is None else handles[0])
            self._storage_identity(handles)
            return registry

    def change(
        self,
        workspace: Path,
        target: Path | None,
        *,
        expected_sha256: str | None = None,
    ) -> dict[str, object]:
        if expected_sha256 is not None:
            preview = self.change(workspace, target)
            if expected_sha256 != preview["preview_sha256"]:
                raise ValueError("Saved memory mappings changed; preview again.")
        # Removal accepts an exact saved identity, even after its directory vanished.
        if target is None:
            identity = str(workspace)
            memory_workspace(identity, None, identity)
            replacement = None
        else:
            replacement = SavedMemoryMapping(
                workspace=MappedDirectory.inspect(workspace),
                target=MappedDirectory.inspect(target),
            )
            identity = replacement.workspace.path
        with self._lock_handles(write=expected_sha256 is not None) as handles:
            root = None if handles is None else handles[0]
            before_file = read_registry_file(root, REGISTRY_NAME)
            before = (
                MemoryMappingRegistry(owner_uid=os.getuid())
                if before_file is None
                else decode_registry(before_file.payload)
            )
            previous = next(
                (item for item in before.mappings if item.workspace.path == identity),
                None,
            )
            if target is None and previous is None:
                raise ValueError("No saved memory mapping for that exact workspace.")
            entries = [
                item for item in before.mappings if item.workspace.path != identity
            ]
            if replacement is not None:
                entries.append(replacement)
            after = MemoryMappingRegistry(
                owner_uid=os.getuid(),
                revision=before.revision + 1,
                mappings=tuple(sorted(entries, key=lambda item: item.workspace.path)),
            )
            payload = canonical_bytes(after)
            if len(payload) > REGISTRY_BYTES:
                raise ValueError("Saved memory mapping registry exceeds 1 MiB.")
            # Bind the logical storage location and the entire before/after state.
            # Bootstrap may create its private root/lock after a read-only preview.
            body: dict[str, object] = {
                "storage": str(self.root.resolve()),
                "storage_identity": (
                    self._storage_identity(handles) if before_file is not None else None
                ),
                "action": "remove" if target is None else "set",
                "workspace": identity,
                "before_file": None if before_file is None else before_file.identity,
                "backup_name": (
                    None
                    if before_file is None
                    else mapping_backup_name(before_file.payload)
                ),
                "before": before.model_dump(mode="json"),
                "after": after.model_dump(mode="json"),
            }
            preview_hash = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            )
            if expected_sha256 is not None and expected_sha256 != preview_hash:
                raise ValueError("Saved memory mappings changed; preview again.")
            if replacement is not None:
                replacement.workspace.selection()
                replacement.target.selection()
            self._storage_identity(handles)
            progress: dict[str, object] = {
                "backup_synced": False,
                "published": False,
                "synced": False,
            }
            if expected_sha256 is not None:
                assert root is not None

                def verify() -> None:
                    self._storage_identity(handles)
                    if read_registry_file(root, REGISTRY_NAME) != before_file:
                        raise ValueError(
                            "Saved memory mappings changed; preview again."
                        )
                    if replacement is not None:
                        replacement.workspace.selection()
                        replacement.target.selection()

                self._publish(root, before_file, after, verify, progress)
            return {
                **body,
                "preview_sha256": preview_hash,
                "applied": expected_sha256 is not None,
                **progress,
            }


class MemoryMappingResolver:
    """Capture one registry snapshot on first preview; retain it through handoff."""

    def __init__(self, storage: Path, *, disabled: bool = False) -> None:
        self.store = MemoryMappingStore(storage)
        self.disabled = disabled
        self.registry: MemoryMappingRegistry | None = None

    def resolve(self, workspace: Path) -> DirectorySelection | None:
        if self.disabled:
            return None
        try:
            if self.registry is None:
                self.registry = self.store.read()
            selected = DirectorySelection.inspect(workspace)
            for item in self.registry.mappings:
                if item.workspace.path == str(selected.path):
                    if item.workspace.selection() != selected:
                        raise ValueError("Mapped workspace changed.")
                    return item.target.selection()
            return None
        except (OSError, ValueError, RuntimeError):
            raise DirectorySelectionError(
                "Saved memory mapping unavailable or changed. Review it with "
                "mos memory-project-mapping, or use --memory-project-local."
            ) from None


def add_command(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "action",
        choices=("show", "set", "remove", "history", "restore", "discard", "import"),
    )
    command.add_argument("-C", "--workspace", type=Path)
    command.add_argument("--target", type=Path)
    command.add_argument("--file-name")
    command.add_argument("--input", type=Path)
    command.add_argument("--mode", choices=("merge", "replace"))
    command.add_argument("--on-conflict", choices=("error", "keep", "replace"))
    command.add_argument(
        "--memory-storage", type=Path, default=Path.home() / ".mos-eisley-memory"
    )
    command.add_argument("--apply", action="store_true")
    command.add_argument("--expected-sha256")
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
    if args.action == "import":
        from mos_eisley.conversation_memory_registry_import import (
            run_command as import_mapping,
        )

        return import_mapping(args)
    if args.input is not None or args.mode is not None or args.on_conflict is not None:
        raise ValueError("--input, --mode and --on-conflict are only valid for import.")
    if args.action in {"history", "restore", "discard"}:
        from mos_eisley.conversation_memory_registry_history import (
            run_command as recover,
        )

        return recover(args)
    if args.file_name is not None:
        raise ValueError("--file-name is only valid for restore/discard.")
    store = MemoryMappingStore(args.memory_storage)
    if args.action == "show":
        if (
            args.workspace is not None
            or args.target is not None
            or args.apply
            or args.expected_sha256
        ):
            raise ValueError("show accepts only --memory-storage and --json.")
        receipt: dict[str, object] = {
            "storage": str(store.root.resolve()),
            "registry": store.read().model_dump(mode="json"),
        }
    else:
        if args.workspace is None or (args.action == "set") != (
            args.target is not None
        ):
            raise ValueError("set requires -C and --target; remove requires only -C.")
        if args.apply != (args.expected_sha256 is not None):
            raise ValueError("Use --apply and --expected-sha256 together.")
        receipt = store.change(
            args.workspace, args.target, expected_sha256=args.expected_sha256
        )
    print(
        json.dumps(
            {"type": "memory.project_mapping", **receipt},
            ensure_ascii=True,
            indent=None if args.json else 2,
        )
    )
    return 0
