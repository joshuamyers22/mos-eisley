"""Explicit backup retention and partial batch cleanup preserve live memory."""

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

from mos_eisley.conversation_memory import MemorySnapshot, MemoryStore
from mos_eisley.conversation_memory_batch_cleanup import (
    MAX_CLEANUP_MANIFEST_BYTES,
    MemoryBatchCleanupError,
    MemoryCleanupManifest,
    MemoryCleanupSelection,
    cleanup_memory_batch,
    read_cleanup_manifest,
)
from mos_eisley.core.models import canonical_bytes, digest


class MemoryBatchCleanupTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        self.storage = self.base / "memory"
        self.store = MemoryStore(self.storage, self.workspace)
        self.old = self.store.change("project", "set", text="Earlier decisions")
        self.current = self.store.change("project", "append", text="Current decisions")
        self.store.change("user", "set", text="Private preferences")
        self.cutoff = 2_000_000_000

    def selection(
        self,
        action: str,
        index: int = 1,
        snapshot: MemorySnapshot | None = None,
    ) -> MemoryCleanupSelection:
        snapshot = snapshot or self.old
        backup = "resolution-backup-" + digest(canonical_bytes(snapshot)) + ".json"
        staging = f".memory-migration-{index:032x}.tmp"
        name = backup if action == "prune-backup" else staging
        path = self.storage / name
        path.write_bytes(canonical_bytes(snapshot))
        path.chmod(0o600)
        os.utime(path, ns=(1_000_000_000, 1_000_000_000))
        if action == "recover-backup-link":
            os.link(path, self.storage / backup)
        return MemoryCleanupSelection.model_validate(
            {
                "action": action,
                "record_sha256": snapshot.sha256,
                "temporary_name": staging if action != "prune-backup" else None,
                "backup_name": backup if action != "discard-staging" else None,
            }
        )

    def cleanup(
        self,
        *selections: MemoryCleanupSelection,
        receipt: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return cleanup_memory_batch(
            self.storage,
            str(self.workspace),
            MemoryCleanupManifest(records=selections),
            before_ns=self.cutoff
            if any(item.action == "prune-backup" for item in selections)
            else None,
            expected_sha256=str(receipt["preview_sha256"]) if receipt else None,
        )

    def test_mixed_batch_is_deterministic_and_preserves_live_and_unselected_records(
        self,
    ) -> None:
        discard = self.selection("discard-staging", 2)
        prune = self.selection("prune-backup")
        repair = self.selection("recover-backup-link", 1, self.current)
        untouched = self.storage / ".memory-resolution-unrecognized.tmp"
        untouched.write_bytes(b"incomplete")
        before = {p: p.read_bytes() for p in self.storage.iterdir()}
        receipt = self.cleanup(discard, prune, repair)
        self.assertEqual(receipt, self.cleanup(repair, prune, discard))
        self.assertEqual(receipt["status"], "planned")
        self.assertEqual(before, {p: p.read_bytes() for p in self.storage.iterdir()})
        result = self.cleanup(prune, repair, discard, receipt=receipt)
        names = sorted(item.removed_name for item in (discard, prune, repair))
        self.assertEqual(result["removed"], names)
        self.assertEqual(result["synced"], names)
        self.assertEqual(result["status"], "completed")
        for path, payload in before.items():
            if path.name in names:
                self.assertFalse(path.exists())
            else:
                self.assertEqual(path.read_bytes(), payload)
        assert repair.backup_name is not None
        self.assertEqual((self.storage / repair.backup_name).stat().st_nlink, 1)
        with self.assertRaisesRegex(ValueError, "exactly two links"):
            self.cleanup(prune, repair, discard, receipt=receipt)

    def test_cutoff_is_strict_and_binds_timestamp_and_policy_to_review(self) -> None:
        prune = self.selection("prune-backup")
        path = self.storage / prune.removed_name
        self.cutoff = path.stat().st_mtime_ns
        with self.assertRaisesRegex(ValueError, "cutoff"):
            self.cleanup(prune)
        self.cutoff += 1
        receipt = self.cleanup(prune)
        self.cutoff += 1
        with self.assertRaisesRegex(ValueError, "changed"):
            self.cleanup(prune, receipt=receipt)
        receipt = self.cleanup(prune)
        os.utime(path, ns=(1, path.stat().st_mtime_ns - 1))
        with self.assertRaisesRegex(ValueError, "changed"):
            self.cleanup(prune, receipt=receipt)
        self.assertTrue(path.exists())

    def test_pruning_protects_current_snapshot_and_absent_current_memory(self) -> None:
        prune = self.selection("prune-backup", snapshot=self.current)
        with self.assertRaisesRegex(ValueError, "distinct current"):
            self.cleanup(prune)
        self.store.path("project").unlink()
        self.workspace.rmdir()
        with self.assertRaisesRegex(ValueError, "distinct current"):
            self.cleanup(prune)
        self.assertTrue((self.storage / prune.removed_name).exists())
        self.assertFalse(self.workspace.exists())
        self.assertFalse(self.store.path("project").exists())

    def test_invalid_later_candidate_prevents_any_deletion(self) -> None:
        discard = self.selection("discard-staging")
        prune = self.selection("prune-backup")
        receipt = self.cleanup(discard, prune)
        (self.storage / prune.removed_name).write_bytes(b"incomplete")
        with self.assertRaises(ValueError):
            self.cleanup(discard, prune, receipt=receipt)
        self.assertTrue((self.storage / discard.removed_name).exists())

    def test_prune_rejects_wrong_hash_name_scope_owner_and_unsafe_links(self) -> None:
        prune = self.selection("prune-backup")
        path = self.storage / prune.removed_name
        original = path.read_bytes()
        wrong = prune.model_copy(update={"record_sha256": "0" * 64})
        with self.assertRaises(ValueError):
            self.cleanup(wrong)
        for changes in (
            {"owner_uid": os.getuid() + 1},
            {"workspace": str(self.base)},
            {"scope": "user", "workspace": None},
        ):
            document = self.old.document.model_copy(update=changes)
            other = MemorySnapshot(
                document=document, sha256=digest(canonical_bytes(document))
            )
            path.write_bytes(canonical_bytes(other))
            with self.assertRaises(ValueError):
                self.cleanup(prune.model_copy(update={"record_sha256": other.sha256}))
        path.write_bytes(original + b"\n")
        with self.assertRaises(ValueError):
            self.cleanup(prune)
        path.write_bytes(original)
        alias = self.storage / "other"
        os.link(path, alias)
        with self.assertRaisesRegex(ValueError, "single-link"):
            self.cleanup(prune)
        alias.unlink()
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.cleanup(prune)
        path.chmod(0o600)
        path.rename(alias)
        path.symlink_to(alias)
        with self.assertRaises(OSError):
            self.cleanup(prune)
        path.unlink()
        path.mkdir()
        with self.assertRaises(ValueError):
            self.cleanup(prune)
        path.rmdir()
        alias.rename(path)
        wrong_name = "resolution-backup-" + "0" * 64 + ".json"
        path.rename(self.storage / wrong_name)
        with self.assertRaisesRegex(ValueError, "filename"):
            self.cleanup(prune.model_copy(update={"backup_name": wrong_name}))
        self.assertEqual(self.store.read("project"), self.current)

    def test_changed_file_live_memory_workspace_and_lock_reject_stale_batch(
        self,
    ) -> None:
        prune = self.selection("prune-backup")
        for path in (self.storage / prune.removed_name, self.store.path("project")):
            receipt = self.cleanup(prune)
            replacement = self.storage / "replacement"
            replacement.write_bytes(path.read_bytes())
            replacement.chmod(0o600)
            os.utime(replacement, ns=(1, 1))
            os.replace(replacement, path)
            with self.assertRaisesRegex(ValueError, "changed"):
                self.cleanup(prune, receipt=receipt)
        receipt = self.cleanup(prune)
        self.store.change("project", "append", text="New decisions")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.cleanup(prune, receipt=receipt)
        receipt = self.cleanup(prune)
        self.workspace.rmdir()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.cleanup(prune, receipt=receipt)
        receipt = self.cleanup(prune)
        lock = self.storage / "memory.lock"
        lock.rename(self.storage / "old.lock")
        lock.touch(mode=0o600)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.cleanup(prune, receipt=receipt)
        self.assertTrue((self.storage / prune.removed_name).exists())

    def test_shared_reader_blocks_batch_apply_and_missing_storage_stays_absent(
        self,
    ) -> None:
        discard = self.selection("discard-staging")
        receipt = self.cleanup(discard)
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(receipt, self.cleanup(discard))
            with self.assertRaises(BlockingIOError):
                self.cleanup(discard, receipt=receipt)
        missing = self.base / "absent"
        with self.assertRaisesRegex(ValueError, "existing memory"):
            cleanup_memory_batch(
                missing, str(self.workspace), MemoryCleanupManifest(records=(discard,))
            )
        self.assertFalse(missing.exists())

    def test_mid_batch_replacement_stops_and_reports_only_completed_deletions(
        self,
    ) -> None:
        first = self.selection("discard-staging", 1)
        second = self.selection("discard-staging", 2)
        receipt = self.cleanup(first, second)
        sync = os.fsync

        def replace_after_sync(fd: int) -> None:
            sync(fd)
            path = self.storage / second.removed_name
            replacement = self.storage / "replacement"
            replacement.write_bytes(path.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, path)

        with (
            patch("os.fsync", side_effect=replace_after_sync),
            self.assertRaises(MemoryBatchCleanupError) as caught,
        ):
            self.cleanup(first, second, receipt=receipt)
        result = caught.exception.receipt
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["removed"], [first.removed_name])
        self.assertEqual(result["synced"], [first.removed_name])
        self.assertTrue((self.storage / second.removed_name).exists())
        fresh = self.cleanup(second)
        self.cleanup(second, receipt=fresh)
        self.assertEqual(self.store.read("project"), self.current)

    def test_unlink_and_flush_failures_distinguish_removed_and_synced(self) -> None:
        for boundary in ("unlink", "fsync"):
            with self.subTest(boundary=boundary):
                discard = self.selection("discard-staging")
                receipt = self.cleanup(discard)
                with (
                    patch("os." + boundary, side_effect=OSError("injected fault")),
                    self.assertRaises(MemoryBatchCleanupError) as caught,
                ):
                    self.cleanup(discard, receipt=receipt)
                result = caught.exception.receipt
                removed = [discard.removed_name] if boundary == "fsync" else []
                self.assertEqual(result["removed"], removed)
                self.assertEqual(result["synced"], [])
                self.assertEqual(
                    (self.storage / discard.removed_name).exists(), boundary == "unlink"
                )
                self.assertEqual(self.store.read("project"), self.current)

    def test_manifest_rejects_duplicates_overlaps_bad_shapes_and_bounds(self) -> None:
        prune = self.selection("prune-backup")
        for records in ((), (prune, prune), (prune,) * 33):
            with self.assertRaises(ValueError):
                MemoryCleanupManifest(records=records)
        repair = MemoryCleanupSelection(
            action="recover-backup-link",
            record_sha256=self.old.sha256,
            temporary_name=".memory-migration-" + "2" * 32 + ".tmp",
            backup_name=prune.backup_name,
        )
        with self.assertRaises(ValueError):
            MemoryCleanupManifest(records=(repair, prune))
        for changes in (
            {"temporary_name": "../escape"},
            {"backup_name": str(prune.backup_name) + "\n"},
            {"record_sha256": "0" * 64 + "\n"},
            {"extra": True},
            {"backup_name": None},
            {"action": "auto"},
            {"temporary_name": ".memory-resolution-" + "3" * 32 + ".tmp"},
        ):
            with self.assertRaises(ValueError):
                MemoryCleanupSelection.model_validate({**prune.model_dump(), **changes})
        path = self.base / "selection.json"
        manifest = MemoryCleanupManifest(records=(prune,))
        path.write_bytes(canonical_bytes(manifest))
        self.assertEqual(read_cleanup_manifest(path), manifest)
        for payload in (
            b"x" * (MAX_CLEANUP_MANIFEST_BYTES + 1),
            b"{",
            b"[]",
            b'{"records":[],"records":[]}',
            b'{"records":[{"action":"discard-staging","action":"prune-backup"}]}',
        ):
            path.write_bytes(payload)
            with self.assertRaises(ValueError):
                read_cleanup_manifest(path)
        path.unlink()
        path.symlink_to(self.store.path("project"))
        with self.assertRaises(OSError):
            read_cleanup_manifest(path)
        path.unlink()
        path.mkdir()
        with self.assertRaises(ValueError):
            read_cleanup_manifest(path)

    def test_policy_and_expected_hash_validation_precedes_storage_io(self) -> None:
        prune = self.selection("prune-backup")
        manifest = MemoryCleanupManifest(records=(prune,))
        for cutoff in (None, 0, -1, True, 2**63):
            with (
                patch("os.open", side_effect=AssertionError("unexpected I/O")),
                self.assertRaises(ValueError),
            ):
                cleanup_memory_batch(
                    self.storage, str(self.workspace), manifest, before_ns=cutoff
                )
        with self.assertRaises(ValueError):
            cleanup_memory_batch(
                self.storage,
                str(self.workspace),
                manifest,
                before_ns=self.cutoff,
                expected_sha256="x",
            )
        discard = self.selection("discard-staging")
        with self.assertRaises(ValueError):
            cleanup_memory_batch(
                self.storage,
                str(self.workspace),
                MemoryCleanupManifest(records=(discard,)),
                before_ns=self.cutoff,
            )

    def test_32_records_apply_with_no_directory_scan(self) -> None:
        records = tuple(self.selection("discard-staging", i) for i in range(32))
        with patch("os.scandir", side_effect=AssertionError("unexpected scan")):
            receipt = self.cleanup(*records)
            result = self.cleanup(*records, receipt=receipt)
        self.assertEqual(
            result["removed"], sorted(item.removed_name for item in records)
        )

    def test_cli_preview_apply_and_partial_failure_receipts(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO

        from mos_eisley.cli import main

        discard = self.selection("discard-staging")
        prune = self.selection("prune-backup")
        manifest = MemoryCleanupManifest(records=(discard, prune))
        path = self.base / "selection.json"
        path.write_bytes(canonical_bytes(manifest))
        command = [
            "memory-project-cleanup-batch",
            "--workspace-identity",
            str(self.workspace),
            "--memory-storage",
            str(self.storage),
            "--selection",
            str(path),
            "--before-ns",
            str(self.cutoff),
            "--json",
        ]
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(command), 0)
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["type"], "memory.project_cleanup_batch")
        approved = [*command, "--apply", "--expected-sha256", receipt["preview_sha256"]]
        unlink = os.unlink

        def fail_second(name: str, *args: Any, **kwargs: Any) -> None:
            if name == prune.removed_name:
                raise OSError("injected fault")
            unlink(name, *args, **kwargs)

        output = StringIO()
        with redirect_stdout(output), patch("os.unlink", side_effect=fail_second):
            self.assertEqual(main(approved), 2)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["removed"], [discard.removed_name])
        path.write_bytes(canonical_bytes(MemoryCleanupManifest(records=(prune,))))
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(command), 0)
        fresh = json.loads(output.getvalue())
        with redirect_stdout(StringIO()):
            self.assertEqual(
                main(
                    [*command, "--apply", "--expected-sha256", fresh["preview_sha256"]]
                ),
                0,
            )

    def test_process_death_after_unlink_requires_fresh_remaining_selection(
        self,
    ) -> None:
        discard = self.selection("discard-staging")
        prune = self.selection("prune-backup")
        repair = self.selection("recover-backup-link", 2, self.current)
        path = self.base / "selection.json"
        path.write_bytes(
            canonical_bytes(MemoryCleanupManifest(records=(discard, prune, repair)))
        )
        receipt = self.cleanup(discard, prune, repair)
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_batch_cleanup import (
    cleanup_memory_batch, read_cleanup_manifest,
)
with patch('os.fsync', side_effect=lambda fd: os._exit(73)):
    manifest = read_cleanup_manifest(Path(sys.argv[3]))
    cleanup_memory_batch(Path(sys.argv[1]), sys.argv[2], manifest,
                         before_ns=int(sys.argv[4]), expected_sha256=sys.argv[5])
"""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(self.storage),
                str(self.workspace),
                str(path),
                str(self.cutoff),
                str(receipt["preview_sha256"]),
            ],
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertFalse((self.storage / discard.removed_name).exists())
        with self.assertRaises(FileNotFoundError):
            self.cleanup(discard, prune, repair, receipt=receipt)
        fresh = self.cleanup(prune, repair)
        self.cleanup(prune, repair, receipt=fresh)
        assert repair.backup_name is not None
        self.assertEqual((self.storage / repair.backup_name).stat().st_nlink, 1)
        self.assertEqual(self.store.read("project"), self.current)
