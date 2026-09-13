"""Bounded complete inventories, protected mapping backups and interrupted deletion."""

import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_memory_registry import (
    REGISTRY_BYTES,
    REGISTRY_NAME,
    MappedDirectory,
    MemoryMappingRegistry,
    MemoryMappingStore,
    SavedMemoryMapping,
    mapping_backup_name,
)
from mos_eisley.conversation_memory_registry_retention import (
    MAX_MAPPING_PRUNE,
    MappingRetentionError,
    MemoryMappingRetention,
)
from mos_eisley.core.models import canonical_bytes


def data(value: object) -> Any:
    return json.loads(json.dumps(value))


class MappingRetentionTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "workspace"
        self.target = self.base / "target"
        self.workspace.mkdir()
        self.target.mkdir()
        self.storage = self.base / "memory"
        self.store = MemoryMappingStore(self.storage)
        preview = self.store.change(self.workspace, self.target)
        self.store.change(
            self.workspace, self.target, expected_sha256=str(preview["preview_sha256"])
        )
        self.current = self.storage / REGISTRY_NAME
        self.retention = MemoryMappingRetention(self.storage)
        self.serial = 1

    def backup(self, mtime: int, registry: MemoryMappingRegistry | None = None) -> Path:
        self.serial += 1
        record = registry or self.store.read().model_copy(
            update={"revision": self.serial}
        )
        payload = canonical_bytes(record)
        path = self.storage / mapping_backup_name(payload)
        path.write_bytes(payload)
        path.chmod(0o600)
        os.utime(path, ns=(mtime, mtime))
        return path

    def test_policy_combines_newest_cutoff_and_matching_current(self) -> None:
        older = self.backup(1)
        cutoff = self.backup(100)
        newest = self.backup(200)
        current_copy = self.backup(2, self.store.read())
        before = self.current.read_bytes()
        review = self.retention.retain(keep_newest=1, before_ns=100)
        self.assertEqual(review["selected"], [older.name])
        protected = {row["name"]: row["reasons"] for row in data(review)["protected"]}
        self.assertEqual(protected[cutoff.name], ["age-cutoff"])
        self.assertEqual(protected[newest.name], ["keep-newest", "age-cutoff"])
        self.assertEqual(protected[current_copy.name], ["matches-current-registry"])
        result = self.retention.retain(
            keep_newest=1, before_ns=100, expected_sha256=str(review["preview_sha256"])
        )
        self.assertEqual(result["removed"], [older.name])
        self.assertEqual(result["synced"], [older.name])
        self.assertFalse(older.exists())
        self.assertTrue(all(p.exists() for p in (cutoff, newest, current_copy)))
        self.assertEqual(self.current.read_bytes(), before)

    def test_ties_use_filename_order_and_missing_current_protects_all(self) -> None:
        names = sorted(self.backup(5).name for _ in range(3))
        review = self.retention.retain(keep_newest=1, before_ns=6)
        self.assertEqual(review["selected"], names[1:])
        self.current.unlink()
        review = self.retention.retain(keep_newest=0, before_ns=6)
        self.assertEqual(review["selected"], [])
        self.assertEqual({r["name"] for r in data(review)["protected"]}, set(names))
        self.assertTrue(
            all(
                "no-current-registry" in r["reasons"] for r in data(review)["protected"]
            )
        )
        self.retention.retain(
            keep_newest=0, before_ns=6, expected_sha256=str(review["preview_sha256"])
        )
        self.assertTrue(all((self.storage / n).exists() for n in names))
        self.assertFalse(self.current.exists())

    def test_invalid_or_foreign_current_blocks_entire_retention(self) -> None:
        backup = self.backup(1)
        valid = self.store.read()
        for payload in (
            b"broken",
            canonical_bytes(valid.model_copy(update={"owner_uid": os.getuid() + 1})),
        ):
            self.current.write_bytes(payload)
            with self.assertRaises(ValueError):
                self.retention.retain(keep_newest=0, before_ns=10)
            self.assertTrue(backup.exists())

    def test_prune_is_capped_and_remainder_needs_fresh_review(self) -> None:
        names = [self.backup(i + 1).name for i in range(MAX_MAPPING_PRUNE + 3)]
        review = self.retention.retain(keep_newest=0, before_ns=100)
        self.assertEqual(review["selected"], names[:32])
        self.assertEqual(review["remaining_eligible"], names[32:])
        self.retention.retain(
            keep_newest=0, before_ns=100, expected_sha256=str(review["preview_sha256"])
        )
        with self.assertRaises(ValueError):
            self.retention.retain(
                keep_newest=0,
                before_ns=100,
                expected_sha256=str(review["preview_sha256"]),
            )
        fresh = self.retention.retain(keep_newest=0, before_ns=100)
        self.assertEqual(fresh["selected"], names[32:])

    def test_all_backups_validated_even_when_newest_would_be_protected(self) -> None:
        older = self.backup(1)
        newer = self.backup(9)
        original = newer.read_bytes()
        record = MemoryMappingRegistry.model_validate_json(original)
        for payload in (
            b"broken",
            original + b"\n",
            original.replace(b'"revision":3', b'"revision":3,"revision":3'),
            canonical_bytes(record.model_copy(update={"owner_uid": os.getuid() + 1})),
            canonical_bytes(record.model_copy(update={"revision": 99})),
        ):
            newer.write_bytes(payload)
            with self.assertRaises(ValueError):
                self.retention.retain(keep_newest=1, before_ns=5)
            self.assertTrue(older.exists())
        newer.write_bytes(original)
        bad_name = self.storage / "mapping-backup-unsupported.json"
        bad_name.write_bytes(original)
        with self.assertRaises(ValueError):
            self.retention.retain(keep_newest=1, before_ns=5)

    def test_staging_and_other_memory_files_are_not_pruned(self) -> None:
        backup = self.backup(1)
        names = [
            ".memory-mappings-" + "a" * 32 + ".tmp",
            "resolution-backup-" + "0" * 64 + ".json",
            "user-memory.json",
        ]
        for name in names:
            (self.storage / name).write_bytes(b"unrelated")
        review = self.retention.retain(keep_newest=0, before_ns=2)
        self.assertEqual(review["selected"], [backup.name])
        self.retention.retain(
            keep_newest=0, before_ns=2, expected_sha256=str(review["preview_sha256"])
        )
        for name in names:
            self.assertEqual((self.storage / name).read_bytes(), b"unrelated")

    def test_stale_protected_file_inventory_current_and_policy_reject_apply(
        self,
    ) -> None:
        selected = self.backup(1)
        protected = self.backup(10)
        review = self.retention.retain(keep_newest=1, before_ns=20)
        os.utime(protected, ns=(11, 11))
        with self.assertRaises(ValueError):
            self.retention.retain(
                keep_newest=1,
                before_ns=20,
                expected_sha256=str(review["preview_sha256"]),
            )
        review = self.retention.retain(keep_newest=1, before_ns=20)
        with self.assertRaises(ValueError):
            self.retention.retain(
                keep_newest=0,
                before_ns=20,
                expected_sha256=str(review["preview_sha256"]),
            )
        with self.assertRaises(ValueError):
            self.retention.retain(
                keep_newest=1,
                before_ns=21,
                expected_sha256=str(review["preview_sha256"]),
            )
        self.backup(30)
        with self.assertRaises(ValueError):
            self.retention.retain(
                keep_newest=1,
                before_ns=20,
                expected_sha256=str(review["preview_sha256"]),
            )
        review = self.retention.retain(keep_newest=1, before_ns=20)
        current = self.store.read().model_copy(update={"revision": 99})
        self.current.write_bytes(canonical_bytes(current))
        with self.assertRaises(ValueError):
            self.retention.retain(
                keep_newest=1,
                before_ns=20,
                expected_sha256=str(review["preview_sha256"]),
            )
        self.assertTrue(selected.exists())

    def test_late_retained_change_stops_before_next_unlink(self) -> None:
        first, second, kept = self.backup(1), self.backup(2), self.backup(3)
        review = self.retention.retain(keep_newest=1, before_ns=10)
        fsync = os.fsync

        def mutate(fd: int) -> None:
            fsync(fd)
            os.utime(kept, ns=(4, 4))

        with (
            patch("os.fsync", side_effect=mutate),
            self.assertRaises(MappingRetentionError) as caught,
        ):
            self.retention.retain(
                keep_newest=1,
                before_ns=10,
                expected_sha256=str(review["preview_sha256"]),
            )
        self.assertEqual(caught.exception.receipt["removed"], [first.name])
        self.assertEqual(caught.exception.receipt["synced"], [first.name])
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertTrue(kept.exists())

    def test_failed_flush_reports_removed_but_unsynced(self) -> None:
        first, second = self.backup(1), self.backup(2)
        review = self.retention.retain(keep_newest=0, before_ns=10)
        with (
            patch("os.fsync", side_effect=OSError("flush failed")),
            self.assertRaises(MappingRetentionError) as caught,
        ):
            self.retention.retain(
                keep_newest=0,
                before_ns=10,
                expected_sha256=str(review["preview_sha256"]),
            )
        self.assertEqual(caught.exception.receipt["removed"], [first.name])
        self.assertEqual(caught.exception.receipt["synced"], [])
        self.assertTrue(second.exists())

    def test_real_process_death_after_unlink_requires_new_preview(self) -> None:
        first, second = self.backup(1), self.backup(2)
        preview = self.retention.retain(keep_newest=0, before_ns=10)
        script = """
import os,sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_registry_retention import MemoryMappingRetention
store=MemoryMappingRetention(Path(sys.argv[1]))
def die(fd):
    os._exit(73)
with patch("os.fsync",side_effect=die):
    store.retain(keep_newest=0,before_ns=10,expected_sha256=sys.argv[2])
"""
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(self.storage),
                str(preview["preview_sha256"]),
            ],
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(child.returncode, 73, child.stderr)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        with self.assertRaises(ValueError):
            self.retention.retain(
                keep_newest=0,
                before_ns=10,
                expected_sha256=str(preview["preview_sha256"]),
            )
        self.assertEqual(
            self.retention.retain(keep_newest=0, before_ns=10)["selected"],
            [second.name],
        )

    def test_unsafe_backup_and_lock_contention_fail_without_deletion(self) -> None:
        first = self.backup(1)
        backup = self.storage / "safe-copy"
        first.rename(backup)
        for kind in ("symlink", "hardlink", "fifo", "public", "directory"):
            if kind == "symlink":
                first.symlink_to(backup)
            elif kind == "hardlink":
                os.link(backup, first)
            elif kind == "fifo":
                os.mkfifo(first, 0o600)
            elif kind == "directory":
                first.mkdir()
            else:
                first.write_bytes(backup.read_bytes())
                first.chmod(0o644)
            with self.assertRaises((OSError, ValueError)):
                self.retention.retain(keep_newest=0, before_ns=10)
            if kind == "directory":
                first.rmdir()
            else:
                first.unlink()
        backup.rename(first)
        preview = self.retention.retain(keep_newest=0, before_ns=10)
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.retention.retain(
                    keep_newest=0,
                    before_ns=10,
                    expected_sha256=str(preview["preview_sha256"]),
                )
        self.assertTrue(first.exists())

    def test_real_inventory_bounds(self) -> None:
        paths = [self.backup(i) for i in range(128)]
        self.assertEqual(
            len(
                data(self.retention.retain(keep_newest=128, before_ns=1))["inventory"][
                    "backups"
                ]
            ),
            128,
        )
        extra = self.backup(129)
        with self.assertRaisesRegex(ValueError, "128 backups"):
            self.retention.retain(keep_newest=0, before_ns=1)
        for path in (*paths, extra):
            path.unlink()
        for i in range(1023):
            (self.storage / f"other-{i}").touch()
        with self.assertRaisesRegex(ValueError, "1,024"):
            self.retention.retain(keep_newest=0, before_ns=1)
        for path in self.storage.glob("other-*"):
            path.unlink()
        # Real valid canonical registries whose combined bytes exceed 8 MiB.
        entries = tuple(
            SavedMemoryMapping(
                workspace=MappedDirectory(
                    path="/" + f"{i:03}" + "w" * 3690, device=1, inode=i
                ),
                target=MappedDirectory(path="/" + "t" * 3690, device=1, inode=1),
            )
            for i in range(128)
        )
        large = MemoryMappingRegistry(owner_uid=os.getuid(), mappings=entries)
        self.assertLess(len(canonical_bytes(large)), REGISTRY_BYTES)
        for i in range(9):
            self.backup(i, large.model_copy(update={"revision": i}))
        with self.assertRaisesRegex(ValueError, "byte budget"):
            self.retention.retain(keep_newest=0, before_ns=20)
        for path in self.storage.glob("mapping-backup-*"):
            path.unlink()
        oversized = self.backup(1)
        oversized.write_bytes(b"x" * (REGISTRY_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "1 MiB"):
            self.retention.retain(keep_newest=0, before_ns=20)

    def test_invalid_policy_and_missing_storage_do_not_create_data(self) -> None:
        absent = self.base / "absent"
        store = MemoryMappingRetention(absent)
        for count in (-1, 129, True):
            with self.assertRaises(ValueError):
                store.retain(keep_newest=count, before_ns=1)
        for cutoff in (-1, 0, 2**63, True):
            with self.assertRaises(ValueError):
                store.retain(keep_newest=0, before_ns=cutoff)
        for sha in ("wrong", "A" * 64):
            with self.assertRaises(ValueError):
                store.retain(keep_newest=0, before_ns=1, expected_sha256=sha)
        with self.assertRaises(ValueError):
            store.retain(keep_newest=0, before_ns=1)
        self.assertFalse(absent.exists())

    def test_storage_and_lock_replacement_stale_preview(self) -> None:
        backup = self.backup(1)
        preview = self.retention.retain(keep_newest=0, before_ns=10)
        lock = self.storage / "memory.lock"
        lock.rename(self.storage / "old-lock")
        lock.touch(mode=0o600)
        with self.assertRaises(ValueError):
            self.retention.retain(
                keep_newest=0,
                before_ns=10,
                expected_sha256=str(preview["preview_sha256"]),
            )
        preview = self.retention.retain(keep_newest=0, before_ns=10)
        moved = self.base / "old-memory"
        self.storage.rename(moved)
        self.storage.mkdir(mode=0o700)
        for path in moved.iterdir():
            path.rename(self.storage / path.name)
        with self.assertRaises(ValueError):
            self.retention.retain(
                keep_newest=0,
                before_ns=10,
                expected_sha256=str(preview["preview_sha256"]),
            )
        self.assertTrue(backup.exists())

    def test_cli_preview_apply_and_option_guards(self) -> None:
        backup = self.backup(1)

        def cli(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "memory-project-mapping",
                    *args,
                    "--memory-storage",
                    str(self.storage),
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )

        base = ["retain", "--keep-newest", "0", "--before-ns", "10"]
        result = cli(*base)
        self.assertEqual(result.returncode, 0, result.stderr)
        preview = json.loads(result.stdout)
        self.assertEqual(preview["selected"], [backup.name])
        result = cli(*base, "--apply", "--expected-sha256", preview["preview_sha256"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["removed"], [backup.name])
        for args in (
            ("retain",),
            (*base, "--apply"),
            (*base, "--input", "x"),
            ("history", "--keep-newest", "1"),
            ("import", "--before-ns", "10"),
            (*base, "-C", str(self.workspace)),
        ):
            self.assertEqual(cli(*args).returncode, 2, args)

    def test_directory_change_during_inventory_rejects_partial_listing(self) -> None:
        from contextlib import contextmanager

        selected = self.backup(1)
        payload = canonical_bytes(self.store.read().model_copy(update={"revision": 99}))
        added = self.storage / mapping_backup_name(payload)
        scandir = os.scandir

        @contextmanager
        def changed(root: int):
            with scandir(root) as entries:
                yield entries
            added.write_bytes(payload)
            added.chmod(0o600)

        with patch("os.scandir", side_effect=changed), self.assertRaises(ValueError):
            self.retention.retain(keep_newest=0, before_ns=10)
        self.assertTrue(selected.exists())
        self.assertTrue(added.exists())

    def test_cli_reports_partial_progress_on_flush_failure(self) -> None:
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from mos_eisley.cli import main

        selected = self.backup(1)
        preview = self.retention.retain(keep_newest=0, before_ns=10)
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch("os.fsync", side_effect=OSError("flush interrupted")),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            code = main(
                [
                    "memory-project-mapping",
                    "retain",
                    "--keep-newest",
                    "0",
                    "--before-ns",
                    "10",
                    "--memory-storage",
                    str(self.storage),
                    "--apply",
                    "--expected-sha256",
                    str(preview["preview_sha256"]),
                    "--json",
                ]
            )
        self.assertEqual(code, 2)
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["status"], "incomplete")
        self.assertEqual(receipt["removed"], [selected.name])
        self.assertEqual(receipt["synced"], [])

    def test_both_backend_resumes_and_memory_documents_survive_retention(self) -> None:
        from mos_eisley.conversation_memory import MemoryStore

        memory = MemoryStore(self.storage, self.target)
        memory.change("project", "set", text="Project decisions")
        memory.change("user", "set", text="User preferences")
        for backend in ("snapshot", "sqlite"):
            selected = self.backup(1)
            sessions = self.base / backend
            before = {
                p.name: p.read_bytes()
                for p in self.storage.glob("*.json")
                if not p.name.startswith("mapping-backup-")
            }

            def launch(
                command: list[str], backend: str = backend, sessions: Path = sessions
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
                        str(sessions),
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
            preview = self.retention.retain(keep_newest=0, before_ns=10)
            self.retention.retain(
                keep_newest=0,
                before_ns=10,
                expected_sha256=str(preview["preview_sha256"]),
            )
            self.assertFalse(selected.exists())
            resumed = launch(["resume", opened["session_id"]])
            self.assertEqual(resumed["memory_workspace"], str(self.target))
            self.assertEqual(launch(["chat"])["memory_workspace"], str(self.target))
            for name, payload in before.items():
                self.assertEqual((self.storage / name).read_bytes(), payload)
