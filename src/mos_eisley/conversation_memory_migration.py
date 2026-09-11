"""Preview-bound, source-preserving project memory copies to absent targets."""

import json
import os
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from mos_eisley.conversation_directory import DirectorySelection
from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot, MemoryStore
from mos_eisley.conversation_memory_project import select_memory_project
from mos_eisley.core.models import canonical_bytes, digest


def _identity(info: os.stat_result) -> dict[str, int]:
    return {"device": info.st_dev, "inode": info.st_ino}


def _directory(selection: DirectorySelection) -> dict[str, object]:
    return {
        "path": str(selection.path),
        "device": selection.device,
        "inode": selection.inode,
    }


class _MigrationStore(MemoryStore):
    def _storage_identity(self, handles: tuple[int, int] | None) -> dict[str, object]:
        if handles is None:
            return {"path": str(self.root), "exists": False}
        root, lock_fd = handles
        held = os.fstat(root)
        named = os.stat(self.root, follow_symlinks=False)
        if _identity(held) != _identity(named):
            raise ValueError("Memory storage changed; preview the migration again.")
        lock = os.stat("memory.lock", dir_fd=root, follow_symlinks=False)
        if _identity(lock) != _identity(os.fstat(lock_fd)):
            raise ValueError("Memory lock changed; preview the migration again.")
        if (
            held.st_uid != os.getuid()
            or held.st_mode & 0o077
            or lock.st_uid != os.getuid()
            or lock.st_mode & 0o077
            or lock.st_nlink != 1
        ):
            raise ValueError("memory storage must be private and owned by this user")
        return {
            "path": str(self.root),
            "canonical_path": str(self.root.resolve(strict=True)),
            "exists": True,
            **_identity(held),
            "lock": _identity(lock),
        }

    def migrate(
        self,
        target: "_MigrationStore",
        source_directory: DirectorySelection,
        target_directory: DirectorySelection,
        expected_sha256: str | None,
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            root = handles[0] if handles is not None else None
            source_directory.verify()
            target_directory.verify()
            storage = self._storage_identity(handles)
            source = self._read(root, "project")
            destination = target._read(root, "project")
            status = (
                "same-identity"
                if self.workspace == target.workspace
                else "collision"
                if source is not None and destination is not None
                else "source-only"
                if source is not None
                else "target-only"
                if destination is not None
                else "empty"
            )
            proposed = None
            if status == "source-only" and source is not None:
                document = source.document.model_copy(
                    update={"workspace": target.workspace, "revision": 1}
                )
                proposed = MemorySnapshot(
                    document=document, sha256=digest(canonical_bytes(document))
                )
            body: dict[str, object] = {
                "schema_version": 1,
                "operation": "copy-project-memory",
                "storage": storage,
                "source_directory": _directory(source_directory),
                "target_directory": _directory(target_directory),
                "source_path": str(self.path("project")),
                "target_path": str(target.path("project")),
                "source": source.model_dump(mode="json") if source else None,
                "target": destination.model_dump(mode="json") if destination else None,
                "proposed": proposed.model_dump(mode="json") if proposed else None,
                "status": status,
                "can_apply": proposed is not None,
            }
            preview_hash = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
            if expected_sha256 is not None:
                if expected_sha256 != preview_hash:
                    raise ValueError("Memory migration changed; preview it again.")
                if proposed is None or root is None:
                    raise ValueError(
                        "Migration requires a source and an absent target."
                    )

                def verify() -> None:
                    source_directory.verify()
                    target_directory.verify()
                    if (
                        self._storage_identity(handles) != storage
                        or self._read(root, "project") != source
                        or target._read(root, "project") is not None
                    ):
                        raise ValueError("Memory migration changed; preview it again.")

                self._publish_missing(
                    root, target.path("project").name, proposed, verify
                )
            return {
                **body,
                "preview_sha256": preview_hash,
                "applied": expected_sha256 is not None,
            }

    def _publish_missing(
        self, root: int, name: str, snapshot: MemorySnapshot, verify: Callable[[], None]
    ) -> None:
        payload = canonical_bytes(snapshot)
        if len(payload) > RECORD_BYTES:
            raise ValueError("memory record exceeds byte limit")
        temporary = ".memory-migration-" + uuid4().hex + ".tmp"
        fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=root
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            verify()
            # Linking an already durable file is atomic and cannot replace a target.
            os.link(
                temporary,
                name,
                src_dir_fd=root,
                dst_dir_fd=root,
                follow_symlinks=False,
            )
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=root)
        # An error here can mean the target was published. Never delete or retry it.
        os.fsync(root)


def migrate_memory_project(
    storage: Path,
    workspace: Path,
    project_root: Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, object]:
    """Without an expected hash, inspect only; with one, copy the exact proposal."""
    if expected_sha256 is not None and (
        len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ValueError(
            "Migration requires the SHA-256 from a fresh migration preview."
        )
    source_directory = DirectorySelection.inspect(workspace)
    target_directory = select_memory_project(source_directory.path, project_root)
    source = _MigrationStore(storage, source_directory.path)
    target = _MigrationStore(storage, target_directory.path)
    return source.migrate(target, source_directory, target_directory, expected_sha256)
