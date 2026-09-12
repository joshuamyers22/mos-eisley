"""Unattributed invalid staging cleanup binds raw bytes and preserves stored data."""

import base64
import fcntl
import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_memory import RECORD_BYTES, MemorySnapshot, MemoryStore
from mos_eisley.conversation_memory_staging import (
    MemoryStagingDiscardError,
    discard_memory_staging,
)
from mos_eisley.core.models import canonical_bytes, digest


class MemoryStagingTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "project"
        self.workspace.mkdir()
        self.storage = self.base / "memory"
        self.store = MemoryStore(self.storage, self.workspace)
        self.project = self.store.change(
            "project", "set", text="Live project decisions"
        )
        self.user = self.store.change("user", "set", text="Private preferences")
        self.name = ".memory-migration-" + "1" * 32 + ".tmp"
        self.path = self.storage / self.name
        self.payload = b'{"document":{"text":"incomplete\x00\xff\x1b[2J'
        self.seed()

    def seed(self, payload: bytes | None = None) -> None:
        if payload is not None:
            self.payload = payload
        self.path.write_bytes(self.payload)
        self.path.chmod(0o600)

    def discard(self, receipt: dict[str, object] | None = None) -> dict[str, object]:
        return discard_memory_staging(
            self.storage,
            self.name,
            digest(self.payload),
            expected_sha256=str(receipt["preview_sha256"]) if receipt else None,
        )

    def test_raw_review_is_complete_unattributed_and_preserves_all_other_files(
        self,
    ) -> None:
        unrelated = self.storage / (".memory-resolution-" + "2" * 32 + ".tmp")
        unrelated.write_bytes(b"other invalid record")
        backup = self.storage / ("resolution-backup-" + "3" * 64 + ".json")
        backup.write_bytes(b"unrelated backup")
        before = {
            p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.storage.iterdir()
        }
        receipt = self.discard()
        self.assertEqual(receipt, self.discard())
        self.assertEqual(receipt["scope"], "storage")
        self.assertIsNone(receipt["project_identity"])
        self.assertFalse(receipt["project_identity_verified"])
        self.assertEqual(
            base64.b64decode(str(receipt["raw_bytes_base64"])), self.payload
        )
        self.assertEqual(receipt["raw_sha256"], digest(self.payload))
        self.assertNotIn("\x1b", json.dumps(receipt))
        self.assertEqual(
            before,
            {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.storage.iterdir()},
        )
        applied = self.discard(receipt)
        self.assertEqual(applied["status"], "completed")
        self.assertTrue(applied["removed"])
        self.assertTrue(applied["synced"])
        self.assertFalse(self.path.exists())
        for path, observed in before.items():
            if path != self.path:
                self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), observed)
        with self.assertRaises(FileNotFoundError):
            self.discard(receipt)

    def test_empty_corrupt_and_maximum_size_records_are_reviewed_without_scans(
        self,
    ) -> None:
        corrupt = canonical_bytes(self.project).replace(b"Live", b"Dead")
        for payload in (b"", corrupt, b"\xff" * RECORD_BYTES):
            with self.subTest(size=len(payload)):
                self.seed(payload)
                with patch("os.scandir", side_effect=AssertionError("unexpected scan")):
                    receipt = self.discard()
                    self.assertEqual(
                        base64.b64decode(str(receipt["raw_bytes_base64"])), payload
                    )
                    self.discard(receipt)
        self.assertEqual(self.store.read("project"), self.project)

    def test_all_valid_snapshots_are_refused_even_foreign_or_noncanonical(self) -> None:
        foreign_doc = self.project.document.model_copy(
            update={"owner_uid": os.getuid() + 1, "workspace": str(self.base)}
        )
        foreign = MemorySnapshot(
            document=foreign_doc, sha256=digest(canonical_bytes(foreign_doc))
        )
        for snapshot in (self.project, self.user, foreign):
            for payload in (
                canonical_bytes(snapshot),
                canonical_bytes(snapshot) + b"\n",
            ):
                with self.subTest(
                    snapshot=snapshot.sha256, canonical=not payload.endswith(b"\n")
                ):
                    self.seed(payload)
                    with self.assertRaisesRegex(ValueError, "Valid snapshots"):
                        self.discard()
                    self.assertTrue(self.path.exists())

    def test_bound_filename_hash_and_size_validation(self) -> None:
        for name in (
            "../outside",
            "user.json",
            self.store.path("project").name,
            "resolution-backup-" + "1" * 64 + ".json",
            ".memory-" + "1" * 32 + ".tmp",
            self.name + "\n",
            ".memory-migration-*.tmp",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                discard_memory_staging(self.storage, name, digest(self.payload))
        for raw_hash in ("x", "A" * 64, "0" * 64 + "\n", "0" * 64):
            with self.subTest(raw_hash=raw_hash), self.assertRaises(ValueError):
                discard_memory_staging(self.storage, self.name, raw_hash)
        with self.assertRaises(ValueError):
            discard_memory_staging(
                self.storage, self.name, digest(self.payload), expected_sha256="bad"
            )
        self.seed(b"x" * (RECORD_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "256 KiB"):
            self.discard()

    def test_unsafe_files_are_refused_and_open_descriptors_close(self) -> None:
        alias = self.storage / "alias"
        os.link(self.path, alias)
        with self.assertRaises(ValueError):
            self.discard()
        alias.unlink()
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.discard()
        self.path.chmod(0o600)
        self.path.rename(alias)
        self.path.symlink_to(alias)
        with self.assertRaises(OSError):
            self.discard()
        self.path.unlink()
        original_open = os.open
        opened: list[int] = []

        def tracked_open(*args: Any, **kwargs: Any) -> int:
            fd = original_open(*args, **kwargs)
            if args[0] == self.name:
                opened.append(fd)
            return fd

        for kind in ("directory", "fifo"):
            if kind == "directory":
                self.path.mkdir()
            else:
                os.mkfifo(self.path, 0o600)
            with (
                patch("os.open", side_effect=tracked_open),
                self.assertRaises(ValueError),
            ):
                self.discard()
            with self.assertRaises(OSError):
                os.fstat(opened[-1])
            if kind == "directory":
                self.path.rmdir()
            else:
                self.path.unlink()
        self.assertEqual(self.store.read("project"), self.project)

    def test_byte_identity_timestamp_and_completion_changes_reject_old_review(
        self,
    ) -> None:
        receipt = self.discard()
        self.path.write_bytes(self.payload + b"!")
        with self.assertRaisesRegex(ValueError, "raw hash"):
            self.discard(receipt)
        self.seed()
        receipt = self.discard()
        replacement = self.storage / "replacement"
        replacement.write_bytes(self.payload)
        replacement.chmod(0o600)
        os.replace(replacement, self.path)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.discard(receipt)
        receipt = self.discard()
        os.utime(self.path, ns=(1, 1))
        with self.assertRaisesRegex(ValueError, "changed"):
            self.discard(receipt)
        receipt = self.discard()
        self.seed(canonical_bytes(self.project))
        with self.assertRaisesRegex(ValueError, "Valid snapshots"):
            self.discard(receipt)
        self.assertTrue(self.path.exists())

    def test_storage_lock_replacement_and_private_mode_changes_reject_approval(
        self,
    ) -> None:
        receipt = self.discard()
        lock = self.storage / "memory.lock"
        lock.rename(self.storage / "old.lock")
        lock.touch(mode=0o600)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.discard(receipt)
        receipt = self.discard()
        moved = self.base / "old-memory"
        self.storage.rename(moved)
        self.storage.mkdir(mode=0o700)
        for path in moved.iterdir():
            (self.storage / path.name).write_bytes(path.read_bytes())
            (self.storage / path.name).chmod(0o600)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.discard(receipt)
        self.storage.chmod(0o755)
        with self.assertRaises(ValueError):
            self.discard()
        self.storage.chmod(0o700)
        lock.chmod(0o644)
        with self.assertRaises(ValueError):
            self.discard()

    def test_missing_storage_or_lock_are_never_created(self) -> None:
        missing = self.base / "missing"
        with self.assertRaisesRegex(ValueError, "existing memory"):
            discard_memory_staging(missing, self.name, digest(self.payload))
        self.assertFalse(missing.exists())
        (self.storage / "memory.lock").unlink()
        with self.assertRaises(FileNotFoundError):
            self.discard()
        self.assertFalse((self.storage / "memory.lock").exists())
        self.assertTrue(self.path.exists())

    def test_shared_lock_blocks_apply_and_no_workspace_or_current_document_is_read(
        self,
    ) -> None:
        receipt = self.discard()
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(receipt, self.discard())
            with self.assertRaises(BlockingIOError):
                self.discard(receipt)
        self.workspace.rmdir()
        self.store.path("project").write_bytes(b"unrelated damaged live record")
        self.assertEqual(receipt, self.discard())
        self.discard(receipt)
        self.assertFalse(self.workspace.exists())
        self.assertEqual(
            self.store.path("project").read_bytes(), b"unrelated damaged live record"
        )

    def test_replacement_during_read_or_reinspection_prevents_unlink(self) -> None:
        real_stat = os.stat
        observed = 0
        replace_at = 1

        def replace_on_stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
            nonlocal observed
            if path == self.name:
                observed += 1
            if path == self.name and observed == replace_at:
                replacement = self.storage / "replacement"
                replacement.write_bytes(self.payload)
                replacement.chmod(0o600)
                os.replace(replacement, self.path)
            return real_stat(path, *args, **kwargs)

        with (
            patch("os.stat", side_effect=replace_on_stat),
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            self.discard()
        receipt = self.discard()
        observed = 0
        replace_at = 2
        with (
            patch("os.stat", side_effect=replace_on_stat),
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            self.discard(receipt)
        self.assertTrue(self.path.exists())

    def test_unlink_and_flush_faults_report_actual_in_process_progress(self) -> None:
        for boundary in ("unlink", "fsync"):
            with self.subTest(boundary=boundary):
                self.seed()
                receipt = self.discard()
                with (
                    patch("os." + boundary, side_effect=OSError("injected fault")),
                    self.assertRaises(MemoryStagingDiscardError) as caught,
                ):
                    self.discard(receipt)
                result = caught.exception.receipt
                self.assertEqual(result["status"], "incomplete")
                self.assertEqual(result["removed"], boundary == "fsync")
                self.assertFalse(result["synced"])
                self.assertEqual(self.path.exists(), boundary == "unlink")
                self.assertEqual(self.store.read("project"), self.project)

    def test_cli_requires_exact_apply_pair_and_reports_partial_receipt(self) -> None:
        from mos_eisley.cli import main

        command = [
            "memory-staging-discard",
            "--memory-storage",
            str(self.storage),
            "--temporary-name",
            self.name,
            "--raw-sha256",
            digest(self.payload),
            "--json",
        ]
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(command), 0)
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["type"], "memory.staging_discard")
        for flags in (
            ["--apply"],
            ["--expected-sha256", receipt["preview_sha256"]],
            ["--apply", "--expected-sha256", "0" * 64],
        ):
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertNotEqual(main([*command, *flags]), 0)
            self.assertTrue(self.path.exists())
        output = StringIO()
        with (
            redirect_stdout(output),
            patch("os.fsync", side_effect=OSError("injected fault")),
        ):
            self.assertEqual(
                main(
                    [
                        *command,
                        "--apply",
                        "--expected-sha256",
                        receipt["preview_sha256"],
                    ]
                ),
                2,
            )
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(result["removed"])
        self.assertFalse(result["synced"])

    def test_foreign_file_owner_is_rejected_even_when_raw_hash_matches(self) -> None:
        inode = self.path.stat().st_ino
        real_fstat = os.fstat

        def foreign_owner(fd: int) -> os.stat_result:
            info = real_fstat(fd)
            if info.st_ino == inode:
                fields = list(info)
                fields[4] = os.getuid() + 1
                return os.stat_result(fields)
            return info

        with (
            patch("os.fstat", side_effect=foreign_owner),
            self.assertRaises(ValueError),
        ):
            self.discard()
        self.assertTrue(self.path.exists())

    def test_actual_interrupted_copy_leaves_empty_or_partial_reviewable_staging(
        self,
    ) -> None:
        self.path.unlink()
        target = self.base / "destination"
        target.mkdir()
        target_store = MemoryStore(self.storage, target)
        before = {p: p.read_bytes() for p in self.storage.iterdir()}
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_migration import relocate_memory_project
storage, source, target = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
preview = relocate_memory_project(storage, source, target)
fdopen = os.fdopen
class PartialWriter:
    def __init__(self, stream):
        self.stream = stream
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.stream.close()
    def write(self, payload):
        self.stream.write(payload[:int(sys.argv[4])])
        self.stream.flush()
        os.fsync(self.stream.fileno())
        os._exit(73)
def interrupted_open(fd, mode, *args, **kwargs):
    stream = fdopen(fd, mode, *args, **kwargs)
    return PartialWriter(stream) if mode == 'wb' else stream
with patch('os.fdopen', side_effect=interrupted_open):
    relocate_memory_project(storage, source, target,
                            expected_sha256=preview['preview_sha256'])
"""
        for count in (0, 37):
            with self.subTest(written=count):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        code,
                        str(self.storage),
                        str(self.workspace),
                        str(target),
                        str(count),
                    ],
                    capture_output=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 73, result.stderr)
                candidates = list(self.storage.glob(".memory-migration-*.tmp"))
                self.assertEqual(len(candidates), 1)
                path = candidates[0]
                payload = path.read_bytes()
                self.assertEqual(len(payload), count)
                receipt = discard_memory_staging(
                    self.storage, path.name, digest(payload)
                )
                discard_memory_staging(
                    self.storage,
                    path.name,
                    digest(payload),
                    expected_sha256=str(receipt["preview_sha256"]),
                )
                self.assertFalse(path.exists())
                self.assertFalse(target_store.path("project").exists())
                self.assertEqual(
                    before, {p: p.read_bytes() for p in self.storage.iterdir()}
                )

    def test_actual_process_death_after_unlink_preserves_other_memory(self) -> None:
        receipt = self.discard()
        before = {p: p.read_bytes() for p in self.storage.iterdir() if p != self.path}
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_staging import discard_memory_staging
with patch('os.fsync', side_effect=lambda fd: os._exit(74)):
    discard_memory_staging(Path(sys.argv[1]), sys.argv[2], sys.argv[3],
                           expected_sha256=sys.argv[4])
"""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(self.storage),
                self.name,
                digest(self.payload),
                str(receipt["preview_sha256"]),
            ],
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 74, result.stderr)
        self.assertFalse(self.path.exists())
        self.assertEqual(before, {p: p.read_bytes() for p in self.storage.iterdir()})
        with self.assertRaises(FileNotFoundError):
            self.discard(receipt)
