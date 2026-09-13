"""Expanded raw limits and exact-byte, project-verified staging disposal."""

import base64
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot, MemoryStore
from mos_eisley.conversation_memory_staging import (
    MAX_STAGING_REVIEW_BYTES,
    MemoryStagingDiscardError,
    discard_memory_staging,
    discard_project_memory_staging,
)
from mos_eisley.core.models import canonical_bytes, digest


class MemoryStagingReviewTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        self.storage = self.base / "memory"
        self.store = MemoryStore(self.storage, self.workspace)
        self.snapshot = self.store.change("project", "set", text="Project decisions")
        self.store.change("user", "set", text="Personal preferences")
        self.name = ".memory-resolution-" + "1" * 32 + ".tmp"
        self.path = self.storage / self.name
        self.payload = (
            json.dumps(self.snapshot.model_dump(mode="json"), indent=2).encode() + b"\n"
        )
        self.seed()

    def seed(self, payload: bytes | None = None) -> None:
        if payload is not None:
            self.payload = payload
        self.path.write_bytes(self.payload)
        self.path.chmod(0o600)

    def review(
        self, receipt: dict[str, object] | None = None, *, limit: int = RECORD_BYTES
    ) -> dict[str, object]:
        return discard_project_memory_staging(
            self.storage,
            str(self.workspace),
            self.name,
            digest(self.payload),
            review_max_bytes=limit,
            expected_sha256=str(receipt["preview_sha256"]) if receipt else None,
        )

    def raw(
        self, receipt: dict[str, object] | None = None, *, limit: int = RECORD_BYTES
    ) -> dict[str, object]:
        return discard_memory_staging(
            self.storage,
            self.name,
            digest(self.payload),
            review_max_bytes=limit,
            expected_sha256=str(receipt["preview_sha256"]) if receipt else None,
        )

    def test_noncanonical_review_preserves_other_files(
        self,
    ) -> None:
        backup = self.storage / (
            "resolution-backup-" + digest(canonical_bytes(self.snapshot)) + ".json"
        )
        backup.write_bytes(canonical_bytes(self.snapshot))
        backup.chmod(0o600)
        other = self.storage / (".memory-migration-" + "2" * 32 + ".tmp")
        other.write_bytes(b"incomplete")
        before = {path: path.read_bytes() for path in self.storage.iterdir()}
        with patch("os.scandir", side_effect=AssertionError("unexpected scan")):
            receipt = self.review()
            self.assertEqual(receipt, self.review())
            self.assertEqual(receipt["scope"], "project")
            self.assertTrue(receipt["project_identity_verified"])
            self.assertEqual(receipt["project_identity"], str(self.workspace))
            self.assertEqual(receipt["serialization"], "noncanonical")
            self.assertEqual(receipt["record"], self.snapshot.model_dump(mode="json"))
            self.assertEqual(receipt["current_project"], receipt["record"])
            self.assertEqual(
                base64.b64decode(str(receipt["raw_bytes_base64"])), self.payload
            )
            self.assertNotEqual(receipt["raw_sha256"], self.snapshot.sha256)
            self.assertEqual(self.review(receipt)["status"], "completed")
        self.assertFalse(self.path.exists())
        for path, payload in before.items():
            if path != self.path:
                self.assertEqual(path.read_bytes(), payload)

    def test_canonical_and_last_copy_staging_are_supported_without_workspace_creation(
        self,
    ) -> None:
        self.seed(canonical_bytes(self.snapshot))
        self.store.path("project").unlink()
        self.workspace.rmdir()
        receipt = self.review()
        self.assertEqual(receipt["serialization"], "canonical")
        self.assertIsNone(receipt["current_project"])
        self.assertFalse(
            json.loads(json.dumps(receipt))["workspace_identity"]["exists"]
        )
        self.review(receipt)
        self.assertFalse(self.workspace.exists())
        self.assertFalse(self.path.exists())

    def test_oversized_valid_snapshot_requires_explicit_limit_and_project_review(
        self,
    ) -> None:
        payload = canonical_bytes(self.snapshot)
        self.seed(payload + b" " * (MAX_STAGING_REVIEW_BYTES - len(payload)))
        for operation in (self.review, self.raw):
            with self.assertRaisesRegex(ValueError, "256 KiB"):
                operation()
        with self.assertRaisesRegex(ValueError, "Valid snapshots"):
            self.raw(limit=MAX_STAGING_REVIEW_BYTES)
        receipt = self.review(limit=MAX_STAGING_REVIEW_BYTES)
        self.assertEqual(
            len(base64.b64decode(str(receipt["raw_bytes_base64"]))),
            MAX_STAGING_REVIEW_BYTES,
        )
        self.assertEqual(receipt["review_max_bytes"], MAX_STAGING_REVIEW_BYTES)
        self.assertEqual(
            self.review(receipt, limit=MAX_STAGING_REVIEW_BYTES)["status"], "completed"
        )

    def test_oversized_invalid_bytes_stay_unattributed_at_real_maximum(self) -> None:
        self.seed(b"\xff" * MAX_STAGING_REVIEW_BYTES)
        with self.assertRaisesRegex(ValueError, "256 KiB"):
            self.raw()
        with self.assertRaises(ValueError):
            self.review(limit=MAX_STAGING_REVIEW_BYTES)
        receipt = self.raw(limit=MAX_STAGING_REVIEW_BYTES)
        self.assertEqual(
            base64.b64decode(str(receipt["raw_bytes_base64"])), self.payload
        )
        self.assertFalse(receipt["project_identity_verified"])
        self.assertIsNone(receipt["project_identity"])
        self.raw(receipt, limit=MAX_STAGING_REVIEW_BYTES)
        self.seed(b"x" * (MAX_STAGING_REVIEW_BYTES + 1))
        for operation in (self.review, self.raw):
            with self.assertRaisesRegex(ValueError, "byte limit"):
                operation(limit=MAX_STAGING_REVIEW_BYTES)

    def test_limit_is_validated_before_io_and_bound_to_review(self) -> None:
        receipt = self.review(limit=RECORD_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)
        self.seed(b"invalid")
        receipt = self.raw(limit=RECORD_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.raw(receipt)
        for limit in (0, -1, True, MAX_STAGING_REVIEW_BYTES + 1):
            with patch("os.open", side_effect=AssertionError("unexpected open")):
                for operation in (self.raw, self.review):
                    with self.assertRaises(ValueError):
                        operation(limit=limit)

    def test_foreign_owner_project_user_and_invalid_records_cannot_claim_project_scope(
        self,
    ) -> None:
        for update in (
            {"owner_uid": os.getuid() + 1},
            {"workspace": str(self.base)},
            {"scope": "user", "workspace": None},
        ):
            document = self.snapshot.document.model_copy(update=update)
            snapshot = MemorySnapshot(
                document=document, sha256=digest(canonical_bytes(document))
            )
            self.seed(canonical_bytes(snapshot) + b"\n")
            with self.assertRaisesRegex(ValueError, "owner/project"):
                self.review()
            with self.assertRaisesRegex(ValueError, "Valid snapshots"):
                self.raw()
        self.seed(b"incomplete")
        with self.assertRaises(ValueError):
            self.review()
        self.assertFalse(self.raw()["project_identity_verified"])

    def test_duplicate_keys_are_not_treated_as_verified_project_identity(self) -> None:
        original = canonical_bytes(self.snapshot)
        for payload in (
            original.replace(b'"document":', b'"document":{},"document":', 1),
            original.replace(b'"owner_uid":', b'"owner_uid":999999,"owner_uid":', 1),
            original.replace(b'"text":', b'"text":"hidden","text":', 1),
        ):
            self.seed(payload)
            MemorySnapshot.model_validate_json(payload)
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                self.review()
            with self.assertRaisesRegex(ValueError, "Valid snapshots"):
                self.raw()
        self.assertTrue(self.path.exists())

    def test_formatting_changes_and_recomputed_raw_hash_invalidate_review(self) -> None:
        receipt = self.review()
        self.seed(self.payload + b" ")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)
        receipt = self.review()
        self.path.write_bytes(self.payload + b" ")
        with self.assertRaisesRegex(ValueError, "raw hash"):
            self.review(receipt)

    def test_current_project_changes_bind_review_but_user_changes_do_not(self) -> None:
        receipt = self.review()
        self.store.change("user", "append", text="Another preference")
        self.assertEqual(self.review(), receipt)
        self.store.change("project", "append", text="New project decision")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)
        self.store.path("project").write_bytes(b"broken")
        with self.assertRaises(ValueError):
            self.review()
        self.seed(b"invalid")
        self.assertFalse(self.raw()["project_identity_verified"])

    def test_file_workspace_and_lock_replacements_invalidate_review(self) -> None:
        receipt = self.review()
        self.path.rename(self.base / "preserved")
        self.seed()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)
        receipt = self.review()
        self.workspace.rename(self.base / "old-project")
        self.workspace.mkdir()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)
        receipt = self.review()
        lock = self.storage / "memory.lock"
        lock.rename(self.storage / "old-lock")
        lock.touch(mode=0o600)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)

    def test_unsafe_types_and_hardlinked_backups_are_refused(self) -> None:
        preserved = self.base / "preserved"
        self.path.rename(preserved)
        for kind in ("symlink", "hardlink", "fifo", "directory", "public"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    self.path.symlink_to(preserved)
                elif kind == "hardlink":
                    os.link(preserved, self.path)
                elif kind == "fifo":
                    os.mkfifo(self.path, 0o600)
                elif kind == "directory":
                    self.path.mkdir(mode=0o700)
                else:
                    self.path.write_bytes(self.payload)
                    self.path.chmod(0o644)
                with self.assertRaises((OSError, ValueError)):
                    self.review()
                if kind == "directory":
                    self.path.rmdir()
                else:
                    self.path.unlink()
        preserved.rename(self.path)
        backup = self.storage / (
            "resolution-backup-" + digest(canonical_bytes(self.snapshot)) + ".json"
        )
        os.link(self.path, backup)
        with self.assertRaisesRegex(ValueError, "single-link"):
            self.review()
        self.assertEqual(backup.read_bytes(), self.payload)

    def test_alias_identity_and_live_or_backup_names_are_refused(self) -> None:
        alias = self.base / "alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaises(ValueError):
            discard_project_memory_staging(
                self.storage, str(alias), self.name, digest(self.payload)
            )
        for name in (
            "../outside",
            "user.json",
            self.store.path("project").name,
            "resolution-backup-" + "1" * 64 + ".json",
            ".memory-mappings-" + "1" * 32 + ".tmp",
        ):
            with self.assertRaises(ValueError):
                discard_project_memory_staging(
                    self.storage, str(self.workspace), name, digest(self.payload)
                )

    def test_shared_reader_blocks_apply_and_missing_storage_stays_absent(self) -> None:
        receipt = self.review()
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(self.review(), receipt)
            with self.assertRaises(BlockingIOError):
                self.review(receipt)
        absent = self.base / "absent"
        with self.assertRaises(ValueError):
            discard_project_memory_staging(
                absent, str(self.workspace), self.name, digest(self.payload)
            )
        self.assertFalse(absent.exists())

    def test_replacement_during_snapshot_review_is_detected_before_unlink(self) -> None:
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

    def test_unlink_and_flush_failures_report_actual_progress(self) -> None:
        for operation, removed in (("unlink", False), ("fsync", True)):
            self.seed()
            receipt = self.review()
            with (
                patch(
                    "mos_eisley.conversation_memory_staging.os." + operation,
                    side_effect=OSError("interrupted"),
                ),
                self.assertRaises(MemoryStagingDiscardError) as failed,
            ):
                self.review(receipt)
            self.assertEqual(failed.exception.receipt["status"], "incomplete")
            self.assertEqual(failed.exception.receipt["removed"], removed)
            self.assertFalse(failed.exception.receipt["synced"])
            self.assertEqual(self.path.exists(), not removed)

    def test_process_death_requires_fresh_file_review(
        self,
    ) -> None:
        receipt = self.review()
        script = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_staging import discard_project_memory_staging
unlink = os.unlink
def die(name, *, dir_fd=None):
    unlink(name, dir_fd=dir_fd)
    os._exit(73)
with patch('mos_eisley.conversation_memory_staging.os.unlink', side_effect=die):
    discard_project_memory_staging(Path(sys.argv[1]), sys.argv[2], sys.argv[3],
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
        self.assertEqual(self.store.read("project"), self.snapshot)
        self.seed()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.review(receipt)
        self.review(self.review())

    def test_cli_project_and_oversized_raw_review_apply(self) -> None:
        def invoke(arguments: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, "-m", "mos_eisley.cli", *arguments],
                capture_output=True,
                text=True,
                timeout=20,
            )

        project_args = [
            "memory-project-staging-discard",
            "--workspace-identity",
            str(self.workspace),
        ]
        for prefix, payload, limit in (
            (project_args, self.payload, RECORD_BYTES),
            (["memory-staging-discard"], b"x" * (RECORD_BYTES + 1), RECORD_BYTES + 1),
        ):
            self.seed(payload)
            args = [
                *prefix,
                "--memory-storage",
                str(self.storage),
                "--temporary-name",
                self.name,
                "--raw-sha256",
                digest(self.payload),
                "--review-max-bytes",
                str(limit),
                "--json",
            ]
            preview = invoke(args)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            receipt = json.loads(preview.stdout)
            self.assertEqual(receipt["review_max_bytes"], limit)
            self.assertEqual(invoke([*args, "--apply"]).returncode, 2)
            applied = invoke(
                [*args, "--apply", "--expected-sha256", receipt["preview_sha256"]]
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(json.loads(applied.stdout)["status"], "completed")
