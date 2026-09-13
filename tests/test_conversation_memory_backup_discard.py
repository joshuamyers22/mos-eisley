"""Unsupported backup disposal cannot bypass canonical/current-memory protection."""

import base64
import fcntl
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot, MemoryStore
from mos_eisley.conversation_memory_backup_discard import (
    MemoryBackupDiscardError,
    discard_memory_backup,
    discard_project_memory_backup,
)
from mos_eisley.conversation_memory_raw import MAX_RAW_REVIEW_BYTES
from mos_eisley.conversation_memory_retention import retain_memory_backups
from mos_eisley.core.models import canonical_bytes, digest


class MemoryBackupDiscardTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        self.storage = self.base / "memory"
        self.store = MemoryStore(self.storage, self.workspace)
        self.old = self.store.change("project", "set", text="Former project decisions")
        self.current = self.store.change("project", "set", text="Current decisions")
        self.store.change("user", "set", text="Personal preferences")
        self.name = "resolution-backup-" + digest(canonical_bytes(self.old)) + ".json"
        self.path = self.storage / self.name
        self.payload = json.dumps(self.old.model_dump(mode="json"), indent=2).encode()
        self.seed()

    def seed(self, payload: bytes | None = None) -> None:
        if payload is not None:
            self.payload = payload
        self.path.write_bytes(self.payload)
        self.path.chmod(0o600)

    def review(
        self, receipt: dict[str, object] | None = None, *, limit: int = RECORD_BYTES
    ) -> dict[str, object]:
        return discard_project_memory_backup(
            self.storage,
            str(self.workspace),
            self.name,
            digest(self.payload),
            expected_sha256=str(receipt["preview_sha256"]) if receipt else None,
            review_max_bytes=limit,
        )

    def raw(
        self, receipt: dict[str, object] | None = None, *, limit: int = RECORD_BYTES
    ) -> dict[str, object]:
        return discard_memory_backup(
            self.storage,
            self.name,
            digest(self.payload),
            expected_sha256=str(receipt["preview_sha256"]) if receipt else None,
            review_max_bytes=limit,
        )

    def test_noncanonical_discard_preserves_all_other_files_and_unblocks_retention(
        self,
    ) -> None:
        staging = self.storage / (".memory-resolution-" + "1" * 32 + ".tmp")
        staging.write_bytes(b"unrelated staging")
        before = {p: p.read_bytes() for p in self.storage.iterdir()}
        with self.assertRaises(ValueError):
            retain_memory_backups(
                self.storage, str(self.workspace), keep_newest=1, before_ns=2**62
            )
        with patch("os.scandir", side_effect=AssertionError("unexpected scan")):
            receipt = self.review()
            self.assertEqual(receipt, self.review())
            self.assertEqual(
                receipt["unsupported_reasons"], ["noncanonical-serialization"]
            )
            self.assertEqual(receipt["canonical_backup_name"], self.name)
            self.assertEqual(receipt["record"], self.old.model_dump(mode="json"))
            self.assertEqual(
                receipt["current_project"], self.current.model_dump(mode="json")
            )
            self.assertTrue(receipt["project_identity_verified"])
            self.assertEqual(
                base64.b64decode(str(receipt["raw_bytes_base64"])), self.payload
            )
            self.assertEqual(self.review(receipt)["status"], "completed")
        for path, payload in before.items():
            if path != self.path:
                self.assertEqual(path.read_bytes(), payload)
        self.assertFalse(self.path.exists())
        retention = retain_memory_backups(
            self.storage, str(self.workspace), keep_newest=1, before_ns=2**62
        )
        self.assertEqual(retention["selected"], [])

    def test_invalid_backup_receipt_is_unattributed_and_preserves_live_memory(
        self,
    ) -> None:
        for payload in (
            b"",
            b"\xff\x00\x1b[2J",
            canonical_bytes(self.old).replace(b"Former", b"Broken"),
        ):
            self.seed(payload)
            receipt = self.raw()
            self.assertEqual(receipt["scope"], "storage")
            self.assertIsNone(receipt["project_identity"])
            self.assertFalse(receipt["project_identity_verified"])
            self.assertEqual(
                receipt["current_memory_protection"], "unverified-invalid-record"
            )
            self.assertNotIn("\x1b", json.dumps(receipt))
            self.assertEqual(
                base64.b64decode(str(receipt["raw_bytes_base64"])), payload
            )
            self.raw(receipt)
        self.assertEqual(self.store.read("project"), self.current)

    def test_supported_canonical_backups_cannot_bypass_retention(self) -> None:
        self.seed(canonical_bytes(self.old))
        with self.assertRaisesRegex(ValueError, "canonical backups require retention"):
            self.review()
        with self.assertRaisesRegex(ValueError, "Valid snapshots"):
            self.raw()
        self.assertTrue(self.path.exists())

    def test_misnamed_valid_backup_is_explicitly_bound_to_actual_and_canonical_names(
        self,
    ) -> None:
        canonical_name = self.name
        self.path.unlink()
        self.name = "resolution-backup-" + "a" * 64 + ".json"
        self.path = self.storage / self.name
        self.seed(canonical_bytes(self.old))
        receipt = self.review()
        self.assertEqual(receipt["backup_name"], self.name)
        self.assertEqual(receipt["canonical_backup_name"], canonical_name)
        self.assertEqual(receipt["unsupported_reasons"], ["filename-mismatch"])
        self.review(receipt)

    def test_current_memory_and_missing_or_unreadable_current_protect_valid_backups(
        self,
    ) -> None:
        self.seed(canonical_bytes(self.current) + b"\n")
        with self.assertRaisesRegex(ValueError, "matches current"):
            self.review()
        self.seed(canonical_bytes(self.old) + b"\n")
        current_path = self.store.path("project")
        current_path.unlink()
        with self.assertRaisesRegex(ValueError, "no current"):
            self.review()
        current_path.write_bytes(b"broken")
        current_path.chmod(0o600)
        with self.assertRaises(ValueError):
            self.review()
        with self.assertRaisesRegex(ValueError, "Valid snapshots"):
            self.raw()
        self.assertTrue(self.path.exists())

    def test_foreign_owner_project_and_user_records_are_refused_by_both_paths(
        self,
    ) -> None:
        for update in (
            {"owner_uid": os.getuid() + 1},
            {"workspace": str(self.base)},
            {"scope": "user", "workspace": None},
        ):
            doc = self.old.document.model_copy(update=update)
            record = MemorySnapshot(document=doc, sha256=digest(canonical_bytes(doc)))
            self.seed(canonical_bytes(record) + b"\n")
            with self.assertRaisesRegex(ValueError, "owner/project"):
                self.review()
            with self.assertRaisesRegex(ValueError, "Valid snapshots"):
                self.raw()

    def test_duplicate_keys_do_not_establish_verified_project_identity(self) -> None:
        for key, duplicate in (
            (b'"document":', b'"document":{},'),
            (b'"owner_uid":', b'"owner_uid":99999,'),
            (b'"text":', b'"text":"hidden",'),
        ):
            self.seed(canonical_bytes(self.old).replace(key, duplicate + key, 1))
            MemorySnapshot.model_validate_json(self.payload)
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                self.review()
            with self.assertRaisesRegex(ValueError, "Valid snapshots"):
                self.raw()

    def test_real_maximum_limits_for_valid_and_invalid_bytes(self) -> None:
        canonical = canonical_bytes(self.old)
        for payload, project in (
            (canonical + b" " * (MAX_RAW_REVIEW_BYTES - len(canonical)), True),
            (b"\xff" * MAX_RAW_REVIEW_BYTES, False),
        ):
            self.seed(payload)
            operation = self.review if project else self.raw
            with self.assertRaisesRegex(ValueError, "256 KiB"):
                operation()
            receipt = operation(limit=MAX_RAW_REVIEW_BYTES)
            self.assertEqual(
                len(base64.b64decode(str(receipt["raw_bytes_base64"]))),
                MAX_RAW_REVIEW_BYTES,
            )
            if project:
                self.assertIn(
                    "exceeds-retention-record-limit",
                    json.loads(json.dumps(receipt))["unsupported_reasons"],
                )
                with self.assertRaisesRegex(ValueError, "Valid snapshots"):
                    self.raw(limit=MAX_RAW_REVIEW_BYTES)
            operation(receipt, limit=MAX_RAW_REVIEW_BYTES)
        self.seed(b"x" * (MAX_RAW_REVIEW_BYTES + 1))
        for operation in (self.raw, self.review):
            with self.assertRaisesRegex(ValueError, "byte limit"):
                operation(limit=MAX_RAW_REVIEW_BYTES)

    def test_limits_names_and_hashes_are_validated_before_io(self) -> None:
        for project in (False, True):
            for name, raw, expected, limit in (
                ("../outside", digest(self.payload), None, RECORD_BYTES),
                ("user.json", digest(self.payload), None, RECORD_BYTES),
                (
                    self.store.path("project").name,
                    digest(self.payload),
                    None,
                    RECORD_BYTES,
                ),
                (
                    ".memory-resolution-" + "1" * 32 + ".tmp",
                    digest(self.payload),
                    None,
                    RECORD_BYTES,
                ),
                (
                    "resolution-backup-broken.json",
                    digest(self.payload),
                    None,
                    RECORD_BYTES,
                ),
                (self.name, "A" * 64, None, RECORD_BYTES),
                (self.name, digest(self.payload), "bad", RECORD_BYTES),
                (self.name, digest(self.payload), None, 0),
                (self.name, digest(self.payload), None, True),
                (self.name, digest(self.payload), None, MAX_RAW_REVIEW_BYTES + 1),
            ):
                with (
                    patch("os.open", side_effect=AssertionError("unexpected open")),
                    self.assertRaises(ValueError),
                ):
                    # Separate calls preserve the different public signatures.
                    if project:
                        discard_project_memory_backup(
                            self.storage,
                            str(self.workspace),
                            name,
                            raw,
                            expected_sha256=expected,
                            review_max_bytes=limit,
                        )
                    else:
                        discard_memory_backup(
                            self.storage,
                            name,
                            raw,
                            expected_sha256=expected,
                            review_max_bytes=limit,
                        )

    def test_changed_bytes_policy_current_file_workspace_and_lock_invalidate_review(
        self,
    ) -> None:
        for project in (False, True):
            self.seed(
                json.dumps(self.old.model_dump(mode="json"), indent=2).encode()
                if project
                else b"invalid"
            )
            operation = self.review if project else self.raw
            receipt = operation()
            with self.assertRaisesRegex(ValueError, "changed"):
                operation(receipt, limit=RECORD_BYTES + 1)
            self.seed(self.payload + b" ")
            with self.assertRaisesRegex(ValueError, "changed"):
                operation(receipt)
            receipt = operation()
            self.path.rename(self.base / ("original-" + str(project)))
            self.seed()
            with self.assertRaisesRegex(ValueError, "changed"):
                operation(receipt)
        receipt = self.review()
        self.store.change("user", "append", text="Unrelated")
        self.assertEqual(self.review(), receipt)
        self.store.change("project", "append", text="A new decision")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)
        receipt = self.review()
        self.workspace.rename(self.base / "old-workspace")
        self.workspace.mkdir()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)
        receipt = self.review()
        (self.storage / "memory.lock").rename(self.storage / "old-lock")
        (self.storage / "memory.lock").touch(mode=0o600)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)

    def test_raw_hash_and_late_file_replacement_are_rechecked(self) -> None:
        receipt = self.review()
        self.path.write_bytes(self.payload + b" ")
        with self.assertRaisesRegex(ValueError, "raw hash"):
            self.review(receipt)
        self.seed()
        receipt = self.review()
        original_open = os.open

        def replace(
            path: str | Path,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            fd = original_open(path, flags, mode, dir_fd=dir_fd)
            if path == self.store.path("project").name:
                self.path.rename(self.base / "replaced")
                self.seed()
            return fd

        with (
            patch("os.open", side_effect=replace),
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            self.review(receipt)
        self.assertTrue(self.path.exists())

    def test_unsafe_file_types_permissions_and_links_are_refused(self) -> None:
        self.path.rename(self.base / "preserved")
        for kind in ("symlink", "hardlink", "fifo", "directory", "public"):
            if kind == "symlink":
                self.path.symlink_to(self.base / "preserved")
            elif kind == "hardlink":
                os.link(self.base / "preserved", self.path)
            elif kind == "fifo":
                os.mkfifo(self.path, 0o600)
            elif kind == "directory":
                self.path.mkdir(mode=0o700)
            else:
                self.seed()
                self.path.chmod(0o644)
            for operation in (self.review, self.raw):
                with self.assertRaises((OSError, ValueError)):
                    operation()
            if kind == "directory":
                self.path.rmdir()
            else:
                self.path.unlink()
        self.assertEqual((self.base / "preserved").read_bytes(), self.payload)

    def test_missing_storage_and_historical_workspace_do_not_get_created(self) -> None:
        absent = self.base / "absent"
        with self.assertRaises(ValueError):
            discard_memory_backup(absent, self.name, digest(self.payload))
        self.assertFalse(absent.exists())
        alias = self.base / "alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaises(ValueError):
            discard_project_memory_backup(
                self.storage, str(alias), self.name, digest(self.payload)
            )
        self.workspace.rmdir()
        self.review(self.review())
        self.assertFalse(self.workspace.exists())

    def test_shared_reader_blocks_apply_and_storage_replacement_invalidates_review(
        self,
    ) -> None:
        receipt = self.review()
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(self.review(), receipt)
            with self.assertRaises(BlockingIOError):
                self.review(receipt)
        previous = self.base / "previous-memory"
        self.storage.rename(previous)
        self.storage.mkdir(mode=0o700)
        for path in previous.iterdir():
            destination = self.storage / path.name
            destination.write_bytes(path.read_bytes())
            destination.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)

    def test_unlink_flush_failures_report_progress_for_both_paths(self) -> None:
        for project in (False, True):
            for operation, removed in (("unlink", False), ("fsync", True)):
                self.seed(canonical_bytes(self.old) + b"\n" if project else b"invalid")
                discard = self.review if project else self.raw
                receipt = discard()
                with (
                    patch("os." + operation, side_effect=OSError("interrupted")),
                    self.assertRaises(MemoryBackupDiscardError) as caught,
                ):
                    discard(receipt)
                self.assertEqual(caught.exception.receipt["status"], "incomplete")
                self.assertEqual(caught.exception.receipt["removed"], removed)
                self.assertFalse(caught.exception.receipt["synced"])
                self.assertEqual(self.path.exists(), not removed)

    def test_process_death_requires_fresh_review_of_replacement(self) -> None:
        receipt = self.review()
        script = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_backup_discard import discard_project_memory_backup
unlink = os.unlink
def die(name, *, dir_fd=None):
    unlink(name, dir_fd=dir_fd)
    os._exit(73)
with patch('os.unlink', side_effect=die):
    discard_project_memory_backup(Path(sys.argv[1]), sys.argv[2], sys.argv[3],
                                  sys.argv[4], expected_sha256=sys.argv[5])
"""
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(self.storage),
                str(self.workspace),
                self.name,
                digest(self.payload),
                str(receipt["preview_sha256"]),
            ],
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(child.returncode, 73, child.stderr)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.store.read("project"), self.current)
        self.seed()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)
        self.review(self.review())

    def test_cli_review_apply_guards_and_incomplete_receipt(self) -> None:
        from mos_eisley.cli import parser
        from mos_eisley.conversation_memory_backup_discard import run_command

        def invoke(arguments: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, "-m", "mos_eisley.cli", *arguments],
                text=True,
                capture_output=True,
                timeout=20,
            )

        for project in (False, True):
            self.seed(canonical_bytes(self.old) + b"\n" if project else b"invalid")
            args = [
                "memory-project-backup-discard" if project else "memory-backup-discard",
                "--memory-storage",
                str(self.storage),
                "--backup-name",
                self.name,
                "--raw-sha256",
                digest(self.payload),
                "--json",
            ]
            if project:
                args += ["--workspace-identity", str(self.workspace)]
            preview = invoke(args)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            receipt = json.loads(preview.stdout)
            self.assertEqual(
                receipt["type"],
                "memory.project_backup_discard" if project else "memory.backup_discard",
            )
            self.assertEqual(invoke([*args, "--apply"]).returncode, 2)
            self.assertEqual(
                invoke(
                    [*args, "--expected-sha256", receipt["preview_sha256"]]
                ).returncode,
                2,
            )
            applied_args = [
                *args,
                "--apply",
                "--expected-sha256",
                receipt["preview_sha256"],
            ]
            out = StringIO()
            with (
                redirect_stdout(out),
                patch("os.fsync", side_effect=OSError("interrupted")),
            ):
                self.assertEqual(run_command(parser().parse_args(applied_args)), 2)
            failed = json.loads(out.getvalue())
            self.assertEqual(failed["status"], "incomplete")
            self.assertTrue(failed["removed"])
            self.seed()
            preview = invoke(args)
            receipt = json.loads(preview.stdout)
            applied = invoke(
                [*args, "--apply", "--expected-sha256", receipt["preview_sha256"]]
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(json.loads(applied.stdout)["status"], "completed")
