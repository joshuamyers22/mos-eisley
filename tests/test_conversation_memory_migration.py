"""Migration receipts bind content and filesystem identities before publication."""

import fcntl
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_memory import MemorySnapshot, MemoryStore
from mos_eisley.conversation_memory_migration import migrate_memory_project
from mos_eisley.conversation_memory_project import preview_memory_project
from mos_eisley.core.models import canonical_bytes


class MemoryMigrationTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "project" / "child"
        self.workspace.mkdir(parents=True)
        self.project = self.workspace.parent
        self.storage = self.base / "memory"
        self.source = MemoryStore(self.storage, self.workspace)
        self.target = MemoryStore(self.storage, self.project)

    def preview(self) -> dict[str, object]:
        return migrate_memory_project(self.storage, self.workspace, self.project)

    def apply(self, receipt: dict[str, object]) -> dict[str, object]:
        return migrate_memory_project(
            self.storage,
            self.workspace,
            self.project,
            expected_sha256=str(receipt["preview_sha256"]),
        )

    def seed(self, text: str = "Project decisions") -> dict[str, object]:
        self.source.change("project", "set", text=text)
        return self.preview()

    def launch(self, *options: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "memory-project-migrate",
                "-C",
                str(self.workspace),
                "--memory-project-root",
                str(self.project),
                "--memory-storage",
                str(self.storage),
                "--json",
                *options,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_missing_storage_preview_and_rejected_apply_create_nothing(self) -> None:
        receipt = self.preview()
        self.assertEqual(receipt["status"], "empty")
        self.assertFalse(receipt["can_apply"])
        with self.assertRaisesRegex(ValueError, "absent target"):
            self.apply(receipt)
        self.assertFalse(self.storage.exists())

    def test_copy_matches_proposal_and_preserves_source_and_user_bytes(self) -> None:
        self.seed()
        self.source.change("project", "disable")
        self.source.change("user", "set", text="User instructions")
        receipt = self.preview()
        original = {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.storage.iterdir()
        }
        self.assertEqual(receipt, self.preview())
        result = self.apply(receipt)
        self.assertTrue(result["applied"])
        snapshot = MemorySnapshot.model_validate_json(json.dumps(receipt["proposed"]))
        self.assertEqual(
            self.target.path("project").read_bytes(), canonical_bytes(snapshot)
        )
        self.assertEqual(snapshot.document.revision, 1)
        self.assertFalse(snapshot.document.enabled)
        loaded = self.target.load()
        assert loaded is not None
        self.assertIsNone(loaded.project)
        self.assertIsNotNone(loaded.user)
        self.assertEqual(self.target.path("project").stat().st_nlink, 1)
        self.assertEqual(self.target.path("project").stat().st_mode & 0o777, 0o600)
        for name, before in original.items():
            path = self.storage / name
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(receipt)
        self.assertFalse(list(self.storage.glob(".memory-migration-*")))

    def test_empty_source_is_copied_as_an_existing_document(self) -> None:
        receipt = self.seed("")
        self.apply(receipt)
        target = self.target.read("project")
        assert target is not None
        self.assertEqual(target.document.text, "")
        self.assertIsNone(self.target.load())

    def test_source_changes_and_old_informational_hash_are_rejected(self) -> None:
        receipt = self.seed()
        old = preview_memory_project(self.storage, self.workspace, self.project)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(old)
        self.source.change("project", "append", text="Later decision")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(receipt)
        self.assertFalse(self.target.path("project").exists())
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.apply({"preview_sha256": "not-a-hash"})

    def test_collisions_including_disabled_empty_targets_are_never_overwritten(
        self,
    ) -> None:
        receipt = self.seed()
        self.target.change("project", "disable")
        before = self.target.path("project").read_bytes()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(receipt)
        collision = self.preview()
        self.assertEqual(collision["status"], "collision")
        with self.assertRaisesRegex(ValueError, "absent target"):
            self.apply(collision)
        self.assertEqual(self.target.path("project").read_bytes(), before)

    def test_same_identity_and_target_only_are_not_applicable(self) -> None:
        self.seed()
        same = migrate_memory_project(self.storage, self.workspace, self.workspace)
        self.assertEqual(same["status"], "same-identity")
        self.assertFalse(same["can_apply"])
        self.target.change("project", "set", text="Root")
        self.source.path("project").unlink()
        receipt = self.preview()
        self.assertEqual(receipt["status"], "target-only")
        with self.assertRaisesRegex(ValueError, "absent target"):
            self.apply(receipt)

    def test_replaced_directory_storage_and_lock_invalidate_receipt(self) -> None:
        self.seed()
        for path in (
            self.workspace,
            self.project,
            self.storage,
            self.storage / "memory.lock",
        ):
            with self.subTest(path=path):
                receipt = self.preview()
                moved = path.with_name(path.name + "-old")
                path.rename(moved)
                if moved.is_dir():
                    shutil.copytree(moved, path)
                else:
                    shutil.copy2(moved, path)
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.apply(receipt)
                self.assertFalse(self.target.path("project").exists())

    def test_unsafe_storage_source_and_target_are_rejected_without_writes(self) -> None:
        receipt = self.seed()
        self.storage.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "private"):
            self.apply(receipt)
        self.storage.chmod(0o700)
        source = self.source.path("project")
        original = source.read_bytes()
        alias = self.base / "linked-source"
        os.link(source, alias)
        with self.assertRaisesRegex(ValueError, "private"):
            self.apply(receipt)
        alias.unlink()
        self.target.path("project").symlink_to(source)
        with self.assertRaises(OSError):
            self.apply(receipt)
        self.assertEqual(source.read_bytes(), original)
        self.assertTrue(self.target.path("project").is_symlink())

    def test_apply_requires_exclusive_lock_and_does_not_wait(self) -> None:
        receipt = self.seed()
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(self.preview(), receipt)
            with self.assertRaises(BlockingIOError):
                self.apply(receipt)
        self.assertFalse(self.target.path("project").exists())

    def test_racing_target_at_publication_is_not_overwritten(self) -> None:
        receipt = self.seed()
        link = os.link
        target = self.target.path("project")

        def race(
            src: str,
            dst: str,
            *,
            src_dir_fd: int,
            dst_dir_fd: int,
            follow_symlinks: bool,
        ) -> None:
            target.write_text("concurrent target", encoding="utf-8")
            link(
                src,
                dst,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )

        with (
            patch("mos_eisley.conversation_memory_migration.os.link", side_effect=race),
            self.assertRaises(FileExistsError),
        ):
            self.apply(receipt)
        self.assertEqual(target.read_text(), "concurrent target")
        self.assertFalse(list(self.storage.glob(".memory-migration-*")))

    def test_write_failure_cleans_temporary_and_leaves_source_untouched(self) -> None:
        receipt = self.seed()
        before = self.source.path("project").read_bytes()
        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.fsync",
                side_effect=OSError("disk"),
            ),
            self.assertRaisesRegex(OSError, "disk"),
        ):
            self.apply(receipt)
        self.assertFalse(self.target.path("project").exists())
        self.assertEqual(self.source.path("project").read_bytes(), before)
        self.assertFalse(list(self.storage.glob(".memory-migration-*")))
        self.apply(receipt)

    def test_durability_failure_preserves_published_target_and_blocks_retry(
        self,
    ) -> None:
        receipt = self.seed()
        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.fsync",
                side_effect=[None, OSError("disk")],
            ),
            self.assertRaisesRegex(OSError, "disk"),
        ):
            self.apply(receipt)
        self.assertIsNotNone(self.target.read("project"))
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(receipt)
        self.assertFalse(list(self.storage.glob(".memory-migration-*")))

    def test_cli_requires_paired_apply_flags_and_emits_exact_preview(self) -> None:
        receipt = self.seed()
        for flags in (
            ("--apply",),
            ("--expected-sha256", str(receipt["preview_sha256"])),
        ):
            result = self.launch(*flags)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.target.path("project").exists())
        preview = self.launch()
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(
            json.loads(preview.stdout), {"type": "memory.project_migration", **receipt}
        )
        result = self.launch(
            "--apply", "--expected-sha256", str(receipt["preview_sha256"])
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["applied"])

    def test_lock_replaced_during_staging_prevents_publication(self) -> None:
        receipt = self.seed()
        fsync = os.fsync

        def replace_lock(fd: int) -> None:
            fsync(fd)
            lock = self.storage / "memory.lock"
            lock.rename(self.storage / "old.lock")
            lock.touch(mode=0o600)

        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.fsync",
                side_effect=replace_lock,
            ),
            self.assertRaisesRegex(ValueError, "lock changed"),
        ):
            self.apply(receipt)
        self.assertFalse(self.target.path("project").exists())
        self.assertFalse(list(self.storage.glob(".memory-migration-*")))

    def test_source_changed_during_staging_prevents_publication(self) -> None:
        receipt = self.seed()
        newer = self.source.change("project", "append", text="New decision")
        old = MemorySnapshot.model_validate_json(json.dumps(receipt["source"]))
        self.source.path("project").write_bytes(canonical_bytes(old))
        fsync = os.fsync

        def change_source(fd: int) -> None:
            fsync(fd)
            self.source.path("project").write_bytes(canonical_bytes(newer))

        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.fsync",
                side_effect=change_source,
            ),
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            self.apply(receipt)
        self.assertFalse(self.target.path("project").exists())
        self.assertEqual(self.source.read("project"), newer)
        self.assertFalse(list(self.storage.glob(".memory-migration-*")))

    def test_process_death_after_link_fails_closed_and_preserves_source(self) -> None:
        receipt = self.seed()
        original = self.source.path("project").read_bytes()
        code = """
import os
import sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_migration import migrate_memory_project
link = os.link
def interrupted(*args, **kwargs):
    link(*args, **kwargs)
    os._exit(77)
with patch('mos_eisley.conversation_memory_migration.os.link', side_effect=interrupted):
    migrate_memory_project(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]),
                           expected_sha256=sys.argv[4])
"""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(self.storage),
                str(self.workspace),
                str(self.project),
                str(receipt["preview_sha256"]),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertEqual(self.source.path("project").read_bytes(), original)
        with self.assertRaisesRegex(ValueError, "private"):
            self.target.read("project")
        with self.assertRaisesRegex(ValueError, "private"):
            self.apply(receipt)
        # Model operator recovery: validate the exact target and its one staging alias.
        aliases = list(self.storage.glob(".memory-migration-*"))
        self.assertEqual(len(aliases), 1)
        self.assertTrue(aliases[0].samefile(self.target.path("project")))
        proposed = MemorySnapshot.model_validate_json(json.dumps(receipt["proposed"]))
        self.assertEqual(aliases[0].read_bytes(), canonical_bytes(proposed))
        aliases[0].unlink()
        self.assertEqual(self.target.read("project"), proposed)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(receipt)
