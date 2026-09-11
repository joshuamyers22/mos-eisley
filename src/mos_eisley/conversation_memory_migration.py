"""Reviewed project-memory copying, relocation, collision resolution and recovery."""

import json
import os
import re
import stat
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from mos_eisley.conversation_directory import DirectorySelection
from mos_eisley.conversation_memory import (
    RECORD_BYTES,
    MemoryDocument,
    MemorySnapshot,
    MemoryStore,
)
from mos_eisley.conversation_memory_identity import RelocationSource
from mos_eisley.conversation_memory_project import select_memory_project
from mos_eisley.core.models import canonical_bytes, digest

Resolution = Literal["keep-target", "use-source", "append-source", "use-text"]


def _identity(info: os.stat_result) -> dict[str, int]:
    return {"device": info.st_dev, "inode": info.st_ino}


def _directory(selection: DirectorySelection | RelocationSource) -> dict[str, object]:
    if isinstance(selection, RelocationSource):
        return selection.receipt()
    return {
        "path": str(selection.path),
        "device": selection.device,
        "inode": selection.inode,
    }


class MemoryMigrationStore(MemoryStore):
    """Filesystem primitives shared by explicit memory maintenance commands."""

    def _resolution_backup(
        self, root: int, name: str, expected: MemorySnapshot, *, sync: bool = False
    ) -> bool:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        except FileNotFoundError:
            return False
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_nlink != 1
                or stream.read(RECORD_BYTES + 1) != canonical_bytes(expected)
            ):
                raise ValueError(
                    "Resolution backup is unsafe or changed; inspect storage."
                )
            if sync:
                os.fsync(stream.fileno())
        return True

    def resolve(
        self,
        target: "MemoryMigrationStore",
        source_directory: DirectorySelection | RelocationSource,
        target_directory: DirectorySelection,
        strategy: Resolution,
        text: str | None,
        expected_sha256: str | None,
        *,
        operation: str = "resolve-project-memory",
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError(
                    "Resolution requires existing source and target documents."
                )
            root = handles[0]

            def inspect() -> dict[str, object]:
                source_directory.verify()
                target_directory.verify()
                storage = self._storage_identity(handles)
                source, destination = (
                    self._read(root, "project"),
                    target._read(root, "project"),
                )
                if source is None or destination is None:
                    raise ValueError(
                        "Resolution requires existing source and target documents."
                    )
                identities: dict[str, object] = {}
                for label, store in (("source", self), ("target", target)):
                    info = os.stat(
                        store.path("project").name, dir_fd=root, follow_symlinks=False
                    )
                    identities[label] = {
                        **_identity(info),
                        "ctime_ns": info.st_ctime_ns,
                    }
                return {
                    "storage": storage,
                    "source_directory": _directory(source_directory),
                    "target_directory": _directory(target_directory),
                    "source": source.model_dump(mode="json"),
                    "target": destination.model_dump(mode="json"),
                    "record_identities": identities,
                }

            inspected = inspect()
            source = MemorySnapshot.model_validate_json(json.dumps(inspected["source"]))
            destination = MemorySnapshot.model_validate_json(
                json.dumps(inspected["target"])
            )
            content = destination.document.text
            if strategy == "use-source":
                content = source.document.text
            elif strategy == "append-source":
                content = "\n\n".join(
                    part for part in (content, source.document.text) if part
                )
            elif strategy == "use-text":
                assert text is not None
                content = text
            will_write = content != destination.document.text
            proposed = MemoryDocument.model_validate(
                {
                    **destination.document.model_dump(),
                    "text": content,
                    "revision": destination.document.revision + int(will_write),
                }
            )
            backup_name = (
                "resolution-backup-" + digest(canonical_bytes(destination)) + ".json"
            )
            backup_exists = (
                self._resolution_backup(root, backup_name, destination)
                if will_write
                else False
            )
            body: dict[str, object] = {
                "schema_version": 1,
                "operation": operation,
                **inspected,
                "strategy": strategy,
                "proposed": proposed.model_dump(mode="json", exclude={"updated_at"}),
                "updated_at_policy": "apply-time" if will_write else "preserve",
                "will_write": will_write,
                "backup_path": str(self.root / backup_name) if will_write else None,
                "backup_exists": backup_exists,
            }
            preview_hash = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
            result = None
            if expected_sha256 is not None:
                if expected_sha256 != preview_hash:
                    raise ValueError("Memory resolution changed; preview it again.")

                def verify() -> None:
                    if inspect() != inspected:
                        raise ValueError("Memory resolution changed; preview it again.")

                verify()
                result = destination
                if will_write:
                    if not backup_exists:
                        self._publish_missing(root, backup_name, destination, verify)
                    if not self._resolution_backup(
                        root, backup_name, destination, sync=True
                    ):
                        raise ValueError(
                            "Resolution backup is missing; inspect storage."
                        )
                    os.fsync(root)
                    document = proposed.model_copy(
                        update={"updated_at": datetime.now(UTC)}
                    )
                    result = MemorySnapshot(
                        document=document, sha256=digest(canonical_bytes(document))
                    )

                    def verify_with_backup() -> None:
                        verify()
                        if not self._resolution_backup(root, backup_name, destination):
                            raise ValueError(
                                "Resolution backup is missing; inspect storage."
                            )

                    self._replace_resolution(
                        root, target.path("project").name, result, verify_with_backup
                    )
            return {
                **body,
                "preview_sha256": preview_hash,
                "applied": expected_sha256 is not None,
                "result": result.model_dump(mode="json") if result else None,
            }

    def _replace_resolution(
        self, root: int, name: str, snapshot: MemorySnapshot, verify: Callable[[], None]
    ) -> None:
        payload = canonical_bytes(snapshot)
        if len(payload) > RECORD_BYTES:
            raise ValueError("memory record exceeds byte limit")
        temporary = ".memory-resolution-" + uuid4().hex + ".tmp"
        fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=root
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            verify()
            os.replace(temporary, name, src_dir_fd=root, dst_dir_fd=root)
            os.fsync(root)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=root)

    def _recovery_record(
        self,
        root: int,
        temporary: str,
        target_sha256: str,
        *,
        record_name: str | None = None,
    ) -> tuple[MemorySnapshot, dict[str, int]]:
        record_name = record_name or self.path("project").name
        fd = os.open(
            record_name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=root,
        )
        try:
            with os.fdopen(fd, "rb", closefd=False) as stream:
                info = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or info.st_mode & 0o077
                    or info.st_nlink != 2
                ):
                    raise ValueError(
                        "Recovery requires a private target with exactly two links."
                    )
                identity = {**_identity(info), "ctime_ns": info.st_ctime_ns}
                for name in (record_name, temporary):
                    named = os.stat(name, dir_fd=root, follow_symlinks=False)
                    if (
                        _identity(named) != _identity(info)
                        or named.st_ctime_ns != info.st_ctime_ns
                        or named.st_nlink != 2
                    ):
                        raise ValueError(
                            "Recovery requires the exact target staging alias."
                        )
                payload = stream.read(RECORD_BYTES + 1)
                if len(payload) > RECORD_BYTES:
                    raise ValueError("memory record exceeds byte limit")
                snapshot = MemorySnapshot.model_validate_json(payload)
                if (
                    snapshot.sha256 != target_sha256
                    or snapshot.document.owner_uid != os.getuid()
                    or snapshot.document.scope != "project"
                    or snapshot.document.workspace != self.workspace
                    or payload != canonical_bytes(snapshot)
                    or os.fstat(stream.fileno()).st_ctime_ns != info.st_ctime_ns
                ):
                    raise ValueError(
                        "Recovery target does not match the approved copy."
                    )
        finally:
            os.close(fd)
        return snapshot, identity

    def recover(
        self,
        source_directory: DirectorySelection | RelocationSource,
        target_directory: DirectorySelection,
        temporary: str,
        target_sha256: str,
        expected_sha256: str | None,
        *,
        operation: str = "recover-project-memory-link",
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            if handles is None:
                raise ValueError("Recovery requires existing memory storage.")
            root = handles[0]

            def inspect() -> dict[str, object]:
                source_directory.verify()
                target_directory.verify()
                storage = self._storage_identity(handles)
                snapshot, identity = self._recovery_record(
                    root, temporary, target_sha256
                )
                return {
                    "schema_version": 1,
                    "operation": operation,
                    "storage": storage,
                    "source_directory": _directory(source_directory),
                    "target_directory": _directory(target_directory),
                    "target_path": str(self.path("project")),
                    "temporary_path": str(self.root / temporary),
                    "target": snapshot.model_dump(mode="json"),
                    "record_identity": identity,
                    "action": "remove-verified-temporary-alias",
                }

            body = inspect()
            preview_hash = digest(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
            if expected_sha256 is not None:
                if expected_sha256 != preview_hash or inspect() != body:
                    raise ValueError("Memory recovery changed; preview it again.")
                os.unlink(temporary, dir_fd=root)
                os.fsync(root)
                # Normal readers retain their single-link rule throughout recovery.
                recovered = self._read(root, "project")
                if recovered is None or recovered.sha256 != target_sha256:
                    raise ValueError("Recovery target changed; inspect storage again.")
            return {
                **body,
                "preview_sha256": preview_hash,
                "applied": expected_sha256 is not None,
            }

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
        target: "MemoryMigrationStore",
        source_directory: DirectorySelection | RelocationSource,
        target_directory: DirectorySelection,
        expected_sha256: str | None,
        *,
        operation: str = "copy-project-memory",
    ) -> dict[str, object]:
        with self._lock_handles(exclusive=expected_sha256 is not None) as handles:
            root = handles[0] if handles is not None else None
            source_directory.verify()
            target_directory.verify()
            storage = self._storage_identity(handles)
            source = self._read(root, "project")
            destination = target._read(root, "project")
            source_identity = self._project_record_identity(root)
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
                "operation": operation,
                "storage": storage,
                "source_directory": _directory(source_directory),
                "target_directory": _directory(target_directory),
                "source_path": str(self.path("project")),
                "source_record_identity": source_identity,
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
                        or self._project_record_identity(root) != source_identity
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

    def _project_record_identity(self, root: int | None) -> dict[str, int] | None:
        if root is None:
            return None
        try:
            info = os.stat(
                self.path("project").name, dir_fd=root, follow_symlinks=False
            )
        except FileNotFoundError:
            return None
        return {**_identity(info), "ctime_ns": info.st_ctime_ns}

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
    source = MemoryMigrationStore(storage, source_directory.path)
    target = MemoryMigrationStore(storage, target_directory.path)
    return source.migrate(target, source_directory, target_directory, expected_sha256)


def recover_memory_project(
    storage: Path,
    workspace: Path,
    project_root: Path,
    *,
    temporary_name: str,
    target_sha256: str,
    expected_sha256: str | None = None,
) -> dict[str, object]:
    """Inspect or remove one approved copy's exact interrupted-publication alias."""
    if re.fullmatch(r"\.memory-migration-[0-9a-f]{32}\.tmp", temporary_name) is None:
        raise ValueError("Recovery requires an exact migration temporary filename.")
    for value in (target_sha256, expected_sha256):
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("Recovery requires lowercase SHA-256 hashes.")
    source_directory = DirectorySelection.inspect(workspace)
    target_directory = select_memory_project(source_directory.path, project_root)
    if source_directory.path == target_directory.path:
        raise ValueError(
            "Recovery requires distinct workspace and project-root identities."
        )
    target = MemoryMigrationStore(storage, target_directory.path)
    return target.recover(
        source_directory,
        target_directory,
        temporary_name,
        target_sha256,
        expected_sha256,
    )


def _validate_resolution(strategy: Resolution, text: str | None) -> None:
    if strategy not in ("keep-target", "use-source", "append-source", "use-text"):
        raise ValueError("Choose an explicit memory resolution strategy.")
    if (strategy == "use-text") != (text is not None):
        raise ValueError(
            "Use --text only with --strategy use-text, including empty text."
        )


def resolve_memory_project(
    storage: Path,
    workspace: Path,
    project_root: Path,
    *,
    strategy: Resolution,
    text: str | None = None,
    expected_sha256: str | None = None,
) -> dict[str, object]:
    """Review a collision and preserve its old target before an explicit replacement."""
    _validate_resolution(strategy, text)
    if (
        expected_sha256 is not None
        and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
    ):
        raise ValueError("Resolution requires the SHA-256 from its preview.")
    source_directory = DirectorySelection.inspect(workspace)
    target_directory = select_memory_project(source_directory.path, project_root)
    if source_directory.path == target_directory.path:
        raise ValueError(
            "Resolution requires distinct workspace and project-root identities."
        )
    source = MemoryMigrationStore(storage, source_directory.path)
    target = MemoryMigrationStore(storage, target_directory.path)
    return source.resolve(
        target, source_directory, target_directory, strategy, text, expected_sha256
    )


class _RelocationStore(MemoryMigrationStore):
    def __init__(self, storage: Path, source: RelocationSource) -> None:
        # Only reviewed relocation can address a vanished identity. Ordinary stores
        # still require an existing directory, including when resuming sessions.
        source.verify()
        self.root = storage.absolute()
        self.workspace = str(source.path)


def relocate_memory_project(
    storage: Path,
    source_workspace: str,
    target_workspace: Path,
    *,
    expected_sha256: str | None = None,
    temporary_name: str | None = None,
    target_sha256: str | None = None,
    strategy: Resolution | None = None,
    text: str | None = None,
) -> dict[str, object]:
    """Review a historical identity's copy, collision resolution or copy recovery."""
    if strategy is not None:
        if temporary_name is not None or target_sha256 is not None:
            raise ValueError("Choose collision resolution or copy recovery, not both.")
        _validate_resolution(strategy, text)
    elif text is not None:
        raise ValueError(
            "Use --text only with --strategy use-text, including empty text."
        )
    if (temporary_name is None) != (target_sha256 is None):
        raise ValueError("Use --temporary-name and --target-sha256 together.")
    for value in (expected_sha256, target_sha256):
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("Relocation requires lowercase SHA-256 hashes.")
    if (
        temporary_name is not None
        and re.fullmatch(r"\.memory-migration-[0-9a-f]{32}\.tmp", temporary_name)
        is None
    ):
        raise ValueError("Recovery requires an exact migration temporary filename.")
    source_directory = RelocationSource.inspect(source_workspace)
    target_directory = DirectorySelection.inspect(target_workspace)
    if source_directory.path == target_directory.path:
        raise ValueError("Relocation requires distinct source and target identities.")
    target = MemoryMigrationStore(storage, target_directory.path)
    if temporary_name is not None:
        assert target_sha256 is not None
        return target.recover(
            source_directory,
            target_directory,
            temporary_name,
            target_sha256,
            expected_sha256,
            operation="recover-relocated-project-memory-link",
        )
    source = _RelocationStore(storage, source_directory)
    if strategy is not None:
        return source.resolve(
            target,
            source_directory,
            target_directory,
            strategy,
            text,
            expected_sha256,
            operation="resolve-relocated-project-memory",
        )
    return source.migrate(
        target,
        source_directory,
        target_directory,
        expected_sha256,
        operation="relocate-project-memory",
    )
