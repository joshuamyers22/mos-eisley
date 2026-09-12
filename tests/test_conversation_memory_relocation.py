"""Relocation binds exact old identities without relaxing ordinary memory access."""

import fcntl
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_memory import MemorySnapshot, MemoryStore
from mos_eisley.conversation_memory_identity import RelocationSource
from mos_eisley.conversation_memory_migration import (
    migrate_memory_project,
    relocate_memory_project,
)
from mos_eisley.core.models import canonical_bytes, digest


class MemoryRelocationTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.old = self.base / "previous" / "project"
        self.old.mkdir(parents=True)
        self.new = self.base / "destination"
        self.new.mkdir()
        self.storage = self.base / "memory"
        self.source = MemoryStore(self.storage, self.old)
        self.target = MemoryStore(self.storage, self.new)

    def preview(self) -> dict[str, object]:
        return relocate_memory_project(self.storage, str(self.old), self.new)

    def apply(self, preview: dict[str, object]) -> dict[str, object]:
        return relocate_memory_project(
            self.storage,
            str(self.old),
            self.new,
            expected_sha256=str(preview["preview_sha256"]),
        )

    def seed(self) -> dict[str, object]:
        self.source.change("project", "set", text="Keep these project decisions")
        self.old.rmdir()
        return self.preview()

    def test_absent_nested_source_and_storage_preview_create_nothing(self) -> None:
        self.old.rmdir()
        self.old.parent.rmdir()
        preview = self.preview()
        self.assertEqual(preview["status"], "empty")
        self.assertFalse(preview["can_apply"])
        self.assertEqual(preview, self.preview())
        with self.assertRaisesRegex(ValueError, "absent target"):
            self.apply(preview)
        self.assertFalse(self.storage.exists())
        self.assertFalse(self.old.parent.exists())
        with self.assertRaisesRegex(ValueError, "directory"):
            MemoryStore(self.storage, self.old)

    def test_vanished_source_copy_preserves_exact_old_and_user_records(self) -> None:
        self.seed()
        self.source.change("project", "disable")
        self.source.change("user", "set", text="Personal preferences")
        original = {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.storage.iterdir()
        }
        preview = self.preview()
        self.assertEqual(preview["operation"], "relocate-project-memory")
        identity = RelocationSource.inspect(str(self.old))
        self.assertFalse(identity.exists)
        self.assertEqual(preview["source_directory"], identity.receipt())
        proposed = MemorySnapshot.model_validate_json(json.dumps(preview["proposed"]))
        self.assertTrue(self.apply(preview)["applied"])
        self.assertEqual(
            self.target.path("project").read_bytes(), canonical_bytes(proposed)
        )
        self.assertEqual(proposed.document.workspace, str(self.new))
        self.assertEqual(proposed.document.revision, 1)
        self.assertFalse(proposed.document.enabled)
        self.assertEqual(self.target.path("project").stat().st_nlink, 1)
        self.assertEqual(self.target.path("project").stat().st_mode & 0o777, 0o600)
        for name, before in original.items():
            path = self.storage / name
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.assertFalse(self.old.exists())
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(preview)

    def test_existing_unrelated_identity_can_copy_empty_memory(self) -> None:
        self.source.change("project", "set", text="")
        preview = self.preview()
        self.assertTrue(RelocationSource.inspect(str(self.old)).exists)
        self.apply(preview)
        copied = self.target.read("project")
        assert copied is not None
        self.assertEqual(copied.document.text, "")
        self.assertTrue(self.old.is_dir())

    def test_exact_identity_rejects_normalization_aliases_and_non_directories(
        self,
    ) -> None:
        alias = self.base / "alias"
        alias.symlink_to(self.old.parent, target_is_directory=True)
        dangling = self.base / "dangling"
        dangling.symlink_to(self.base / "absent")
        file = self.base / "file"
        file.touch()
        for identity in (
            "relative",
            "~/project",
            str(self.old) + "/",
            str(self.old) + "/.",
            str(self.old) + "/../project",
            "/" + str(self.old),
            str(alias / "project"),
            str(alias / "missing"),
            str(dangling),
            str(file),
            str(file / "missing"),
            str(self.base) + "/line\nbreak",
            "/" + "x" * 4096,
        ):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                relocate_memory_project(self.storage, identity, self.new)
        self.assertFalse(self.storage.exists())

    def test_source_reappearance_and_missing_ancestor_creation_stale_preview(
        self,
    ) -> None:
        preview = self.seed()
        self.old.mkdir()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(preview)
        existing = self.preview()
        self.old.rmdir()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(existing)
        self.old.parent.rmdir()
        preview = self.preview()
        self.old.parent.mkdir()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(preview)
        self.assertFalse(self.target.path("project").exists())

    def test_anchor_target_and_lock_replacement_invalidate_receipt(self) -> None:
        self.seed()
        for path in (self.old.parent, self.new, self.storage / "memory.lock"):
            with self.subTest(path=path):
                preview = self.preview()
                moved = path.with_name(path.name + "-saved")
                path.rename(moved)
                if moved.is_dir():
                    path.mkdir()
                else:
                    path.touch(mode=0o600)
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.apply(preview)
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink()
                moved.rename(path)
        self.assertFalse(self.target.path("project").exists())

    def test_identical_source_record_replacement_stales_receipt(self) -> None:
        preview = self.seed()
        path = self.source.path("project")
        replacement = self.storage / "replacement"
        replacement.write_bytes(path.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, path)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(preview)
        self.assertFalse(self.target.path("project").exists())

    def test_changed_source_and_existing_disabled_target_are_rejected(self) -> None:
        preview = self.seed()
        self.source.change("project", "append", text="Changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(preview)
        preview = self.preview()
        self.target.change("project", "disable")
        original = self.target.path("project").read_bytes()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(preview)
        collision = self.preview()
        self.assertEqual(collision["status"], "collision")
        with self.assertRaisesRegex(ValueError, "absent target"):
            self.apply(collision)
        self.assertEqual(self.target.path("project").read_bytes(), original)

    def test_invalid_source_records_fail_closed(self) -> None:
        self.seed()
        path = self.source.path("project")
        original = path.read_bytes()
        for field, value in (
            ("workspace", str(self.new)),
            ("owner_uid", os.getuid() + 1),
        ):
            # Recompute an internally valid hash so identity checks do the rejection.
            snapshot = self.source.read("project")
            assert snapshot is not None
            changed = snapshot.document.model_copy(update={field: value})
            path.write_bytes(
                canonical_bytes(
                    MemorySnapshot(
                        document=changed, sha256=digest(canonical_bytes(changed))
                    )
                )
            )
            with self.assertRaises(ValueError):
                self.preview()
            path.write_bytes(original)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.preview()
        path.chmod(0o600)
        extra = self.storage / "extra"
        os.link(path, extra)
        with self.assertRaises(ValueError):
            self.preview()
        extra.unlink()
        path.rename(extra)
        path.symlink_to(extra)
        with self.assertRaises((OSError, ValueError)):
            self.preview()
        self.assertFalse(self.target.path("project").exists())

    def test_source_reappearing_at_staging_flush_blocks_publication(self) -> None:
        preview = self.seed()
        fsync = os.fsync

        def reappear(fd: int) -> None:
            fsync(fd)
            self.old.mkdir()

        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.fsync",
                side_effect=reappear,
            ),
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            self.apply(preview)
        self.assertFalse(self.target.path("project").exists())
        self.assertFalse(list(self.storage.glob(".memory-migration-*")))

    def test_shared_lock_blocks_apply(self) -> None:
        preview = self.seed()
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(self.preview(), preview)
            with self.assertRaises(BlockingIOError):
                self.apply(preview)
        self.assertFalse(self.target.path("project").exists())

    def test_receipts_are_bound_to_operation_and_destination(self) -> None:
        self.source.change("project", "set", text="Decisions")
        ancestor = migrate_memory_project(self.storage, self.old, self.old.parent)
        with self.assertRaisesRegex(ValueError, "changed"):
            relocate_memory_project(
                self.storage,
                str(self.old),
                self.old.parent,
                expected_sha256=str(ancestor["preview_sha256"]),
            )
        preview = self.preview()
        with self.assertRaisesRegex(ValueError, "changed"):
            relocate_memory_project(
                self.storage,
                str(self.old),
                self.old.parent,
                expected_sha256=str(preview["preview_sha256"]),
            )
        with self.assertRaisesRegex(ValueError, "distinct"):
            relocate_memory_project(self.storage, str(self.old), self.old)

    def test_storage_flush_failure_leaves_published_copy_for_inspection(self) -> None:
        preview = self.seed()
        fsync = os.fsync

        def fail_directory(fd: int) -> None:
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("directory flush failed")
            fsync(fd)

        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.fsync",
                side_effect=fail_directory,
            ),
            self.assertRaisesRegex(OSError, "flush failed"),
        ):
            self.apply(preview)
        self.assertIsNotNone(self.target.read("project"))
        with self.assertRaisesRegex(ValueError, "changed"):
            self.apply(preview)

    def test_process_death_recovery_works_with_vanished_source(self) -> None:
        preview = self.seed()
        original = self.source.path("project").read_bytes()
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_migration import relocate_memory_project
link = os.link
def interrupted(*args, **kwargs):
    link(*args, **kwargs)
    os._exit(77)
with patch('mos_eisley.conversation_memory_migration.os.link', side_effect=interrupted):
    relocate_memory_project(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]),
                            expected_sha256=sys.argv[4])
"""
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(self.storage),
                str(self.old),
                str(self.new),
                str(preview["preview_sha256"]),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(process.returncode, 77, process.stderr)
        with self.assertRaises(ValueError):
            self.target.read("project")
        aliases = list(self.storage.glob(".memory-migration-*"))
        self.assertEqual(len(aliases), 1)
        proposed = MemorySnapshot.model_validate_json(json.dumps(preview["proposed"]))

        def recover(expected: str | None = None) -> dict[str, object]:
            return relocate_memory_project(
                self.storage,
                str(self.old),
                self.new,
                temporary_name=aliases[0].name,
                target_sha256=proposed.sha256,
                expected_sha256=expected,
            )

        receipt = recover()
        self.assertEqual(receipt["operation"], "recover-relocated-project-memory-link")
        with self.assertRaisesRegex(ValueError, "changed"):
            recover(str(preview["preview_sha256"]))
        self.old.mkdir()
        with self.assertRaisesRegex(ValueError, "changed"):
            recover(str(receipt["preview_sha256"]))
        self.old.rmdir()
        receipt = recover()
        self.assertTrue(recover(str(receipt["preview_sha256"]))["applied"])
        self.assertEqual(self.target.read("project"), proposed)
        self.assertEqual(self.source.path("project").read_bytes(), original)
        self.assertFalse(aliases[0].exists())
        self.assertFalse(self.old.exists())

    def test_cli_requires_paired_apply_and_recovery_flags(self) -> None:
        preview = self.seed()

        def launch(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "memory-project-relocate",
                    "--from-workspace",
                    str(self.old),
                    "--to-workspace",
                    str(self.new),
                    "--memory-storage",
                    str(self.storage),
                    "--json",
                    *args,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

        for args in (
            ("--apply",),
            ("--expected-sha256", str(preview["preview_sha256"])),
            ("--temporary-name", "wrong"),
            ("--target-sha256", "0" * 64),
            ("--temporary-name", "../bad", "--target-sha256", "0" * 64),
            ("--apply", "--expected-sha256", "BAD"),
        ):
            result = launch(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.target.path("project").exists())
        result = launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["preview_sha256"], preview["preview_sha256"]
        )
        result = launch("--apply", "--expected-sha256", str(preview["preview_sha256"]))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["applied"])
