"""Cleanup deletes only an exact reviewed staging name and retains live memory."""

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

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot, MemoryStore
from mos_eisley.conversation_memory_cleanup import cleanup_memory_project
from mos_eisley.core.models import canonical_bytes, digest


class MemoryCleanupTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        self.storage = self.base / "memory"
        self.store = MemoryStore(self.storage, self.workspace)
        self.name = ".memory-resolution-" + "1" * 32 + ".tmp"

    def seed(self, *, linked: bool = False) -> tuple[MemorySnapshot, str | None]:
        snapshot = self.store.change(
            "project", "set", text="Preserved project decisions"
        )
        self.store.change("user", "set", text="Private preferences")
        if linked:
            self.name = ".memory-migration-" + "1" * 32 + ".tmp"
        staging = self.storage / self.name
        staging.write_bytes(canonical_bytes(snapshot))
        staging.chmod(0o600)
        backup = (
            "resolution-backup-" + digest(canonical_bytes(snapshot)) + ".json"
            if linked
            else None
        )
        if backup:
            os.link(staging, self.storage / backup)
        return snapshot, backup

    def cleanup(
        self,
        snapshot: MemorySnapshot,
        backup: str | None = None,
        *,
        receipt: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return cleanup_memory_project(
            self.storage,
            str(self.workspace),
            action="recover-backup-link" if backup else "discard-staging",
            temporary_name=self.name,
            record_sha256=snapshot.sha256,
            backup_name=backup,
            expected_sha256=str(receipt["preview_sha256"]) if receipt else None,
        )

    def test_single_file_discard_preserves_live_memory_user_and_unselected_files(
        self,
    ) -> None:
        snapshot, _ = self.seed()
        unrelated = self.storage / (".memory-resolution-" + "2" * 32 + ".tmp")
        unrelated.write_bytes(b"incomplete unrelated staging")
        before = {
            p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.storage.iterdir()
        }
        receipt = self.cleanup(snapshot)
        self.assertEqual(receipt, self.cleanup(snapshot))
        self.assertEqual(receipt["current_project"], snapshot.model_dump(mode="json"))
        self.assertEqual(receipt["record"], snapshot.model_dump(mode="json"))
        self.assertIsNone(receipt["removed"])
        self.assertEqual(
            before,
            {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.storage.iterdir()},
        )
        result = self.cleanup(snapshot, receipt=receipt)
        self.assertTrue(result["applied"])
        self.assertEqual(result["removed"], self.name)
        for path, value in before.items():
            if path.name != self.name:
                self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), value)
        self.assertFalse((self.storage / self.name).exists())
        with self.assertRaises(FileNotFoundError):
            self.cleanup(snapshot, receipt=receipt)

    def test_backup_recovery_preserves_exact_backup_and_current_newer_memory(
        self,
    ) -> None:
        snapshot, backup = self.seed(linked=True)
        assert backup is not None
        current = self.store.change("project", "append", text="Later edits")
        self.workspace.rmdir()
        before = (self.storage / backup).read_bytes()
        receipt = self.cleanup(snapshot, backup)
        self.assertEqual(receipt["current_project"], current.model_dump(mode="json"))
        result = self.cleanup(snapshot, backup, receipt=receipt)
        self.assertTrue(result["applied"])
        self.assertEqual((self.storage / backup).read_bytes(), before)
        self.assertEqual((self.storage / backup).stat().st_nlink, 1)
        self.assertEqual(self.store.read("project"), current)
        self.assertFalse(self.workspace.exists())
        self.assertFalse((self.storage / self.name).exists())

    def test_missing_storage_stays_absent(self) -> None:
        with self.assertRaisesRegex(ValueError, "existing memory storage"):
            cleanup_memory_project(
                self.storage,
                str(self.workspace),
                action="discard-staging",
                temporary_name=self.name,
                record_sha256="0" * 64,
            )
        self.assertFalse(self.storage.exists())

    def test_missing_current_document_is_visible_and_not_created(self) -> None:
        snapshot, _ = self.seed()
        self.store.path("project").unlink()
        self.workspace.rmdir()
        receipt = self.cleanup(snapshot)
        self.assertIsNone(receipt["current_project"])
        self.assertIsNone(receipt["current_record_identity"])
        self.cleanup(snapshot, receipt=receipt)
        self.assertFalse(self.store.path("project").exists())
        self.assertFalse(self.workspace.exists())

    def test_changed_staging_current_record_and_workspace_reject_old_review(
        self,
    ) -> None:
        snapshot, _ = self.seed()
        for path in (self.storage / self.name, self.store.path("project")):
            with self.subTest(path=path):
                receipt = self.cleanup(snapshot)
                replacement = self.storage / "replacement"
                replacement.write_bytes(path.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, path)
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.cleanup(snapshot, receipt=receipt)
        self.workspace.rmdir()
        receipt = self.cleanup(snapshot)
        self.workspace.mkdir()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.cleanup(snapshot, receipt=receipt)
        self.assertTrue((self.storage / self.name).exists())

    def test_storage_and_lock_replacements_reject_old_review(self) -> None:
        snapshot, _ = self.seed()
        receipt = self.cleanup(snapshot)
        lock = self.storage / "memory.lock"
        lock.rename(self.storage / "old.lock")
        lock.touch(mode=0o600)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.cleanup(snapshot, receipt=receipt)
        receipt = self.cleanup(snapshot)
        moved = self.base / "old-memory"
        self.storage.rename(moved)
        self.storage.mkdir(mode=0o700)
        for path in moved.iterdir():
            (self.storage / path.name).write_bytes(path.read_bytes())
            (self.storage / path.name).chmod(0o600)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.cleanup(snapshot, receipt=receipt)

    def test_unsafe_noncanonical_incomplete_and_wrong_identity_records_fail_closed(
        self,
    ) -> None:
        snapshot, _ = self.seed()
        path = self.storage / self.name
        original = path.read_bytes()
        for payload in (
            b"{",
            b"x" * (RECORD_BYTES + 1),
            original + b"\n",
            original.replace(b"Preserved", b"Corrupted"),
        ):
            with self.subTest(payload_length=len(payload)):
                path.write_bytes(payload)
                with self.assertRaises(ValueError):
                    self.cleanup(snapshot)
        for update in (
            {"owner_uid": os.getuid() + 1},
            {"workspace": str(self.base)},
            {"scope": "user", "workspace": None},
        ):
            document = snapshot.document.model_copy(update=update)
            changed = MemorySnapshot(
                document=document, sha256=digest(canonical_bytes(document))
            )
            path.write_bytes(canonical_bytes(changed))
            with self.assertRaises(ValueError):
                self.cleanup(changed)
        path.write_bytes(original)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.cleanup(snapshot)
        path.chmod(0o600)
        moved = self.storage / "moved"
        path.rename(moved)
        path.symlink_to(moved)
        with self.assertRaises(OSError):
            self.cleanup(snapshot)
        path.unlink()
        path.mkdir()
        with self.assertRaises(ValueError):
            self.cleanup(snapshot)
        self.name = ".memory-migration-" + "3" * 32 + ".tmp"
        backup = "resolution-backup-" + digest(canonical_bytes(snapshot)) + ".json"
        (self.storage / backup).mkdir()
        opened: list[int] = []
        original_open = os.open

        def tracked_open(*args: Any, **kwargs: Any) -> int:
            fd = original_open(*args, **kwargs)
            if args[0] == backup:
                opened.append(fd)
            return fd

        with patch("os.open", side_effect=tracked_open), self.assertRaises(OSError):
            self.cleanup(snapshot, backup)
        self.assertEqual(len(opened), 1)
        with self.assertRaises(OSError):
            os.fstat(opened[0])
        self.assertEqual(self.store.read("project"), snapshot)

    def test_linked_staging_is_not_discarded_and_backup_name_is_content_bound(
        self,
    ) -> None:
        snapshot, backup = self.seed(linked=True)
        assert backup is not None
        with self.assertRaisesRegex(ValueError, "single-link"):
            self.cleanup(snapshot)
        wrong = "resolution-backup-" + "0" * 64 + ".json"
        (self.storage / backup).rename(self.storage / wrong)
        with self.assertRaisesRegex(ValueError, "filename"):
            self.cleanup(snapshot, wrong)
        (self.storage / wrong).rename(self.storage / backup)
        extra = self.storage / "extra"
        os.link(self.storage / self.name, extra)
        with self.assertRaisesRegex(ValueError, "exactly two"):
            self.cleanup(snapshot, backup)
        extra.unlink()
        receipt = self.cleanup(snapshot, backup)
        (self.storage / backup).unlink()
        with self.assertRaises(FileNotFoundError):
            self.cleanup(snapshot, backup, receipt=receipt)
        self.assertTrue((self.storage / self.name).exists())

    def test_shared_lock_blocks_apply(self) -> None:
        snapshot, _ = self.seed()
        receipt = self.cleanup(snapshot)
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(self.cleanup(snapshot), receipt)
            with self.assertRaises(BlockingIOError):
                self.cleanup(snapshot, receipt=receipt)
        self.assertTrue((self.storage / self.name).exists())

    def test_unlink_and_directory_flush_failures_preserve_live_memory(self) -> None:
        snapshot, _ = self.seed()
        receipt = self.cleanup(snapshot)
        with (
            patch(
                "mos_eisley.conversation_memory_cleanup.os.unlink",
                side_effect=OSError("unlink failed"),
            ),
            self.assertRaisesRegex(OSError, "unlink failed"),
        ):
            self.cleanup(snapshot, receipt=receipt)
        self.assertTrue((self.storage / self.name).exists())
        with (
            patch(
                "mos_eisley.conversation_memory_cleanup.os.fsync",
                side_effect=OSError("flush failed"),
            ),
            self.assertRaisesRegex(OSError, "flush failed"),
        ):
            self.cleanup(snapshot, receipt=receipt)
        self.assertFalse((self.storage / self.name).exists())
        self.assertEqual(self.store.read("project"), snapshot)

    def test_late_staging_replacement_is_rechecked_before_unlink(self) -> None:
        snapshot, _ = self.seed()
        receipt = self.cleanup(snapshot)
        named = os.stat
        count = 0
        path = self.storage / self.name

        def changed(*args: Any, **kwargs: Any) -> os.stat_result:
            nonlocal count
            result = named(*args, **kwargs)
            if args[0] == self.name:
                count += 1
                if count == 1:
                    replacement = self.storage / "replacement"
                    replacement.write_bytes(path.read_bytes())
                    replacement.chmod(0o600)
                    os.replace(replacement, path)
            return result

        with (
            patch(
                "mos_eisley.conversation_memory_cleanup.os.stat", side_effect=changed
            ),
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            self.cleanup(snapshot, receipt=receipt)
        self.assertTrue(path.exists())

    def test_actual_interrupted_copy_resolution_and_backup_are_cleaned_explicitly(
        self,
    ) -> None:
        source = self.base / "source"
        source.mkdir()
        MemoryStore(self.storage, source).change(
            "project", "set", text="Source decisions"
        )
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_migration import relocate_memory_project
storage, source = Path(sys.argv[1]), sys.argv[2]
target, stage = Path(sys.argv[3]), sys.argv[4]
kwargs = {} if stage == 'copy' else {'strategy': 'append-source'}
preview = relocate_memory_project(storage, source, target, **kwargs)
link = os.link
def interrupted_link(*args, **kwargs):
    if stage == 'backup':
        link(*args, **kwargs)
    os._exit(77)
def interrupted_replace(*args, **kwargs):
    os._exit(77)
target_patch = 'os.replace' if stage == 'resolution' else 'os.link'
callback = interrupted_replace if stage == 'resolution' else interrupted_link
with patch('mos_eisley.conversation_memory_migration.' + target_patch,
           side_effect=callback):
    relocate_memory_project(storage, source, target,
                            expected_sha256=preview['preview_sha256'], **kwargs)
"""
        for stage in ("copy", "resolution", "backup"):
            with self.subTest(stage=stage):
                if stage != "copy":
                    self.store.change("project", "set", text="Destination decisions")
                before = {p: p.read_bytes() for p in self.storage.iterdir()}
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        code,
                        str(self.storage),
                        str(source),
                        str(self.workspace),
                        stage,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 77, result.stderr)
                names = list(self.storage.glob(".memory-*.tmp"))
                self.assertEqual(len(names), 1)
                self.name = names[0].name
                snapshot = MemorySnapshot.model_validate_json(names[0].read_bytes())
                backup = (
                    "resolution-backup-" + digest(canonical_bytes(snapshot)) + ".json"
                    if stage == "backup"
                    else None
                )
                receipt = self.cleanup(snapshot, backup)
                self.cleanup(snapshot, backup, receipt=receipt)
                self.assertFalse(names[0].exists())
                for path, payload in before.items():
                    self.assertEqual(path.read_bytes(), payload)
                if backup:
                    self.assertEqual((self.storage / backup).stat().st_nlink, 1)

    def test_cli_requires_exact_names_and_paired_apply_flags(self) -> None:
        snapshot, _ = self.seed()

        def launch(*options: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "memory-project-cleanup",
                    "--workspace-identity",
                    str(self.workspace),
                    "--memory-storage",
                    str(self.storage),
                    "--action",
                    "discard-staging",
                    "--temporary-name",
                    self.name,
                    "--record-sha256",
                    snapshot.sha256,
                    "--json",
                    *options,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

        for flags in (
            ("--apply",),
            ("--expected-sha256", "0" * 64),
            ("--temporary-name", "../file"),
            ("--temporary-name", "*.tmp"),
            ("--record-sha256", "bad"),
            ("--record-sha256", "0" * 64),
            ("--action", "recover-backup-link"),
            ("--apply", "--expected-sha256", "0" * 64),
            ("--action", "recover-backup-link", "--backup-name", "../bad"),
            ("--backup-name", "resolution-backup-" + "0" * 64 + ".json"),
        ):
            result = launch(*flags)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((self.storage / self.name).exists())
        preview = launch()
        self.assertEqual(preview.returncode, 0, preview.stderr)
        receipt = json.loads(preview.stdout)
        result = launch("--apply", "--expected-sha256", receipt["preview_sha256"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["removed"], self.name)

    def test_process_death_after_unlink_keeps_live_memory_and_recovered_backup(
        self,
    ) -> None:
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_cleanup import cleanup_memory_project
backup = sys.argv[5] or None
with patch('mos_eisley.conversation_memory_cleanup.os.fsync',
           side_effect=lambda fd: os._exit(77)):
    cleanup_memory_project(Path(sys.argv[1]), sys.argv[2],
        action='recover-backup-link' if backup else 'discard-staging',
        temporary_name=sys.argv[3], record_sha256=sys.argv[4],
        backup_name=backup, expected_sha256=sys.argv[6])
"""
        for linked in (False, True):
            with self.subTest(linked=linked):
                snapshot, backup = self.seed(linked=linked)
                receipt = self.cleanup(snapshot, backup)
                before = {
                    p: p.read_bytes()
                    for p in self.storage.iterdir()
                    if p.name != self.name
                }
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        code,
                        str(self.storage),
                        str(self.workspace),
                        self.name,
                        snapshot.sha256,
                        backup or "",
                        str(receipt["preview_sha256"]),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 77, result.stderr)
                self.assertFalse((self.storage / self.name).exists())
                self.assertEqual(self.store.read("project"), snapshot)
                self.assertTrue(
                    all(p.read_bytes() == value for p, value in before.items())
                )
                if backup:
                    self.assertEqual((self.storage / backup).stat().st_nlink, 1)
                if backup:
                    with self.assertRaisesRegex(ValueError, "exactly two"):
                        self.cleanup(snapshot, backup, receipt=receipt)
                else:
                    with self.assertRaises(FileNotFoundError):
                        self.cleanup(snapshot, backup, receipt=receipt)
