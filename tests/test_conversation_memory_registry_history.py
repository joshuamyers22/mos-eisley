"""Mapping backup durability, exact recovery, and filesystem isolation boundaries."""

import base64
import fcntl
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_directory import DirectorySelectionError
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_registry import (
    REGISTRY_BYTES,
    REGISTRY_NAME,
    MemoryMappingResolver,
    MemoryMappingStore,
    mapping_backup_name,
)
from mos_eisley.conversation_memory_registry_history import (
    MappingRecoveryError,
    MemoryMappingHistory,
)
from mos_eisley.core.models import canonical_bytes, digest


def data(value: object) -> Any:
    """Exercise the same JSON receipt contract presented by the CLI."""
    return json.loads(json.dumps(value))


class MappingHistoryTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "workspace"
        self.target = self.base / "target"
        self.other = self.base / "other"
        for path in (self.workspace, self.target, self.other):
            path.mkdir()
        self.storage = self.base / "memory"
        self.store = MemoryMappingStore(self.storage)
        self.history = MemoryMappingHistory(self.storage)
        self.current = self.storage / REGISTRY_NAME

    def save(self, target: Path | None = None) -> None:
        target = target or self.target
        review = self.store.change(self.workspace, target)
        self.store.change(
            self.workspace, target, expected_sha256=str(review["preview_sha256"])
        )

    def seed(self) -> str:
        self.save()
        name = mapping_backup_name(self.current.read_bytes())
        self.save(self.other)
        return name

    def artifact(self, payload: bytes, *, backup: bool = False) -> str:
        name = (
            mapping_backup_name(payload)
            if backup
            else ".memory-mappings-" + "a" * 32 + ".tmp"
        )
        path = self.storage / name
        path.write_bytes(payload)
        path.chmod(0o600)
        return name

    def test_backups_precede_publish_and_history_is_read_only(self) -> None:
        self.assertEqual(self.history.history()["files"], [])
        self.assertFalse(self.storage.exists())
        self.save()
        before = self.current.read_bytes()
        name = mapping_backup_name(before)
        review = self.store.change(self.workspace, self.other)
        self.assertFalse((self.storage / name).exists())
        replace = os.replace

        def publish(src: str, dst: str, *, src_dir_fd: int, dst_dir_fd: int) -> None:
            self.assertEqual((self.storage / name).read_bytes(), before)
            self.assertEqual(self.current.read_bytes(), before)
            replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

        with patch(
            "mos_eisley.conversation_memory_registry.os.replace", side_effect=publish
        ):
            applied = self.store.change(
                self.workspace,
                self.other,
                expected_sha256=str(review["preview_sha256"]),
            )
        self.assertTrue(applied["backup_synced"])
        self.assertTrue(applied["synced"])
        self.assertEqual((self.storage / name).stat().st_mode & 0o777, 0o600)
        inventory = self.history.history()
        self.assertEqual(data(inventory)["files"][0]["file_name"], name)
        self.assertEqual(data(inventory)["files"][0]["registry"]["revision"], 1)
        self.assertEqual(data(inventory)["current"]["registry"]["revision"], 2)

    def test_restore_new_revision_preserves_source_current_and_memory(self) -> None:
        name = self.seed()
        previous = self.current.read_bytes()
        memory = MemoryStore(self.storage, self.target)
        memory.change("project", "set", text="Keep project memory")
        memory.change("user", "set", text="Keep user memory")
        documents = {
            p.name: p.read_bytes()
            for p in self.storage.glob("*.json")
            if p.name != REGISTRY_NAME
        }
        review = self.history.maintain("restore", name)
        self.assertEqual(review["status"], "planned")
        self.assertEqual(data(review)["before"]["revision"], 2)
        self.assertEqual(data(review)["after"]["revision"], 3)
        receipt = self.history.maintain(
            "restore", name, expected_sha256=str(review["preview_sha256"])
        )
        self.assertTrue(receipt["published"])
        self.assertTrue(receipt["synced"])
        self.assertEqual(self.store.read().mappings[0].target.path, str(self.target))
        self.assertEqual(
            (self.storage / mapping_backup_name(previous)).read_bytes(), previous
        )
        for filename, payload in documents.items():
            self.assertEqual((self.storage / filename).read_bytes(), payload)
        self.assertIsNotNone(
            MemoryMappingResolver(self.storage).resolve(self.workspace)
        )
        with self.assertRaises(ValueError):
            self.history.maintain(
                "restore", name, expected_sha256=str(review["preview_sha256"])
            )

    def test_missing_and_corrupt_current_recovery_preserves_exact_bytes(self) -> None:
        name = self.seed()
        original = self.current.read_bytes()
        for payload in (None, b'{"incomplete":', original + b"\n"):
            if payload is None:
                self.current.unlink()
            else:
                self.current.write_bytes(payload)
                self.current.chmod(0o600)
            with self.assertRaises(ValueError):
                self.history.maintain("discard", name)
            preview = self.history.maintain("restore", name)
            self.assertIsNone(preview["before"])
            restored = self.history.maintain(
                "restore", name, expected_sha256=str(preview["preview_sha256"])
            )
            self.assertTrue(restored["synced"])
            if payload is not None:
                self.assertEqual(
                    (self.storage / mapping_backup_name(payload)).read_bytes(), payload
                )
            self.assertEqual(
                self.store.read().mappings[0].target.path, str(self.target)
            )

    def test_staging_restore_keeps_source_and_cleanup_is_separate(self) -> None:
        self.save()
        payload = self.current.read_bytes()
        name = self.artifact(payload)
        self.save(self.other)
        review = self.history.maintain("restore", name)
        self.history.maintain(
            "restore", name, expected_sha256=str(review["preview_sha256"])
        )
        self.assertEqual((self.storage / name).read_bytes(), payload)
        discard = self.history.maintain("discard", name)
        self.assertEqual(
            base64.b64decode(data(discard)["selected"]["raw_bytes_base64"]), payload
        )
        result = self.history.maintain(
            "discard", name, expected_sha256=str(discard["preview_sha256"])
        )
        self.assertTrue(result["removed"])
        self.assertTrue(result["synced"])
        self.assertFalse((self.storage / name).exists())
        self.assertEqual(self.store.read().mappings[0].target.path, str(self.target))

    def test_invalid_staging_and_incomplete_backup_are_reviewable_not_restorable(
        self,
    ) -> None:
        self.save()
        before = self.current.read_bytes()
        blocked_name = mapping_backup_name(before)
        for name in (self.artifact(b"partial"), blocked_name):
            path = self.storage / name
            path.write_bytes(b"partial")
            path.chmod(0o600)
            with self.assertRaises(ValueError):
                self.history.maintain("restore", name)
            review = self.history.maintain("discard", name)
            self.assertEqual(data(review)["selected"]["raw_sha256"], digest(b"partial"))
            if name == blocked_name:
                update = self.store.change(self.workspace, self.other)
                with self.assertRaises(ValueError):
                    self.store.change(
                        self.workspace,
                        self.other,
                        expected_sha256=str(update["preview_sha256"]),
                    )
                self.assertEqual(self.current.read_bytes(), before)
            self.history.maintain(
                "discard", name, expected_sha256=str(review["preview_sha256"])
            )
        self.save(self.other)
        self.assertEqual((self.storage / blocked_name).read_bytes(), before)

    def test_restore_rejects_duplicate_keys_noncanonical_foreign_and_wrong_address(
        self,
    ) -> None:
        self.save()
        original = self.current.read_bytes()
        foreign = canonical_bytes(
            self.store.read().model_copy(update={"owner_uid": os.getuid() + 1})
        )
        for payload in (
            original + b"\n",
            original.replace(b'"revision":1', b'"revision":1,"revision":1'),
            foreign,
        ):
            name = self.artifact(payload)
            with self.assertRaises(ValueError):
                self.history.maintain("restore", name)
            self.assertEqual(self.current.read_bytes(), original)
        wrong = "mapping-backup-" + "0" * 64 + ".json"
        (self.storage / wrong).write_bytes(original)
        (self.storage / wrong).chmod(0o600)
        with self.assertRaises(ValueError):
            self.history.maintain("restore", wrong)
        self.assertFalse(
            data(self.history.maintain("discard", wrong))["selected"][
                "content_address_matches"
            ]
        )
        name = self.artifact(original)
        self.current.write_bytes(foreign)
        with self.assertRaises(ValueError):
            self.history.maintain("restore", name)

    def test_path_argument_and_missing_storage_never_create_files(self) -> None:
        for name in (
            "../project-mappings.json",
            REGISTRY_NAME,
            "memory.lock",
            "/tmp/file",
            ".memory-mappings-x.tmp",
            "mapping-backup-" + "A" * 64 + ".json",
        ):
            with self.assertRaises(ValueError):
                self.history.maintain("discard", name)
        with self.assertRaises(ValueError):
            self.history.maintain(
                "restore",
                ".memory-mappings-" + "a" * 32 + ".tmp",
                expected_sha256="0" * 64,
            )
        self.assertFalse(self.storage.exists())

    def test_selected_current_storage_lock_and_metadata_changes_invalidate_preview(
        self,
    ) -> None:
        name = self.seed()
        candidate = self.storage / name
        original = candidate.read_bytes()
        review = self.history.maintain("restore", name)
        os.utime(candidate, ns=(1, 1))
        with self.assertRaises(ValueError):
            self.history.maintain(
                "restore", name, expected_sha256=str(review["preview_sha256"])
            )
        review = self.history.maintain("restore", name)
        self.save()
        with self.assertRaises(ValueError):
            self.history.maintain(
                "restore", name, expected_sha256=str(review["preview_sha256"])
            )
        review = self.history.maintain("restore", name)
        lock = self.storage / "memory.lock"
        lock.rename(self.storage / "old.lock")
        lock.touch(mode=0o600)
        with self.assertRaises(ValueError):
            self.history.maintain(
                "restore", name, expected_sha256=str(review["preview_sha256"])
            )
        review = self.history.maintain("restore", name)
        self.storage.rename(self.base / "old-memory")
        self.storage.mkdir(mode=0o700)
        for p in (self.base / "old-memory").iterdir():
            p.rename(self.storage / p.name)
        with self.assertRaises(ValueError):
            self.history.maintain(
                "restore", name, expected_sha256=str(review["preview_sha256"])
            )
        self.assertEqual(candidate.read_bytes(), original)

    def test_all_restore_directory_pins_are_rechecked(self) -> None:
        name = self.seed()
        preview = self.history.maintain("restore", name)
        self.target.rename(self.base / "moved")
        self.target.mkdir()
        before = self.current.read_bytes()
        with self.assertRaises(DirectorySelectionError):
            self.history.maintain(
                "restore", name, expected_sha256=str(preview["preview_sha256"])
            )
        with self.assertRaises(DirectorySelectionError):
            self.history.maintain("restore", name)
        self.assertEqual(self.current.read_bytes(), before)
        # Discard does not need to access vanished historical directories.
        self.assertEqual(self.history.maintain("discard", name)["status"], "planned")

    def test_late_source_directory_and_current_changes_block_publication(self) -> None:
        name = self.seed()
        fsync = os.fsync
        for kind in ("source", "current", "directory", "staging"):
            with self.subTest(kind=kind):
                if kind == "directory":
                    self.target.mkdir(exist_ok=True)
                preview = self.history.maintain("restore", name)
                before = self.current.read_bytes()
                fired = False

                def mutate(fd: int, kind: str = kind, before: bytes = before) -> None:
                    nonlocal fired
                    fsync(fd)
                    if fired:
                        return
                    fired = True
                    if kind == "source":
                        os.utime(self.storage / name, ns=(1, 1))
                    elif kind == "current":
                        self.current.write_bytes(before + b"\n")
                    elif kind == "directory":
                        self.target.rename(self.base / "late-moved")
                        self.target.mkdir()
                    else:
                        for staged in self.storage.glob(".memory-mappings-*.tmp"):
                            staged.write_bytes(b"altered")

                # For staged mutation wait until the staging-file flush itself.
                def stage_mutate(fd: int) -> None:
                    fsync(fd)
                    for staged in self.storage.glob(".memory-mappings-*.tmp"):
                        staged.write_bytes(b"altered")

                with (
                    patch(
                        "mos_eisley.conversation_memory_registry.os.fsync",
                        side_effect=stage_mutate if kind == "staging" else mutate,
                    ),
                    self.assertRaises(MappingRecoveryError) as caught,
                ):
                    self.history.maintain(
                        "restore",
                        name,
                        expected_sha256=str(preview["preview_sha256"]),
                    )
                self.assertFalse(caught.exception.receipt["published"])
                self.current.write_bytes(before)
                if kind == "directory":
                    self.target.rmdir()
                    (self.base / "late-moved").rename(self.target)

    def test_unsafe_files_and_lock_contention_are_rejected(self) -> None:
        name = self.seed()
        candidate = self.storage / name
        source = self.storage / "source"
        candidate.rename(source)
        for kind in ("symlink", "hardlink", "fifo", "directory", "public"):
            if kind == "symlink":
                candidate.symlink_to(source)
            elif kind == "hardlink":
                os.link(source, candidate)
            elif kind == "fifo":
                os.mkfifo(candidate, 0o600)
            elif kind == "directory":
                candidate.mkdir()
            else:
                candidate.write_bytes(source.read_bytes())
                candidate.chmod(0o644)
            for action in ("restore", "discard"):
                with self.assertRaises((OSError, ValueError)):
                    self.history.maintain(action, name)
            with self.assertRaises((OSError, ValueError)):
                self.history.history()
            if kind == "directory":
                candidate.rmdir()
            else:
                candidate.unlink()
        source.rename(candidate)
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.history.maintain("restore", name)
            with self.assertRaises(BlockingIOError):
                self.history.history()

    def test_real_byte_file_and_inventory_bounds(self) -> None:
        self.save()
        name = self.artifact(b"x" * REGISTRY_BYTES)
        self.assertEqual(
            data(self.history.maintain("discard", name))["selected"]["file_identity"][
                "bytes"
            ],
            REGISTRY_BYTES,
        )
        (self.storage / name).write_bytes(b"x" * (REGISTRY_BYTES + 1))
        with self.assertRaises(ValueError):
            self.history.maintain("discard", name)
        (self.storage / name).unlink()
        for i in range(129):
            path = self.storage / (f".memory-mappings-{i:032x}.tmp")
            path.write_bytes(b"x")
            path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "128 files"):
            self.history.history()
        for p in self.storage.glob(".memory-mappings-*.tmp"):
            p.unlink()
        for i in range(9):
            path = self.storage / (f".memory-mappings-{i:032x}.tmp")
            path.write_bytes(b"x" * REGISTRY_BYTES)
            path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "8 MiB"):
            self.history.history()
        for p in self.storage.glob(".memory-mappings-*.tmp"):
            p.unlink()
        for i in range(1024):
            (self.storage / f"unrelated-{i}").touch()
        with self.assertRaisesRegex(ValueError, "1,024 entries"):
            self.history.history()

    def test_partial_progress_for_failed_publish_and_discard_flush(self) -> None:
        name = self.seed()
        preview = self.history.maintain("restore", name)
        fsync = os.fsync

        def fail_after_publish(fd: int) -> None:
            if (
                stat.S_ISDIR(os.fstat(fd).st_mode)
                and json.loads(self.current.read_bytes())["revision"] == 3
            ):
                raise OSError("flush interrupted")
            fsync(fd)

        with (
            patch(
                "mos_eisley.conversation_memory_registry.os.fsync",
                side_effect=fail_after_publish,
            ),
            self.assertRaises(MappingRecoveryError) as caught,
        ):
            self.history.maintain(
                "restore", name, expected_sha256=str(preview["preview_sha256"])
            )
        receipt = caught.exception.receipt
        self.assertTrue(receipt["published"])
        self.assertTrue(receipt["backup_synced"])
        self.assertFalse(receipt["synced"])
        self.assertEqual(self.store.read().revision, 3)
        preview = self.history.maintain("discard", name)
        with (
            patch(
                "mos_eisley.conversation_memory_registry_history.os.fsync",
                side_effect=OSError("flush interrupted"),
            ),
            self.assertRaises(MappingRecoveryError) as caught,
        ):
            self.history.maintain(
                "discard", name, expected_sha256=str(preview["preview_sha256"])
            )
        self.assertTrue(caught.exception.receipt["removed"])
        self.assertFalse(caught.exception.receipt["synced"])
        self.assertFalse((self.storage / name).exists())

    def test_process_death_before_after_publish_and_during_backup(self) -> None:
        script = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_registry import MemoryMappingStore
store = MemoryMappingStore(Path(sys.argv[1]))
w, target = Path(sys.argv[2]), Path(sys.argv[3])
preview = store.change(w, target)
replace, fsync = os.replace, os.fsync
def die(*args, **kwargs):
    if sys.argv[4] == "after":
        replace(*args, **kwargs)
    os._exit(73)
def fail_backup(fd):
    fsync(fd)
    os._exit(73)
operation = "fsync" if sys.argv[4] == "backup" else "replace"
with patch(
    "mos_eisley.conversation_memory_registry.os." + operation,
    side_effect=fail_backup if sys.argv[4] == "backup" else die,
):
    store.change(w, target, expected_sha256=preview["preview_sha256"])
"""
        for phase in ("backup", "before", "after"):
            self.save()
            before = self.current.read_bytes()
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(self.storage),
                    str(self.workspace),
                    str(self.other),
                    phase,
                ],
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(child.returncode, 73, child.stderr)
            self.assertEqual(
                (self.storage / mapping_backup_name(before)).read_bytes(), before
            )
            self.assertEqual(
                self.store.read().mappings[0].target.path,
                str(self.other if phase == "after" else self.target),
            )
            if phase == "before":
                stages = list(self.storage.glob(".memory-mappings-*.tmp"))
                self.assertTrue(stages)
                preview = self.history.maintain("restore", stages[-1].name)
                self.history.maintain(
                    "restore",
                    stages[-1].name,
                    expected_sha256=str(preview["preview_sha256"]),
                )
                self.assertEqual(
                    self.store.read().mappings[0].target.path, str(self.other)
                )

    def test_cli_history_restore_discard_and_argument_guards(self) -> None:
        name = self.seed()

        def cli(*arguments: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "memory-project-mapping",
                    *arguments,
                    "--memory-storage",
                    str(self.storage),
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )

        result = cli("history")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["files"][0]["file_name"], name)
        for action in ("restore", "discard"):
            result = cli(action, "--file-name", name)
            self.assertEqual(result.returncode, 0, result.stderr)
            preview = json.loads(result.stdout)
            result = cli(
                action,
                "--file-name",
                name,
                "--apply",
                "--expected-sha256",
                preview["preview_sha256"],
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "completed")
        for args in (
            ("restore",),
            ("history", "--apply"),
            ("history", "--file-name", name),
            ("show", "--file-name", name),
            ("restore", "--file-name", name, "-C", str(self.workspace)),
            ("discard", "--file-name", name, "--expected-sha256", "0" * 64),
        ):
            self.assertEqual(cli(*args).returncode, 2, args)

    def test_substituted_staging_file_is_not_published_or_deleted(self) -> None:
        name = self.seed()
        before = self.current.read_bytes()
        preview = self.history.maintain("restore", name)
        fsync = os.fsync
        substituted: list[Path] = []

        def replace_staged(fd: int) -> None:
            fsync(fd)
            for path in self.storage.glob(".memory-mappings-*.tmp"):
                payload = path.read_bytes()
                path.rename(self.storage / "original-staging")
                path.write_bytes(payload)
                path.chmod(0o600)
                substituted.append(path)

        with (
            patch(
                "mos_eisley.conversation_memory_registry.os.fsync",
                side_effect=replace_staged,
            ),
            self.assertRaises(MappingRecoveryError),
        ):
            self.history.maintain(
                "restore", name, expected_sha256=str(preview["preview_sha256"])
            )
        self.assertTrue(substituted)
        self.assertTrue(substituted[0].exists())
        self.assertEqual(self.current.read_bytes(), before)

    def test_real_interrupted_partial_backup_can_be_reviewed_and_removed(self) -> None:
        self.save()
        before = self.current.read_bytes()
        script = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_registry import MemoryMappingStore
store = MemoryMappingStore(Path(sys.argv[1]))
w, t = Path(sys.argv[2]), Path(sys.argv[3])
preview = store.change(w, t)
fdopen = os.fdopen
class Partial:
    def __init__(self, fd):
        self.fd = fd
    def __enter__(self):
        return self
    def __exit__(self, *args):
        os.close(self.fd)
    def write(self, payload):
        os.write(self.fd, payload[:7])
        os._exit(73)
def opened(fd, mode, *args, **kwargs):
    return Partial(fd) if mode == "wb" else fdopen(fd, mode, *args, **kwargs)
with patch("mos_eisley.conversation_memory_registry.os.fdopen", side_effect=opened):
    store.change(w, t, expected_sha256=preview["preview_sha256"])
"""
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(self.storage),
                str(self.workspace),
                str(self.other),
            ],
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(child.returncode, 73, child.stderr)
        name = mapping_backup_name(before)
        self.assertEqual((self.storage / name).read_bytes(), before[:7])
        self.assertEqual(self.current.read_bytes(), before)
        with self.assertRaises(ValueError):
            self.save(self.other)
        preview = self.history.maintain("discard", name)
        self.history.maintain(
            "discard", name, expected_sha256=str(preview["preview_sha256"])
        )
        self.save(self.other)
        self.assertEqual((self.storage / name).read_bytes(), before)

    def test_real_restore_and_discard_death_require_fresh_inspection(self) -> None:
        name = self.seed()
        script = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_registry_history import MemoryMappingHistory
store = MemoryMappingHistory(Path(sys.argv[1]))
action, name, expected = sys.argv[2:5]
operation = "replace" if action == "restore" else "unlink"
real = getattr(os, operation)
def die(*args, **kwargs):
    real(*args, **kwargs)
    os._exit(73)
with patch("os." + operation, side_effect=die):
    store.maintain(action, name, expected_sha256=expected)
"""
        for action in ("restore", "discard"):
            preview = self.history.maintain(action, name)
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(self.storage),
                    action,
                    name,
                    str(preview["preview_sha256"]),
                ],
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(child.returncode, 73, child.stderr)
            with self.assertRaises(ValueError):
                self.history.maintain(
                    action, name, expected_sha256=str(preview["preview_sha256"])
                )
        self.assertEqual(self.store.read().mappings[0].target.path, str(self.target))
        self.assertFalse((self.storage / name).exists())

    def test_restore_changes_new_launches_but_preserves_both_backend_resumes(
        self,
    ) -> None:
        name = self.seed()
        original = self.current.read_bytes()
        for backend in ("snapshot", "sqlite"):
            self.current.write_bytes(original)
            storage = self.base / backend

            def launch(
                command: list[str], storage: Path = storage, backend: str = backend
            ):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        *command,
                        "-C",
                        str(self.workspace),
                        "--memory-storage",
                        str(self.storage),
                        "--storage",
                        str(storage),
                        "--storage-backend",
                        backend,
                        "--json",
                    ],
                    input="/quit\n",
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return next(
                    json.loads(line)
                    for line in result.stdout.splitlines()
                    if json.loads(line)["type"] == "conversation.opened"
                )

            opened = launch(["chat"])
            self.assertEqual(opened["memory_workspace"], str(self.other))
            staged = self.artifact((self.storage / name).read_bytes())
            self.history.history()
            selected = MemoryMappingResolver(self.storage).resolve(self.workspace)
            assert selected is not None
            self.assertEqual(selected.path, self.other)
            preview = self.history.maintain("restore", staged)
            self.history.maintain(
                "restore", staged, expected_sha256=str(preview["preview_sha256"])
            )
            resumed = launch(["resume", opened["session_id"]])
            self.assertEqual(resumed["memory_workspace"], str(self.other))
            fresh = launch(["chat"])
            self.assertEqual(fresh["memory_workspace"], str(self.target))
