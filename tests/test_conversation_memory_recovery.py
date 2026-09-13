"""Exact alias recovery never deletes or replaces a memory document."""

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

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot, MemoryStore
from mos_eisley.conversation_memory_migration import (
    migrate_memory_project,
    recover_memory_project,
)
from mos_eisley.core.models import canonical_bytes, digest


class MemoryRecoveryTests(TestCase):
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
        self.alias = self.storage / (".memory-migration-" + "a" * 32 + ".tmp")
        self.target_hash = "0" * 64
        self.copy_hash = "0" * 64

    def seed(self) -> dict[str, object]:
        self.source.change("project", "set", text="Original copied preference")
        self.source.change("user", "set", text="Personal preference")
        receipt = migrate_memory_project(self.storage, self.workspace, self.project)
        self.copy_hash = str(receipt["preview_sha256"])
        migrate_memory_project(
            self.storage,
            self.workspace,
            self.project,
            expected_sha256=str(receipt["preview_sha256"]),
        )
        snapshot = self.target.read("project")
        assert snapshot is not None
        self.target_hash = snapshot.sha256
        os.link(self.target.path("project"), self.alias)
        return self.preview()

    def preview(self) -> dict[str, object]:
        return recover_memory_project(
            self.storage,
            self.workspace,
            self.project,
            temporary_name=self.alias.name,
            target_sha256=self.target_hash,
        )

    def apply(self, receipt: dict[str, object]) -> dict[str, object]:
        return recover_memory_project(
            self.storage,
            self.workspace,
            self.project,
            temporary_name=self.alias.name,
            target_sha256=self.target_hash,
            expected_sha256=str(receipt["preview_sha256"]),
        )

    def test_preview_read_only_and_apply_removes_only_exact_alias(self) -> None:
        receipt = self.seed()
        before = {
            p.name: (p.read_bytes(), p.stat().st_mtime_ns)
            for p in self.storage.iterdir()
        }
        self.assertEqual(receipt, self.preview())
        self.assertFalse(receipt["applied"])
        with self.assertRaisesRegex(ValueError, "private"):
            self.target.read("project")
        result = self.apply(receipt)
        self.assertTrue(result["applied"])
        self.assertFalse(self.alias.exists())
        self.assertEqual(self.target.path("project").stat().st_nlink, 1)
        self.assertIsNotNone(self.target.read("project"))
        for name, value in before.items():
            if name != self.alias.name:
                path = self.storage / name
                self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), value)
        with self.assertRaises(ValueError):
            self.apply(receipt)

    def test_source_can_change_without_recovery_overwriting_it(self) -> None:
        receipt = self.seed()
        self.source.change("project", "append", text="Later workspace preference")
        before = self.source.path("project").read_bytes()
        self.apply(receipt)
        self.assertEqual(self.source.path("project").read_bytes(), before)
        snapshot = self.target.read("project")
        assert snapshot is not None
        self.assertEqual(snapshot.document.text, "Original copied preference")

    def test_missing_storage_and_invalid_names_create_nothing(self) -> None:
        with self.assertRaisesRegex(ValueError, "existing"):
            self.preview()
        for name in (
            "../target",
            "memory.lock",
            "/tmp/file",
            ".memory-migration-x.tmp",
        ):
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(ValueError, "filename"),
            ):
                recover_memory_project(
                    self.storage,
                    self.workspace,
                    self.project,
                    temporary_name=name,
                    target_sha256=self.target_hash,
                )
        self.assertFalse(self.storage.exists())

    def test_wrong_hash_and_copy_preview_hash_cannot_authorize_recovery(self) -> None:
        receipt = self.seed()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply({"preview_sha256": self.copy_hash})
        original = self.target_hash
        self.target_hash = "0" * 64
        with self.assertRaisesRegex(ValueError, "approved"):
            self.preview()
        self.target_hash = "bad"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.preview()
        self.target_hash = original
        self.assertEqual(receipt, self.preview())

    def test_extra_links_and_single_link_records_are_rejected(self) -> None:
        receipt = self.seed()
        extra = self.base / "extra"
        os.link(self.alias, extra)
        with self.assertRaisesRegex(ValueError, "two links"):
            self.apply(receipt)
        extra.unlink()
        self.alias.unlink()
        with self.assertRaisesRegex(ValueError, "two links"):
            self.preview()
        self.assertIsNotNone(self.target.read("project"))

    def test_wrong_file_and_symlink_alias_are_preserved(self) -> None:
        self.seed()
        extra = self.base / "real-alias"
        self.alias.rename(extra)
        self.alias.write_text("unrelated", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exact target"):
            self.preview()
        self.assertEqual(self.alias.read_text(), "unrelated")
        self.alias.unlink()
        self.alias.symlink_to(extra)
        with self.assertRaisesRegex(ValueError, "exact target"):
            self.preview()
        self.assertTrue(self.alias.is_symlink())

    def test_target_symlink_and_unsafe_permissions_are_rejected(self) -> None:
        receipt = self.seed()
        self.alias.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "private"):
            self.apply(receipt)
        self.alias.chmod(0o600)
        target = self.target.path("project")
        moved = self.storage / "real-target"
        target.rename(moved)
        target.symlink_to(moved)
        with self.assertRaises(OSError):
            self.preview()
        self.assertTrue(target.is_symlink())
        self.assertTrue(self.alias.exists())

    def test_changed_record_and_noncanonical_bytes_block_apply(self) -> None:
        receipt = self.seed()
        payload = self.alias.read_bytes()
        self.alias.write_bytes(payload + b"\n")
        with self.assertRaisesRegex(ValueError, "approved"):
            self.apply(receipt)
        self.alias.write_bytes(payload)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(receipt)
        self.alias.write_bytes(b"x" * (RECORD_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "byte limit"):
            self.preview()

    def test_replaced_alias_invalidates_receipt_even_with_same_bytes(self) -> None:
        receipt = self.seed()
        self.alias.unlink()
        os.link(self.target.path("project"), self.alias)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(receipt)
        self.apply(self.preview())

    def test_replaced_directory_storage_or_lock_invalidates_receipt(self) -> None:
        self.seed()
        for path in (self.workspace, self.project, self.storage / "memory.lock"):
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
        receipt = self.preview()
        moved = self.storage.with_name("old-memory")
        self.storage.rename(moved)
        self.storage.mkdir(mode=0o700)
        for path in moved.iterdir():
            path.rename(self.storage / path.name)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(receipt)
        self.assertTrue(self.alias.exists())

    def test_apply_requires_exclusive_lock(self) -> None:
        receipt = self.seed()
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(self.preview(), receipt)
            with self.assertRaises(BlockingIOError):
                self.apply(receipt)
        self.assertTrue(self.alias.exists())

    def test_unlink_failure_preserves_pair_and_durability_failure_preserves_target(
        self,
    ) -> None:
        receipt = self.seed()
        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.unlink",
                side_effect=OSError("unlink"),
            ),
            self.assertRaisesRegex(OSError, "unlink"),
        ):
            self.apply(receipt)
        self.assertEqual(receipt, self.preview())
        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.fsync",
                side_effect=OSError("sync"),
            ),
            self.assertRaisesRegex(OSError, "sync"),
        ):
            self.apply(receipt)
        self.assertFalse(self.alias.exists())
        self.assertIsNotNone(self.target.read("project"))
        with self.assertRaisesRegex(ValueError, "two links"):
            self.apply(receipt)

    def test_cli_preview_apply_and_paired_flags(self) -> None:
        receipt = self.seed()
        args = [
            sys.executable,
            "-m",
            "mos_eisley.cli",
            "memory-project-recover",
            "-C",
            str(self.workspace),
            "--memory-project-root",
            str(self.project),
            "--memory-storage",
            str(self.storage),
            "--temporary-name",
            self.alias.name,
            "--target-sha256",
            self.target_hash,
            "--json",
        ]
        for flags in (
            ("--apply",),
            ("--expected-sha256", str(receipt["preview_sha256"])),
        ):
            result = subprocess.run(
                [*args, *flags], capture_output=True, text=True, timeout=15
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(self.alias.exists())
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout), {"type": "memory.project_recovery", **receipt}
        )
        result = subprocess.run(
            [*args, "--apply", "--expected-sha256", str(receipt["preview_sha256"])],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["applied"])
        expected = MemorySnapshot.model_validate_json(json.dumps(receipt["target"]))
        self.assertEqual(
            self.target.path("project").read_bytes(), canonical_bytes(expected)
        )

    def test_foreign_scope_or_owner_is_rejected_even_with_matching_hash(self) -> None:
        receipt = self.seed()
        original = MemorySnapshot.model_validate_json(json.dumps(receipt["target"]))
        for update in (
            {"workspace": str(self.workspace)},
            {"owner_uid": os.getuid() + 1},
            {"scope": "user", "workspace": None},
        ):
            with self.subTest(update=update):
                document = original.document.model_copy(update=update)
                changed = MemorySnapshot(
                    document=document, sha256=digest(canonical_bytes(document))
                )
                self.alias.write_bytes(canonical_bytes(changed))
                self.target_hash = changed.sha256
                with self.assertRaisesRegex(ValueError, "approved"):
                    self.preview()
                self.assertTrue(self.alias.exists())

    def test_alias_changed_during_final_recheck_is_not_removed(self) -> None:
        receipt = self.seed()
        original_stat = os.stat
        calls = 0

        def inspect(
            path: str | bytes | os.PathLike[str] | os.PathLike[bytes] | int,
            *,
            dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> os.stat_result:
            nonlocal calls
            if path == self.alias.name:
                calls += 1
                if calls == 2:
                    self.alias.rename(self.base / "retained-alias")
                    self.alias.write_text("unrelated replacement", encoding="utf-8")
            return original_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.stat", side_effect=inspect
            ),
            self.assertRaisesRegex(ValueError, "exact target"),
        ):
            self.apply(receipt)
        self.assertEqual(self.alias.read_text(), "unrelated replacement")
        self.assertTrue(self.target.path("project").exists())
