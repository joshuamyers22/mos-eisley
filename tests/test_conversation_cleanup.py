"""Temporary retention selection, writer exclusion and interrupted removal."""

import io
import json
import os
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.cli import main
from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run import conversation_cleanup as cleanup
from mos_eisley.run.conversation_cleanup import (
    TemporaryCleanupError,
    TemporaryCleanupPlan,
    TemporaryCleanupReceipt,
    cleanup_temporary_files,
)
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


class TemporaryCleanupTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = self.root / "sessions"
        state = ConversationController.fresh(self.root, demo_cassette())
        self.sid = state.session_id
        for backend in (ConversationStore, SQLiteConversationStore):
            with backend(self.storage, self.sid, self.root) as store:
                store.save(state)
        self.published = self.files()
        self.temporary = tuple(
            self.write_temp(index, payload)
            for index, payload in enumerate(
                (b"", b"PRIVATE truncated {\xff", b"x" * 70_000)
            )
        )

    def files(self) -> dict[str, tuple[bytes, int, int]]:
        return {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino)
            for path in self.storage.iterdir()
            if path.is_file()
        }

    def write_temp(self, index: int, payload: bytes) -> Path:
        path = self.storage / f".{self.sid}.{index:032x}.tmp"
        path.write_bytes(payload)
        path.chmod(0o600)
        return path

    def run_cleanup(
        self, expected: str | None = None, *, apply: bool = False
    ) -> TemporaryCleanupReceipt:
        return cleanup_temporary_files(
            self.storage, self.sid, expected_sha256=expected, apply=apply
        )

    def assert_published(self) -> None:
        current = self.files()
        self.assertEqual(
            {name: current[name] for name in self.published}, self.published
        )

    def test_preview_apply_and_new_empty_preview_preserve_published_stores(
        self,
    ) -> None:
        for name in (
            f".{self.sid}.bad.tmp",
            f".{'f' * 32}.{'e' * 32}.tmp",
            "sessions.sqlite3-journal",
            "backup.json",
        ):
            (self.storage / name).write_bytes(b"UNRELATED")
        before = self.files()
        with (
            patch.object(
                cleanup.os, "unlink", side_effect=AssertionError("preview wrote")
            ),
            patch.object(
                cleanup.os, "fsync", side_effect=AssertionError("preview synced")
            ),
        ):
            preview = self.run_cleanup()
            self.assertEqual(self.run_cleanup(), preview)
        self.assertEqual(self.files(), before)
        self.assertEqual(preview.cleanup_sha256, digest(canonical_bytes(preview.plan)))
        self.assertEqual(preview.plan.scope, "storage_owner")
        self.assertNotIn("workspace", preview.plan.model_dump())
        self.assertEqual(
            preview.plan.bytes, sum(path.stat().st_size for path in self.temporary)
        )
        self.assertNotIn("PRIVATE", preview.model_dump_json())
        result = self.run_cleanup(preview.cleanup_sha256, apply=True)
        self.assertEqual(result.status, "completed")
        self.assertTrue(result.directory_synced)
        self.assertEqual(result.removed, tuple(path.name for path in self.temporary))
        self.assertEqual(result.removed_bytes, preview.plan.bytes)
        self.assertEqual(
            self.files(),
            {
                name: value
                for name, value in before.items()
                if name not in result.removed
            },
        )
        self.assert_published()
        with self.assertRaisesRegex(ValueError, "selection changed"):
            self.run_cleanup(preview.cleanup_sha256, apply=True)
        empty = self.run_cleanup()
        self.assertEqual(empty.plan.files, ())
        self.assertEqual(empty.plan.bytes, 0)
        self.assertEqual(self.run_cleanup(empty.cleanup_sha256, apply=True).removed, ())

    def test_actual_crashed_first_save_can_be_cleaned_without_session_metadata(
        self,
    ) -> None:
        orphan = self.root / "orphan"
        sid = "f" * 32
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.run.conversation_store import ConversationStore
root = Path(sys.argv[1])
state = ConversationController.fresh(root.parent, demo_cassette()).model_copy(
    update={"session_id": sys.argv[2]}
)
with ConversationStore(root, state.session_id, root.parent) as store:
    with patch(
        "mos_eisley.run.conversation_store.os.replace",
        side_effect=lambda *a, **kw: os._exit(77),
    ):
        store.save(state)
"""
        crashed = subprocess.run(
            [sys.executable, "-c", code, str(orphan), sid],
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(crashed.returncode, 77, crashed.stderr.decode())
        self.assertFalse((orphan / f"{sid}.json").exists())
        preview = cleanup_temporary_files(orphan, sid)
        self.assertEqual(len(preview.plan.files), 1)
        self.assertGreater(preview.plan.bytes, 0)
        result = cleanup_temporary_files(
            orphan, sid, expected_sha256=preview.cleanup_sha256, apply=True
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual([path.name for path in orphan.iterdir()], [f"{sid}.lock"])

    def test_stale_content_membership_identity_and_expected_hash_prevent_all_removal(
        self,
    ) -> None:
        for change in ("content", "addition", "removal", "replacement", "lock"):
            with self.subTest(change=change):
                preview = self.run_cleanup()
                path = self.temporary[-1]
                original = path.read_bytes()
                added = self.storage / f".{self.sid}.{99:032x}.tmp"
                if change == "addition":
                    added = self.write_temp(99, b"new")
                elif change == "removal":
                    path.unlink()
                elif change == "lock":
                    lock = self.storage / f"{self.sid}.lock"
                    lock.rename(lock.with_suffix(".old"))
                    lock.touch(mode=0o600)
                elif change == "replacement":
                    replacement = self.root / "replacement"
                    replacement.write_bytes(original)
                    replacement.chmod(0o600)
                    os.replace(replacement, path)
                else:
                    info = path.stat()
                    path.write_bytes(b"y" * len(original))
                    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
                with (
                    patch.object(
                        cleanup.os,
                        "unlink",
                        side_effect=AssertionError("stale apply removed a file"),
                    ),
                    self.assertRaisesRegex(ValueError, "selection changed"),
                ):
                    self.run_cleanup(preview.cleanup_sha256, apply=True)
                if change == "addition":
                    added.unlink()
                path.write_bytes(original)
                path.chmod(0o600)
        for expected in (None, "0" * 64, "PRIVATE-invalid"):
            with self.assertRaises(ValueError):
                self.run_cleanup(expected, apply=True)
        self.assert_published_except_lock()

    def assert_published_except_lock(self) -> None:
        current = self.files()
        for name, value in self.published.items():
            if name != f"{self.sid}.lock":
                self.assertEqual(current[name], value)

    def test_active_json_and_sqlite_writers_block_preview_and_apply(self) -> None:
        preview = self.run_cleanup()
        for backend in (ConversationStore, SQLiteConversationStore):
            with backend(self.storage, self.sid, self.root, create=False):
                for apply in (False, True):
                    with self.assertRaises(BlockingIOError):
                        self.run_cleanup(preview.cleanup_sha256, apply=apply)
        self.assertTrue(all(path.exists() for path in self.temporary))
        self.assert_published()

    def test_missing_lock_root_and_invalid_id_never_create_storage(self) -> None:
        before = self.files()
        for sid in ("../PRIVATE", "A" * 32, "f" * 32):
            with self.assertRaises((ValueError, FileNotFoundError)):
                cleanup_temporary_files(self.storage, sid)
        missing = self.root / "missing"
        with self.assertRaises(FileNotFoundError):
            cleanup_temporary_files(missing, self.sid)
        self.assertFalse(missing.exists())
        self.assertEqual(self.files(), before)

    def test_all_targets_validate_before_any_unlink(self) -> None:
        path = self.temporary[-1]
        external = self.root / "external"
        external.write_bytes(b"PRIVATE external")
        external.chmod(0o600)
        for kind in ("symlink", "hardlink", "directory", "fifo", "public"):
            with self.subTest(kind=kind):
                preview = self.run_cleanup()
                path.unlink()
                if kind == "symlink":
                    path.symlink_to(external)
                elif kind == "hardlink":
                    os.link(external, path)
                elif kind == "directory":
                    path.mkdir(mode=0o700)
                elif kind == "fifo":
                    os.mkfifo(path, mode=0o600)
                else:
                    path.write_bytes(b"public")
                    path.chmod(0o644)
                with patch.object(
                    cleanup.os,
                    "unlink",
                    side_effect=AssertionError("invalid preflight removed a file"),
                ):
                    for apply in (False, True):
                        with self.assertRaises((OSError, ValueError)):
                            self.run_cleanup(preview.cleanup_sha256, apply=apply)
                if kind == "directory":
                    path.rmdir()
                else:
                    path.unlink()
                self.write_temp(2, b"restored")
        self.assertEqual(external.read_bytes(), b"PRIVATE external")
        self.assertTrue(all(path.exists() for path in self.temporary))
        self.assert_published()

    def test_private_owner_root_and_lock_validation(self) -> None:
        preview = self.run_cleanup()
        for path, mode in (
            (self.storage, 0o755),
            (self.storage / f"{self.sid}.lock", 0o644),
        ):
            original = path.stat().st_mode & 0o777
            path.chmod(mode)
            with self.assertRaises(ValueError):
                self.run_cleanup(preview.cleanup_sha256, apply=True)
            path.chmod(original)
        with (
            patch.object(cleanup.os, "getuid", return_value=os.getuid() + 1),
            self.assertRaises(ValueError),
        ):
            self.run_cleanup()
        alias = self.root / "alias"
        alias.symlink_to(self.storage, target_is_directory=True)
        with self.assertRaises(OSError):
            cleanup_temporary_files(alias, self.sid)
        self.assertTrue(all(path.exists() for path in self.temporary))

    def test_root_replacement_invalidates_preview_even_with_identical_bytes(
        self,
    ) -> None:
        preview = self.run_cleanup()
        previous = self.root / "previous"
        self.storage.rename(previous)
        shutil.copytree(previous, self.storage)
        with self.assertRaisesRegex(ValueError, "selection changed"):
            self.run_cleanup(preview.cleanup_sha256, apply=True)
        self.assertTrue(all(path.exists() for path in self.temporary))
        self.assertEqual(len(tuple(previous.glob(".*.tmp"))), 3)

    def test_file_count_and_directory_entry_limits_fail_before_reads(self) -> None:
        for index in range(3, 256):
            self.write_temp(index, b"")
        self.assertEqual(len(self.run_cleanup().plan.files), 256)
        extra = self.write_temp(256, b"")
        with (
            patch.object(
                cleanup,
                "_inspect",
                side_effect=AssertionError("read before count check"),
            ),
            self.assertRaisesRegex(ValueError, "file count limit"),
        ):
            self.run_cleanup()
        extra.unlink()
        with (
            patch.object(
                cleanup, "MAX_DIRECTORY_ENTRIES", len(tuple(self.storage.iterdir())) - 1
            ),
            patch.object(
                cleanup,
                "_inspect",
                side_effect=AssertionError("read before directory bound"),
            ),
            self.assertRaisesRegex(ValueError, "directory exceeds"),
        ):
            self.run_cleanup()

    def test_real_file_and_aggregate_byte_limits_include_empty_truncated_files(
        self,
    ) -> None:
        for path in self.temporary:
            path.unlink()
        for index in range(2):
            path = self.write_temp(index, b"")
            with path.open("r+b") as stream:
                stream.truncate(32_000_000)
        plan = self.run_cleanup().plan
        self.assertEqual(plan.bytes, 64_000_000)
        extra = self.write_temp(2, b"x")
        with self.assertRaisesRegex(ValueError, "byte limit"):
            self.run_cleanup()
        extra.unlink()
        with self.temporary[1].open("r+b") as stream:
            stream.truncate(32_000_001)
        with self.assertRaises(ValueError):
            self.run_cleanup()
        self.assertTrue(self.temporary[0].exists())

    def test_changes_while_hashing_fail_closed(self) -> None:
        original = cleanup._identity  # pyright: ignore[reportPrivateUsage]
        calls = 0

        def changed(fd: int) -> cleanup.TemporaryFileIdentity:
            nonlocal calls
            calls += 1
            if calls == 4:
                self.temporary[1].write_bytes(b"PRIVATE changed while hashing")
            return original(fd)

        with (
            patch.object(cleanup, "_identity", side_effect=changed),
            self.assertRaisesRegex(ValueError, "changed during preview"),
        ):
            self.run_cleanup()
        self.assertTrue(all(path.exists() for path in self.temporary))

    def test_partial_io_failure_reports_prefix_then_requires_fresh_preview(
        self,
    ) -> None:
        preview = self.run_cleanup()
        original = cleanup._remove  # pyright: ignore[reportPrivateUsage]

        def fail_second(root: int, selected: cleanup.TemporaryFileSelection) -> None:
            if selected.name == self.temporary[1].name:
                raise OSError("PRIVATE disk failure")
            original(root, selected)

        with (
            patch.object(cleanup, "_remove", side_effect=fail_second),
            self.assertRaises(TemporaryCleanupError) as caught,
        ):
            self.run_cleanup(preview.cleanup_sha256, apply=True)
        result = caught.exception.receipt
        self.assertEqual(result.removed, (self.temporary[0].name,))
        self.assertEqual(result.failure, "storage_unavailable")
        self.assertTrue(result.directory_synced)
        self.assertNotIn("PRIVATE", str(caught.exception) + result.model_dump_json())
        self.assertTrue(self.temporary[1].exists())
        with self.assertRaisesRegex(ValueError, "selection changed"):
            self.run_cleanup(preview.cleanup_sha256, apply=True)
        retry = self.run_cleanup()
        self.assertEqual(
            len(self.run_cleanup(retry.cleanup_sha256, apply=True).removed), 2
        )
        self.assert_published()

    def test_sync_failure_reports_unconfirmed_durability_and_empty_retry_syncs(
        self,
    ) -> None:
        preview = self.run_cleanup()
        with (
            patch.object(
                cleanup.os, "fsync", side_effect=OSError("PRIVATE sync failure")
            ),
            self.assertRaises(TemporaryCleanupError) as caught,
        ):
            self.run_cleanup(preview.cleanup_sha256, apply=True)
        result = caught.exception.receipt
        self.assertEqual(len(result.removed), 3)
        self.assertFalse(result.directory_synced)
        self.assertEqual(result.failure, "durability_unconfirmed")
        empty = self.run_cleanup()
        original = os.fsync
        with patch.object(cleanup.os, "fsync", wraps=original) as synced:
            result = self.run_cleanup(empty.cleanup_sha256, apply=True)
        synced.assert_called_once()
        self.assertTrue(result.directory_synced)
        self.assert_published()

    def test_root_lock_or_later_file_replacement_stops_after_verified_prefix(
        self,
    ) -> None:
        original = cleanup._remove  # pyright: ignore[reportPrivateUsage]
        for target in ("lock", "file", "root"):
            with self.subTest(target=target):
                for index in range(3):
                    self.write_temp(index, b"restored")
                preview = self.run_cleanup()

                def changed(
                    root: int,
                    selected: cleanup.TemporaryFileSelection,
                    target: str = target,
                ) -> None:
                    original(root, selected)
                    if selected.name == self.temporary[0].name:
                        if target == "root":
                            self.storage.rename(self.root / "old-root")
                            self.storage.mkdir(mode=0o700)
                            (self.storage / "sentinel").write_bytes(b"untouched")
                        elif target == "lock":
                            path = self.storage / f"{self.sid}.lock"
                            path.rename(self.storage / "old.lock")
                            path.touch(mode=0o600)
                        else:
                            self.temporary[1].write_bytes(
                                b"PRIVATE changed after first removal"
                            )

                with (
                    patch.object(cleanup, "_remove", side_effect=changed),
                    self.assertRaises(TemporaryCleanupError) as caught,
                ):
                    self.run_cleanup(preview.cleanup_sha256, apply=True)
                self.assertEqual(
                    caught.exception.receipt.removed, (self.temporary[0].name,)
                )
                self.assertEqual(caught.exception.receipt.failure, "selection_changed")
                if target == "root":
                    self.assertEqual(
                        [path.name for path in self.storage.iterdir()], ["sentinel"]
                    )
                    self.assertEqual(
                        len(tuple((self.root / "old-root").glob(".*.tmp"))), 2
                    )
                else:
                    self.assertTrue(self.temporary[1].exists())
                    self.assertTrue(self.temporary[2].exists())

    def test_process_crash_after_unlink_recovers_with_new_selection(self) -> None:
        preview = self.run_cleanup()
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.run.conversation_cleanup import cleanup_temporary_files
original = os.unlink
def crash(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(77)
with patch("mos_eisley.run.conversation_cleanup.os.unlink", side_effect=crash):
    cleanup_temporary_files(
        Path(sys.argv[1]), sys.argv[2], expected_sha256=sys.argv[3], apply=True
    )
"""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(self.storage),
                self.sid,
                preview.cleanup_sha256,
            ],
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 77, result.stderr.decode())
        self.assertFalse(self.temporary[0].exists())
        retry = self.run_cleanup()
        self.assertEqual(len(retry.plan.files), 2)
        self.assertEqual(
            len(self.run_cleanup(retry.cleanup_sha256, apply=True).removed), 2
        )
        self.assert_published()

    def test_contracts_reject_tampered_selection_and_receipt_claims(self) -> None:
        preview = self.run_cleanup()
        for field, value in (
            ("bytes", preview.plan.bytes + 1),
            ("session_id", "f" * 32),
            ("files", list(reversed(preview.plan.model_dump(mode="json")["files"]))),
            ("scope", "workspace"),
        ):
            changed = preview.plan.model_dump(mode="json")
            changed[field] = value
            with self.assertRaises(ValueError):
                TemporaryCleanupPlan.model_validate_json(json.dumps(changed))
        for field, value in (
            ("cleanup_sha256", "0" * 64),
            ("removed", [self.temporary[1].name]),
            ("removed_bytes", 1),
            ("status", "completed"),
            ("directory_synced", True),
            ("published_sessions_retained", False),
        ):
            changed = preview.model_dump(mode="json")
            changed[field] = value
            with self.assertRaises(ValueError):
                TemporaryCleanupReceipt.model_validate_json(json.dumps(changed))
        completed = self.run_cleanup(preview.cleanup_sha256, apply=True)
        self.assertEqual(
            completed,
            TemporaryCleanupReceipt.model_validate_json(completed.model_dump_json()),
        )
        for field, value in (
            ("removed", list(completed.removed[:-1])),
            ("directory_synced", False),
            ("failure", "storage_unavailable"),
        ):
            changed = completed.model_dump(mode="json")
            changed[field] = value
            with self.assertRaises(ValueError):
                TemporaryCleanupReceipt.model_validate_json(json.dumps(changed))

    def test_cli_preview_apply_and_redacted_validation(self) -> None:
        args = [
            sys.executable,
            "-m",
            "mos_eisley.cli",
            "session-cleanup",
            self.sid,
            "--storage",
            str(self.storage),
            "--json",
        ]
        preview = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        payload = json.loads(preview.stdout)
        self.assertEqual(payload["type"], "conversation.cleanup")
        self.assertEqual(payload["mode"], "preview")
        self.assertNotIn("PRIVATE", preview.stdout + preview.stderr)
        missing_hash = subprocess.run(
            [*args, "--apply"], capture_output=True, text=True, timeout=30
        )
        self.assertEqual(missing_hash.returncode, 2)
        applied = subprocess.run(
            [*args, "--apply", "--expected-sha256", payload["cleanup_sha256"]],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(json.loads(applied.stdout)["status"], "completed")
        args[4] = "PRIVATE-invalid"
        invalid = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(invalid.returncode, 2)
        self.assertNotIn("PRIVATE", invalid.stdout + invalid.stderr)
        self.assert_published()

    def test_cli_partial_receipt_and_schema_error_do_not_echo_private_bytes(
        self,
    ) -> None:
        preview = self.run_cleanup()
        output = io.StringIO()
        errors = io.StringIO()
        args = ["session-cleanup", self.sid, "--storage", str(self.storage), "--json"]
        with (
            patch.object(cleanup, "_remove", side_effect=OSError("PRIVATE failure")),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            status = main(
                [*args, "--apply", "--expected-sha256", preview.cleanup_sha256]
            )
        self.assertEqual(status, 2)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "stopped")
        self.assertEqual(payload["removed"], [])
        self.assertEqual(payload["failure"], "storage_unavailable")
        self.assertIn("preview remaining files again", payload["text"])
        self.assertNotIn("PRIVATE", output.getvalue() + errors.getvalue())
        with self.temporary[-1].open("r+b") as stream:
            stream.truncate(32_000_001)
        output = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(args)
        self.assertEqual(status, 2)
        self.assertIn("validation failed", errors.getvalue())
        self.assertNotIn("PRIVATE", output.getvalue() + errors.getvalue())

    def test_hash_reads_are_chunked_and_detect_growth_past_selected_size(self) -> None:
        original = cleanup.hashlib.sha256
        blocks: list[int] = []
        path = self.temporary[-1]

        def checksum():
            value = original()

            class ObservedHash:
                def update(self, block: bytes) -> None:
                    blocks.append(len(block))
                    value.update(block)
                    if len(block) == 65_536:
                        with path.open("ab") as stream:
                            stream.write(b"PRIVATE growth")

                def hexdigest(self) -> str:
                    return value.hexdigest()

            return ObservedHash()

        with (
            patch.object(cleanup.hashlib, "sha256", side_effect=checksum),
            self.assertRaisesRegex(ValueError, "changed during preview"),
        ):
            self.run_cleanup()
        self.assertTrue(blocks)
        self.assertLessEqual(max(blocks), 65_536)
        self.assertTrue(all(path.exists() for path in self.temporary))
