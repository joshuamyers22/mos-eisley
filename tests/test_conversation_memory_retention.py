"""Complete inventories, protected backups and interrupted retention apply."""

import argparse
import fcntl
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot, MemoryStore
from mos_eisley.conversation_memory_registry import MemoryMappingStore
from mos_eisley.conversation_memory_retention import (
    MAX_BACKUPS,
    MAX_DIRECTORY_ENTRIES,
    MAX_INVENTORY_BYTES,
    MAX_PRUNE,
    MemoryRetentionError,
    retain_memory_backups,
    run_command,
)
from mos_eisley.core.models import canonical_bytes, digest


class MemoryRetentionTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "project"
        self.other = self.base / "other"
        self.workspace.mkdir()
        self.other.mkdir()
        self.storage = self.base / "memory"
        self.store = MemoryStore(self.storage, self.workspace)
        self.current = self.store.change("project", "set", text="Current decisions")
        self.store.change("user", "set", text="Private preferences")
        self.serial = 0

    def backup(
        self,
        mtime: int,
        *,
        workspace: Path | None = None,
        snapshot: MemorySnapshot | None = None,
    ) -> Path:
        self.serial += 1
        if snapshot is None:
            document = self.current.document.model_copy(
                update={
                    "text": f"Earlier decisions {self.serial}",
                    "workspace": str(workspace or self.workspace),
                }
            )
            snapshot = MemorySnapshot(
                document=document, sha256=digest(canonical_bytes(document))
            )
        payload = canonical_bytes(snapshot)
        path = self.storage / ("resolution-backup-" + digest(payload) + ".json")
        path.write_bytes(payload)
        path.chmod(0o600)
        os.utime(path, ns=(mtime, mtime))
        return path

    def retain(
        self, keep: int = 1, cutoff: int = 100, expected: str | None = None
    ) -> dict[str, object]:
        return retain_memory_backups(
            self.storage,
            str(self.workspace),
            keep_newest=keep,
            before_ns=cutoff,
            expected_sha256=expected,
        )

    def apply(
        self, receipt: dict[str, object], keep: int = 1, cutoff: int = 100
    ) -> dict[str, object]:
        return self.retain(keep, cutoff, str(receipt["preview_sha256"]))

    def test_count_age_current_and_other_project_protections(self) -> None:
        oldest = self.backup(10)
        self.backup(20)
        newest = self.backup(110)
        current = self.backup(5, snapshot=self.current)
        foreign = self.backup(1, workspace=self.other)
        registry = MemoryMappingStore(self.storage)
        preview = registry.change(self.workspace, self.other)
        registry.change(
            self.workspace, self.other, expected_sha256=str(preview["preview_sha256"])
        )
        before = {path: path.read_bytes() for path in self.storage.iterdir()}
        receipt = self.retain(2, 100)
        self.assertEqual(receipt, self.retain(2, 100))
        self.assertEqual(receipt["selected"], [oldest.name])
        self.assertEqual(receipt["remaining_eligible"], [])
        data = json.loads(json.dumps(receipt))
        protections = {row["name"]: row["reasons"] for row in data["protected"]}
        self.assertEqual(protections[newest.name], ["keep-newest", "age-cutoff"])
        self.assertEqual(protections[current.name], ["matches-current-memory"])
        other = next(
            row for row in data["inventory"]["backups"] if row["name"] == foreign.name
        )
        self.assertIsNone(other["record"])
        self.assertEqual(
            {path: path.read_bytes() for path in self.storage.iterdir()}, before
        )
        result = self.apply(receipt, 2, 100)
        self.assertEqual(result["removed"], [oldest.name])
        self.assertEqual(result["synced"], result["removed"])
        self.assertEqual(result["status"], "completed")
        for path, payload in before.items():
            if path != oldest:
                self.assertEqual(path.read_bytes(), payload)
        self.assertFalse(oldest.exists())

    def test_equal_mtime_uses_filename_tie_break_and_strict_cutoff(self) -> None:
        paths = [self.backup(10) for _ in range(4)]
        ordered = sorted(path.name for path in paths)
        self.assertEqual(self.retain(1, 10)["selected"], [])
        receipt = self.retain(1, 11)
        self.assertEqual(receipt["selected"], ordered[1:])
        self.apply(receipt, 1, 11)
        self.assertTrue((self.storage / ordered[0]).exists())

    def test_newest_uses_file_mtime_not_document_timestamp_or_revision(self) -> None:
        older = self.backup(1)
        newer = self.backup(2)
        a = MemorySnapshot.model_validate_json(older.read_bytes())
        b = MemorySnapshot.model_validate_json(newer.read_bytes())
        self.assertEqual(a.document.updated_at, b.document.updated_at)
        self.assertEqual(a.document.revision, b.document.revision)
        self.assertEqual(self.retain()["selected"], [older.name])

    def test_missing_current_protects_all_and_empty_inventory_is_noop(self) -> None:
        receipt = self.retain()
        self.assertEqual(self.apply(receipt)["removed"], [])
        backup = self.backup(1)
        self.store.path("project").unlink()
        receipt = self.retain(0)
        self.assertEqual(receipt["selected"], [])
        self.assertIn("no-current-memory", json.dumps(receipt))
        self.assertEqual(self.apply(receipt, 0)["removed"], [])
        self.assertTrue(backup.exists())

    def test_unreadable_current_blocks_inventory(self) -> None:
        self.backup(1)
        self.store.path("project").write_bytes(b"invalid")
        with self.assertRaises(ValueError):
            self.retain(0)

    def test_stale_inventory_policy_and_current_changes_prevent_deletion(self) -> None:
        old = self.backup(1)
        newest = self.backup(2)
        preview = self.retain()
        for keep, cutoff in ((0, 100), (1, 101)):
            with self.assertRaises(ValueError):
                self.apply(preview, keep, cutoff)
        added = self.backup(3, workspace=self.other)
        with self.assertRaises(ValueError):
            self.apply(preview)
        added.unlink()
        preview = self.retain()
        os.utime(newest, ns=(9, 9))
        with self.assertRaises(ValueError):
            self.apply(preview)
        preview = self.retain()
        self.store.change("project", "append", text="New decision")
        with self.assertRaises(ValueError):
            self.apply(preview)
        self.assertTrue(old.exists())
        self.assertTrue(newest.exists())

    def test_retained_file_replacement_invalidates_old_preview(self) -> None:
        self.backup(1)
        newest = self.backup(2)
        preview = self.retain()
        payload = newest.read_bytes()
        preserved = self.base / "preserved"
        newest.rename(preserved)
        newest.write_bytes(payload)
        newest.chmod(0o600)
        os.utime(newest, ns=(2, 2))
        with self.assertRaises(ValueError):
            self.apply(preview)

    def test_workspace_lock_and_storage_identity_changes_invalidate_review(
        self,
    ) -> None:
        self.backup(1)
        self.backup(2)
        preview = self.retain()
        self.workspace.rename(self.base / "old-project")
        self.workspace.mkdir()
        with self.assertRaises(ValueError):
            self.apply(preview)
        preview = self.retain()
        lock = self.storage / "memory.lock"
        lock.rename(self.storage / "old-lock")
        lock.touch(mode=0o600)
        with self.assertRaises(ValueError):
            self.apply(preview)
        preview = self.retain()
        prior = self.base / "old-storage"
        self.storage.rename(prior)
        self.storage.mkdir(mode=0o700)
        for path in prior.iterdir():
            copy = self.storage / path.name
            copy.write_bytes(path.read_bytes())
            copy.chmod(0o600)
        with self.assertRaises(ValueError):
            self.apply(preview)

    def test_unsafe_files_block_even_when_their_project_would_be_retained(self) -> None:
        path = self.backup(2, workspace=self.other)
        saved = self.base / "saved"
        path.rename(saved)
        for kind in ("symlink", "hardlink", "fifo", "directory", "public"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    path.symlink_to(saved)
                elif kind == "hardlink":
                    os.link(saved, path)
                elif kind == "fifo":
                    os.mkfifo(path, 0o600)
                elif kind == "directory":
                    path.mkdir(mode=0o700)
                else:
                    path.write_bytes(saved.read_bytes())
                    path.chmod(0o644)
                with self.assertRaises((OSError, ValueError)):
                    self.retain()
                if kind == "directory":
                    path.rmdir()
                else:
                    path.unlink()
        saved.rename(path)
        self.storage.chmod(0o755)
        with self.assertRaises(ValueError):
            self.retain()
        self.storage.chmod(0o700)

    def test_invalid_noncanonical_foreign_owner_and_user_records_block(self) -> None:
        original = self.backup(1)
        payload = original.read_bytes()
        for invalid in (
            b"broken",
            payload + b"\n",
            payload.replace(
                b'"schema_version":1', b'"schema_version":1,"schema_version":1'
            ),
        ):
            original.write_bytes(invalid)
            with self.assertRaises(ValueError):
                self.retain(0)
        original.unlink()
        for change in (
            {"owner_uid": os.getuid() + 1},
            {"scope": "user", "workspace": None},
        ):
            document = self.current.document.model_copy(update=change)
            snapshot = MemorySnapshot(
                document=document, sha256=digest(canonical_bytes(document))
            )
            path = self.backup(1, snapshot=snapshot)
            with self.assertRaises(ValueError):
                self.retain(0)
            path.unlink()
        unknown = self.storage / "resolution-backup-not-a-digest.json"
        unknown.write_bytes(payload)
        with self.assertRaisesRegex(ValueError, "filename"):
            self.retain(0)

    def test_record_and_total_byte_limits_reject_without_partial_inventory(
        self,
    ) -> None:
        path = self.backup(1)
        original = path.read_bytes()
        path.write_bytes(b"x" * (RECORD_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "byte limit"):
            self.retain()
        path.write_bytes(original)
        self.backup(2)
        self.assertEqual(MAX_INVENTORY_BYTES, 8 * 1024 * 1024)
        large: list[Path] = []
        for index in range(43):
            document = self.current.document.model_copy(
                update={
                    "revision": index + 2,
                    "text": "\x00" * 32700,
                }
            )
            snapshot = MemorySnapshot(
                document=document, sha256=digest(canonical_bytes(document))
            )
            large.append(self.backup(index + 10, snapshot=snapshot))
        self.assertGreater(
            sum(item.stat().st_size for item in large), MAX_INVENTORY_BYTES
        )
        with self.assertRaisesRegex(ValueError, "byte limit"):
            self.retain()
        large[-1].unlink()
        self.retain()

    def test_backup_count_and_directory_entry_limits_are_fail_closed(self) -> None:
        for index in range(MAX_BACKUPS):
            self.backup(index + 1)
        self.retain(128)
        extra = self.backup(MAX_BACKUPS + 1)
        with self.assertRaisesRegex(ValueError, "128"):
            self.retain()
        extra.unlink()
        existing = len(tuple(self.storage.iterdir()))
        for index in range(MAX_DIRECTORY_ENTRIES - existing):
            (self.storage / f"unrelated-{index}").touch()
        self.retain(128)
        (self.storage / "one-too-many").touch()
        with self.assertRaisesRegex(ValueError, "1,024"):
            self.retain()

    def test_wrong_content_address_cannot_enter_inventory(self) -> None:
        path = self.backup(1)
        renamed = self.storage / ("resolution-backup-" + "0" * 64 + ".json")
        path.rename(renamed)
        with self.assertRaisesRegex(ValueError, "canonical"):
            self.retain()

    def test_unlink_failure_before_progress_preserves_every_record(self) -> None:
        self.backup(1)
        self.backup(2)
        preview = self.retain()
        before = {item: item.read_bytes() for item in self.storage.iterdir()}
        with (
            patch(
                "mos_eisley.conversation_memory_retention.os.unlink",
                side_effect=OSError("unlink"),
            ),
            self.assertRaises(MemoryRetentionError) as failure,
        ):
            self.apply(preview)
        self.assertEqual(failure.exception.receipt["removed"], [])
        self.assertEqual(failure.exception.receipt["synced"], [])
        self.assertEqual(
            before, {item: item.read_bytes() for item in self.storage.iterdir()}
        )

    def test_inventory_change_during_scan_is_rejected(self) -> None:
        first = self.backup(1)
        second = self.backup(2)
        earlier = min((first, second), key=lambda item: item.name)
        original_stat = os.stat
        changed = False

        def mutate(
            path: str | Path, *, dir_fd: int | None = None, follow_symlinks: bool = True
        ) -> os.stat_result:
            nonlocal changed
            result = original_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)
            if str(path) == max(first.name, second.name) and not changed:
                changed = True
                os.utime(earlier, ns=(50, 50))
            return result

        with (
            patch(
                "mos_eisley.conversation_memory_retention.os.stat", side_effect=mutate
            ),
            self.assertRaises(ValueError),
        ):
            self.retain()
        self.assertTrue(changed)

    def test_apply_rechecks_protected_inventory_between_deletions(self) -> None:
        first = self.backup(1)
        second = self.backup(2)
        newest = self.backup(3)
        preview = self.retain()
        unlink = os.unlink

        def change_after_unlink(name: str, *, dir_fd: int | None = None) -> None:
            unlink(name, dir_fd=dir_fd)
            if name == first.name:
                os.utime(newest, ns=(8, 8))

        with (
            patch(
                "mos_eisley.conversation_memory_retention.os.unlink",
                side_effect=change_after_unlink,
            ),
            self.assertRaises(MemoryRetentionError) as failed,
        ):
            self.apply(preview)
        self.assertEqual(failed.exception.receipt["removed"], [first.name])
        self.assertEqual(failed.exception.receipt["synced"], [first.name])
        self.assertEqual(failed.exception.receipt["status"], "incomplete")
        self.assertTrue(second.exists())
        self.assertTrue(newest.exists())

    def test_flush_failure_reports_removed_but_not_synced(self) -> None:
        first = self.backup(1)
        self.backup(2)
        preview = self.retain()
        with (
            patch(
                "mos_eisley.conversation_memory_retention.os.fsync",
                side_effect=OSError("flush"),
            ),
            self.assertRaises(MemoryRetentionError) as failed,
        ):
            self.apply(preview)
        self.assertEqual(failed.exception.receipt["removed"], [first.name])
        self.assertEqual(failed.exception.receipt["synced"], [])
        self.assertFalse(first.exists())

    def test_process_death_after_unlink_requires_fresh_inventory(self) -> None:
        first = self.backup(1)
        second = self.backup(2)
        newest = self.backup(3)
        preview = self.retain()
        script = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_retention import retain_memory_backups
unlink = os.unlink
def die(name, *, dir_fd=None):
    unlink(name, dir_fd=dir_fd)
    os._exit(73)
with patch('mos_eisley.conversation_memory_retention.os.unlink', side_effect=die):
    retain_memory_backups(
        Path(sys.argv[1]), sys.argv[2], keep_newest=1, before_ns=100,
        expected_sha256=sys.argv[3],
    )
"""
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(self.storage),
                str(self.workspace),
                str(preview["preview_sha256"]),
            ],
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(child.returncode, 73, child.stderr)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        with self.assertRaises(ValueError):
            self.apply(preview)
        remaining = self.retain()
        self.assertEqual(remaining["selected"], [second.name])
        self.apply(remaining)
        self.assertTrue(newest.exists())
        self.assertEqual(self.store.read("project"), self.current)

    def test_review_is_bounded_to_32_deletions_with_fresh_remaining_plan(self) -> None:
        backups = [self.backup(index + 1) for index in range(35)]
        self.assertEqual(MAX_PRUNE, 32)
        preview = self.retain()
        self.assertEqual(preview["selected"], [path.name for path in backups[:32]])
        self.assertEqual(
            preview["remaining_eligible"], [path.name for path in backups[32:34]]
        )
        self.apply(preview)
        self.apply(self.retain())
        self.assertTrue(backups[-1].exists())
        self.assertEqual(self.retain()["selected"], [])

    def test_vanished_workspace_is_supported_and_alias_is_rejected(self) -> None:
        self.backup(1)
        self.backup(2)
        self.workspace.rmdir()
        receipt = self.retain()
        self.apply(receipt)
        self.assertFalse(self.workspace.exists())
        self.workspace.symlink_to(self.other, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.retain()

    def test_lock_contention_and_invalid_policy_cannot_mutate(self) -> None:
        self.backup(1)
        self.backup(2)
        preview = self.retain()
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(self.retain(), preview)
            with self.assertRaises(BlockingIOError):
                self.apply(preview)
        for keep, cutoff in ((-1, 100), (129, 100), (True, 100), (1, 0), (1, 2**63)):
            with self.assertRaises(ValueError):
                self.retain(keep, cutoff)
        with self.assertRaises(ValueError):
            self.retain(expected="BAD")
        absent = self.base / "absent"
        with self.assertRaises(ValueError):
            retain_memory_backups(
                absent, str(self.workspace), keep_newest=1, before_ns=100
            )
        self.assertFalse(absent.exists())

    def test_cli_preview_apply_and_incomplete_receipt(self) -> None:
        first = self.backup(1)
        self.backup(2)
        args = [
            "memory-project-retention",
            "--workspace-identity",
            str(self.workspace),
            "--memory-storage",
            str(self.storage),
            "--keep-newest",
            "1",
            "--before-ns",
            "100",
            "--json",
        ]
        command = [sys.executable, "-m", "mos_eisley.cli"]
        preview = subprocess.run(
            [*command, *args], capture_output=True, text=True, timeout=15
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        receipt = json.loads(preview.stdout)
        self.assertEqual(receipt["selected"], [first.name])
        rejected = subprocess.run(
            [*command, *args, "--apply"], capture_output=True, text=True, timeout=15
        )
        self.assertEqual(rejected.returncode, 2)
        output = io.StringIO()
        namespace = argparse.Namespace(
            workspace_identity=str(self.workspace),
            memory_storage=self.storage,
            keep_newest=1,
            before_ns=100,
            expected_sha256=receipt["preview_sha256"],
            apply=True,
            json=True,
        )
        with (
            patch(
                "mos_eisley.conversation_memory_retention.os.fsync",
                side_effect=OSError("flush"),
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(run_command(namespace), 2)
        incomplete = json.loads(output.getvalue())
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertEqual(incomplete["removed"], [first.name])
        self.assertEqual(incomplete["synced"], [])
        fresh = json.loads(
            subprocess.run(
                [*command, *args],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            ).stdout
        )
        applied = subprocess.run(
            [*command, *args, "--apply", "--expected-sha256", fresh["preview_sha256"]],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(json.loads(applied.stdout)["status"], "completed")
