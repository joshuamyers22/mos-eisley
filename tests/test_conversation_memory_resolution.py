"""Reviewed collision resolution preserves source and a durable prior target."""

import fcntl
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_memory import (
    MEMORY_BYTES,
    MemoryChangedError,
    MemorySnapshot,
    MemoryStore,
)
from mos_eisley.conversation_memory_migration import Resolution, resolve_memory_project
from mos_eisley.core.models import canonical_bytes


class MemoryResolutionTests(TestCase):
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

    def seed(self) -> None:
        self.source.change("project", "set", text="Workspace decisions")
        self.target.change("project", "set", text="Root decisions")
        self.source.change("user", "set", text="Personal preferences")

    def resolve(
        self,
        strategy: Resolution = "append-source",
        *,
        text: str | None = None,
        receipt: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return resolve_memory_project(
            self.storage,
            self.workspace,
            self.project,
            strategy=strategy,
            text=text,
            expected_sha256=str(receipt["preview_sha256"]) if receipt else None,
        )

    def test_preview_and_apply_preserve_source_user_and_prior_target(self) -> None:
        self.seed()
        before = {
            p.name: (p.read_bytes(), p.stat().st_mtime_ns)
            for p in self.storage.iterdir()
        }
        receipt = self.resolve()
        self.assertEqual(receipt, self.resolve())
        self.assertTrue(receipt["will_write"])
        self.assertFalse(receipt["backup_exists"])
        self.assertFalse(receipt["applied"])
        self.assertIsNone(receipt["result"])
        for name, value in before.items():
            path = self.storage / name
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), value)
        started = datetime.now(UTC)
        result = self.resolve(receipt=receipt)
        snapshot = MemorySnapshot.model_validate_json(json.dumps(result["result"]))
        self.assertEqual(self.target.read("project"), snapshot)
        self.assertEqual(
            snapshot.document.text, "Root decisions\n\nWorkspace decisions"
        )
        self.assertGreaterEqual(snapshot.document.updated_at, started)
        self.assertEqual(snapshot.document.revision, 2)
        backup = Path(str(receipt["backup_path"]))
        self.assertEqual(
            backup.read_bytes(), before[self.target.path("project").name][0]
        )
        self.assertEqual(backup.stat().st_nlink, 1)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        for path in (self.source.path("project"), self.source.path("user")):
            self.assertEqual(
                (path.read_bytes(), path.stat().st_mtime_ns), before[path.name]
            )
        with self.assertRaisesRegex(ValueError, "changed"):
            self.resolve(receipt=receipt)

    def test_strategies_preserve_disabled_target_and_do_not_deduplicate(self) -> None:
        cases: tuple[tuple[Resolution, str | None, str], ...] = (
            ("use-source", None, "Workspace decisions"),
            ("append-source", None, "Root decisions\n\nWorkspace decisions"),
            ("use-text", "Reviewed combined text", "Reviewed combined text"),
            ("use-text", "", ""),
        )
        for strategy, supplied, expected in cases:
            with self.subTest(strategy=strategy, supplied=supplied):
                self.seed()
                self.target.change("project", "disable")
                receipt = self.resolve(strategy, text=supplied)
                result = self.resolve(strategy, text=supplied, receipt=receipt)
                snapshot = MemorySnapshot.model_validate_json(
                    json.dumps(result["result"])
                )
                self.assertEqual(snapshot.document.text, expected)
                self.assertFalse(snapshot.document.enabled)
        self.source.change("project", "set", text="Repeated")
        self.target.change("project", "set", text="Repeated")
        receipt = self.resolve()
        result = self.resolve(receipt=receipt)
        snapshot = MemorySnapshot.model_validate_json(json.dumps(result["result"]))
        self.assertEqual(snapshot.document.text, "Repeated\n\nRepeated")

    def test_keep_target_and_identical_replacement_are_true_noops(self) -> None:
        self.seed()
        cases: tuple[tuple[Resolution, str | None], ...] = (
            ("keep-target", None),
            ("use-text", "Root decisions"),
        )
        for strategy, text in cases:
            with self.subTest(strategy=strategy):
                before = {
                    p.name: (p.read_bytes(), p.stat().st_ctime_ns)
                    for p in self.storage.iterdir()
                }
                receipt = self.resolve(strategy, text=text)
                self.assertFalse(receipt["will_write"])
                self.assertIsNone(receipt["backup_path"])
                self.resolve(strategy, text=text, receipt=receipt)
                self.resolve(strategy, text=text, receipt=receipt)
                after = {
                    p.name: (p.read_bytes(), p.stat().st_ctime_ns)
                    for p in self.storage.iterdir()
                }
                self.assertEqual(before, after)

    def test_stale_source_target_strategy_and_text_are_rejected_before_backup(
        self,
    ) -> None:
        self.seed()
        receipt = self.resolve()
        cases: tuple[tuple[Resolution, str | None], ...] = (
            ("use-source", None),
            ("use-text", "Other"),
        )
        for strategy, text in cases:
            with self.assertRaisesRegex(ValueError, "changed"):
                self.resolve(strategy, text=text, receipt=receipt)
        for store in (self.source, self.target):
            receipt = self.resolve()
            store.change("project", "append", text="New decision")
            with self.assertRaisesRegex(ValueError, "changed"):
                self.resolve(receipt=receipt)
        self.assertFalse(list(self.storage.glob("resolution-backup-*")))

    def test_missing_or_identical_identities_and_invalid_arguments_create_nothing(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "existing"):
            self.resolve()
        self.assertFalse(self.storage.exists())
        with self.assertRaisesRegex(ValueError, "distinct"):
            resolve_memory_project(
                self.storage, self.workspace, self.workspace, strategy="keep-target"
            )
        self.source.change("project", "set", text="Only source")
        with self.assertRaisesRegex(ValueError, "existing"):
            self.resolve()
        cases: tuple[tuple[Resolution, str | None], ...] = (
            ("use-text", None),
            ("use-source", "unexpected"),
        )
        for strategy, text in cases:
            with self.assertRaisesRegex(ValueError, "--text"):
                self.resolve(strategy, text=text)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.resolve(receipt={"preview_sha256": "bad"})
        self.assertFalse(self.target.path("project").exists())

    def test_oversized_reconciliation_is_rejected_without_writes(self) -> None:
        self.seed()
        with self.assertRaises(ValueError):
            self.resolve("use-text", text="é" * (MEMORY_BYTES // 2 + 1))
        self.source.change("project", "set", text="x" * (MEMORY_BYTES // 2))
        self.target.change("project", "set", text="y" * (MEMORY_BYTES // 2))
        with self.assertRaises(ValueError):
            self.resolve()
        self.assertFalse(list(self.storage.glob("resolution-backup-*")))

    def test_empty_disabled_documents_are_collisions(self) -> None:
        self.source.change("project", "disable")
        self.target.change("project", "disable")
        receipt = self.resolve("use-text", text="Reviewed text")
        self.resolve("use-text", text="Reviewed text", receipt=receipt)
        snapshot = self.target.read("project")
        assert snapshot is not None
        self.assertFalse(snapshot.document.enabled)
        self.assertEqual(snapshot.document.text, "Reviewed text")

    def test_replaced_file_directory_and_lock_invalidate_receipt(self) -> None:
        self.seed()
        for path in (
            self.workspace,
            self.project,
            self.source.path("project"),
            self.target.path("project"),
            self.storage / "memory.lock",
            self.storage,
        ):
            with self.subTest(path=path):
                receipt = self.resolve()
                moved = path.with_name(path.name + "-old")
                path.rename(moved)
                if moved.is_dir():
                    shutil.copytree(moved, path)
                else:
                    shutil.copy2(moved, path)
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.resolve(receipt=receipt)
        self.assertFalse(list(self.storage.glob("resolution-backup-*")))

    def test_unsafe_source_links_and_backup_are_rejected(self) -> None:
        self.seed()
        receipt = self.resolve()
        extra = self.base / "extra"
        os.link(self.source.path("project"), extra)
        with self.assertRaisesRegex(ValueError, "private"):
            self.resolve(receipt=receipt)
        extra.unlink()
        backup = Path(str(receipt["backup_path"]))
        backup.write_text("wrong bytes", encoding="utf-8")
        backup.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "backup"):
            self.resolve()
        self.assertEqual(backup.read_text(), "wrong bytes")
        backup.unlink()
        backup.symlink_to(self.target.path("project"))
        with self.assertRaises(OSError):
            self.resolve()
        self.assertTrue(backup.is_symlink())

    def test_existing_verified_backup_is_reused(self) -> None:
        self.seed()
        receipt = self.resolve()
        backup = Path(str(receipt["backup_path"]))
        backup.write_bytes(self.target.path("project").read_bytes())
        backup.chmod(0o600)
        before = (backup.read_bytes(), backup.stat().st_ino)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.resolve(receipt=receipt)
        fresh = self.resolve()
        self.assertTrue(fresh["backup_exists"])
        self.resolve(receipt=fresh)
        self.assertEqual((backup.read_bytes(), backup.stat().st_ino), before)

    def test_exclusive_lock_blocks_apply_but_allows_preview(self) -> None:
        self.seed()
        receipt = self.resolve()
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(receipt, self.resolve())
            with self.assertRaises(BlockingIOError):
                self.resolve(receipt=receipt)
        self.assertFalse(Path(str(receipt["backup_path"])).exists())

    def test_backup_flush_failure_preserves_both_documents(self) -> None:
        self.seed()
        receipt = self.resolve()
        old = self.target.path("project").read_bytes()
        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.fsync",
                side_effect=OSError("sync"),
            ),
            self.assertRaisesRegex(OSError, "sync"),
        ):
            self.resolve(receipt=receipt)
        self.assertEqual(self.target.path("project").read_bytes(), old)
        self.assertFalse(Path(str(receipt["backup_path"])).exists())
        self.assertFalse(list(self.storage.glob(".memory-*.tmp")))

    def test_target_replace_failure_retains_durable_backup_and_allows_fresh_retry(
        self,
    ) -> None:
        self.seed()
        receipt = self.resolve()
        old = self.target.path("project").read_bytes()
        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.replace",
                side_effect=OSError("replace"),
            ),
            self.assertRaisesRegex(OSError, "replace"),
        ):
            self.resolve(receipt=receipt)
        self.assertEqual(self.target.path("project").read_bytes(), old)
        self.assertEqual(Path(str(receipt["backup_path"])).read_bytes(), old)
        self.assertFalse(list(self.storage.glob(".memory-*.tmp")))
        with self.assertRaisesRegex(ValueError, "changed"):
            self.resolve(receipt=receipt)
        self.resolve(receipt=self.resolve())

    def test_late_target_change_is_not_overwritten(self) -> None:
        self.seed()
        alternate = self.target.change("project", "append", text="Concurrent edit")
        self.target.change("project", "set", text="Root decisions")
        receipt = self.resolve()
        fsync = os.fsync
        regular_flushes = 0

        def changed(fd: int) -> None:
            nonlocal regular_flushes
            fsync(fd)
            if stat.S_ISREG(os.fstat(fd).st_mode):
                regular_flushes += 1
                if regular_flushes == 3:
                    self.target.path("project").write_bytes(canonical_bytes(alternate))

        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.fsync", side_effect=changed
            ),
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            self.resolve(receipt=receipt)
        self.assertEqual(self.target.read("project"), alternate)
        self.assertTrue(Path(str(receipt["backup_path"])).exists())

    def test_flush_failure_after_replace_preserves_result_and_backup_and_blocks_replay(
        self,
    ) -> None:
        self.seed()
        receipt = self.resolve()
        old = self.target.path("project").read_bytes()
        fsync = os.fsync

        def fail_after_replace(fd: int) -> None:
            fsync(fd)
            if (
                stat.S_ISDIR(os.fstat(fd).st_mode)
                and self.target.path("project").read_bytes() != old
            ):
                raise OSError("published")

        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.fsync",
                side_effect=fail_after_replace,
            ),
            self.assertRaisesRegex(OSError, "published"),
        ):
            self.resolve(receipt=receipt)
        snapshot = self.target.read("project")
        assert snapshot is not None
        self.assertEqual(
            snapshot.document.text, "Root decisions\n\nWorkspace decisions"
        )
        self.assertEqual(Path(str(receipt["backup_path"])).read_bytes(), old)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.resolve(receipt=receipt)

    def test_cli_requires_review_flags_and_applies_supplied_text(self) -> None:
        self.seed()
        args = [
            sys.executable,
            "-m",
            "mos_eisley.cli",
            "memory-project-resolve",
            "-C",
            str(self.workspace),
            "--memory-project-root",
            str(self.project),
            "--memory-storage",
            str(self.storage),
            "--strategy",
            "use-text",
            "--text",
            "Reviewed text",
            "--json",
        ]
        for flags in (("--apply",), ("--expected-sha256", "0" * 64)):
            result = subprocess.run(
                [*args, *flags], capture_output=True, text=True, timeout=15
            )
            self.assertNotEqual(result.returncode, 0)
        preview = subprocess.run(args, capture_output=True, text=True, timeout=15)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        receipt = json.loads(preview.stdout)
        self.assertEqual(receipt["type"], "memory.project_resolution")
        applied = subprocess.run(
            [*args, "--apply", "--expected-sha256", receipt["preview_sha256"]],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(
            json.loads(applied.stdout)["result"]["document"]["text"], "Reviewed text"
        )

    def test_changed_memory_guard_pauses_root_context_but_preserves_workspace_context(
        self,
    ) -> None:
        self.seed()
        source_context = self.source.load()
        root_context = self.target.load()
        receipt = self.resolve()
        self.resolve(receipt=receipt)
        self.source.check(source_context)
        with self.assertRaises(MemoryChangedError):
            self.target.check(root_context)
        assert root_context is not None and root_context.project is not None
        backup = MemorySnapshot.model_validate_json(
            Path(str(receipt["backup_path"])).read_bytes()
        )
        self.assertEqual(root_context.project, backup)

    def test_process_death_during_backup_or_replacement_preserves_prior_version(
        self,
    ) -> None:
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_migration import resolve_memory_project
original_replace, original_link = os.replace, os.link
def interrupted_replace(*args, **kwargs):
    if sys.argv[5] == 'before':
        os._exit(77)
    original_replace(*args, **kwargs)
    os._exit(77)
def interrupted_link(*args, **kwargs):
    original_link(*args, **kwargs)
    if sys.argv[5] == 'backup':
        os._exit(77)
module = 'mos_eisley.conversation_memory_migration.os.'
with (
    patch(module + 'replace', side_effect=interrupted_replace),
    patch(module + 'link', side_effect=interrupted_link),
):
    resolve_memory_project(
        Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]),
        strategy='append-source', expected_sha256=sys.argv[4],
    )
"""
        for phase in ("backup", "before", "after"):
            with self.subTest(phase=phase):
                self.seed()
                receipt = self.resolve()
                source = self.source.path("project").read_bytes()
                old_target = self.target.path("project").read_bytes()
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        code,
                        str(self.storage),
                        str(self.workspace),
                        str(self.project),
                        str(receipt["preview_sha256"]),
                        phase,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 77, result.stderr)
                self.assertEqual(self.source.path("project").read_bytes(), source)
                backup = Path(str(receipt["backup_path"]))
                self.assertEqual(backup.read_bytes(), old_target)
                current = self.target.read("project")
                assert current is not None
                if phase == "after":
                    self.assertEqual(
                        current.document.text, "Root decisions\n\nWorkspace decisions"
                    )
                else:
                    self.assertEqual(
                        self.target.path("project").read_bytes(), old_target
                    )
                with self.assertRaises(ValueError):
                    self.resolve(receipt=receipt)
                if phase == "backup":
                    self.assertEqual(backup.stat().st_nlink, 2)
                    with self.assertRaisesRegex(ValueError, "backup"):
                        self.resolve()
                elif phase == "before":
                    self.assertTrue(self.resolve()["backup_exists"])
