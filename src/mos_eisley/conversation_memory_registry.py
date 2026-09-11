"""Reviewed, exact-workspace mappings used only when starting fresh sessions."""

from __future__ import annotations

import argparse
import json
import os
import stat
from contextlib import suppress
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
from mos_eisley.core.models import Contract, canonical_bytes, digest

REGISTRY_NAME = "project-mappings.json"
REGISTRY_BYTES = 1024 * 1024
MAX_MAPPINGS = 128


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
        empty = MemoryMappingRegistry(owner_uid=os.getuid())
        if root is None:
            return empty
        try:
            fd = os.open(
                REGISTRY_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root
            )
        except FileNotFoundError:
            return empty
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
        registry = MemoryMappingRegistry.model_validate_json(payload)
        if registry.owner_uid != os.getuid() or canonical_bytes(registry) != payload:
            raise ValueError(
                "Saved memory mappings require canonical owner-scoped data."
            )
        return registry

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
            before = self._read(root)
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
                "action": "remove" if target is None else "set",
                "workspace": identity,
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
            if expected_sha256 is not None:
                assert root is not None
                temporary = ".memory-mappings-" + uuid4().hex + ".tmp"
                fd = os.open(
                    temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=root
                )
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    self._storage_identity(handles)
                    if self._read(root) != before:
                        raise ValueError(
                            "Saved memory mappings changed; preview again."
                        )
                    if replacement is not None:
                        replacement.workspace.selection()
                        replacement.target.selection()
                    os.replace(
                        temporary, REGISTRY_NAME, src_dir_fd=root, dst_dir_fd=root
                    )
                    os.fsync(root)
                finally:
                    with suppress(FileNotFoundError):
                        os.unlink(temporary, dir_fd=root)
            return {
                **body,
                "preview_sha256": preview_hash,
                "applied": expected_sha256 is not None,
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
    command.add_argument("action", choices=("show", "set", "remove"))
    command.add_argument("-C", "--workspace", type=Path)
    command.add_argument("--target", type=Path)
    command.add_argument(
        "--memory-storage", type=Path, default=Path.home() / ".mos-eisley-memory"
    )
    command.add_argument("--apply", action="store_true")
    command.add_argument("--expected-sha256")
    command.add_argument("--json", action="store_true")


def run_command(args: argparse.Namespace) -> int:
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
