"""Cross-project collisions require a separate, identity-bound resolution review."""

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

from mos_eisley.conversation_memory import (
    MemoryChangedError,
    MemorySnapshot,
    MemoryStore,
)
from mos_eisley.conversation_memory_migration import (
    Resolution,
    relocate_memory_project,
    resolve_memory_project,
)
from mos_eisley.core.models import canonical_bytes


class MappedResolutionTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.old = self.base / "original" / "project"
        self.old.mkdir(parents=True)
        self.new = self.base / "other-worktree"
        self.new.mkdir()
        self.storage = self.base / "memory"
        self.source = MemoryStore(self.storage, self.old)
        self.target = MemoryStore(self.storage, self.new)

    def seed(self, *, vanished: bool = True) -> None:
        self.source.change("project", "set", text="Source decisions")
        self.target.change("project", "set", text="Destination decisions")
        self.target.change("user", "set", text="Personal preferences")
        if vanished and self.old.exists():
            self.old.rmdir()

    def resolve(
        self,
        strategy: Resolution = "append-source",
        *,
        text: str | None = None,
        receipt: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return relocate_memory_project(
            self.storage,
            str(self.old),
            self.new,
            strategy=strategy,
            text=text,
            expected_sha256=str(receipt["preview_sha256"]) if receipt else None,
        )

    def test_strategies_preserve_source_user_and_disabled_target_with_backup(
        self,
    ) -> None:
        cases: tuple[tuple[Resolution, str | None, str], ...] = (
            ("use-source", None, "Source decisions"),
            ("append-source", None, "Destination decisions\n\nSource decisions"),
            ("use-text", "Reviewed decisions", "Reviewed decisions"),
            ("use-text", "", ""),
        )
        for vanished in (False, True):
            for strategy, text, expected in cases:
                with self.subTest(vanished=vanished, strategy=strategy, text=text):
                    self.seed(vanished=vanished)
                    self.target.change("project", "disable")
                    before = {p: p.read_bytes() for p in self.storage.iterdir()}
                    old = self.target.read("project")
                    assert old is not None
                    preview = self.resolve(strategy, text=text)
                    self.assertEqual(preview, self.resolve(strategy, text=text))
                    self.assertEqual(
                        preview["operation"], "resolve-relocated-project-memory"
                    )
                    self.assertTrue(
                        all(p.read_bytes() == value for p, value in before.items())
                    )
                    result = self.resolve(strategy, text=text, receipt=preview)
                    snapshot = MemorySnapshot.model_validate_json(
                        json.dumps(result["result"])
                    )
                    self.assertEqual(snapshot, self.target.read("project"))
                    self.assertEqual(snapshot.document.text, expected)
                    self.assertEqual(snapshot.document.workspace, str(self.new))
                    self.assertFalse(snapshot.document.enabled)
                    self.assertEqual(
                        snapshot.document.revision, old.document.revision + 1
                    )
                    self.assertGreaterEqual(
                        snapshot.document.updated_at, old.document.updated_at
                    )
                    backup = Path(str(preview["backup_path"]))
                    self.assertEqual(backup.read_bytes(), canonical_bytes(old))
                    self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(backup.stat().st_nlink, 1)
                    for path in (self.source.path("project"), self.source.path("user")):
                        self.assertEqual(path.read_bytes(), before[path])
                    self.assertEqual(self.old.exists(), not vanished)

    def test_noop_preserves_all_bytes_and_metadata_without_backup(self) -> None:
        self.seed()
        cases: tuple[tuple[Resolution, str | None], ...] = (
            ("keep-target", None),
            ("use-text", "Destination decisions"),
        )
        for strategy, text in cases:
            with self.subTest(strategy=strategy):
                before = {
                    p: (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.storage.iterdir()
                }
                preview = self.resolve(strategy, text=text)
                self.assertFalse(preview["will_write"])
                self.assertIsNone(preview["backup_path"])
                self.assertTrue(
                    self.resolve(strategy, text=text, receipt=preview)["applied"]
                )
                after = {
                    p: (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.storage.iterdir()
                }
                self.assertEqual(before, after)
        self.assertFalse(self.old.exists())

    def test_resolution_requires_both_documents_and_never_creates_missing_storage(
        self,
    ) -> None:
        self.old.rmdir()
        with self.assertRaisesRegex(ValueError, "existing source and target"):
            self.resolve("keep-target")
        self.assertFalse(self.storage.exists())
        self.target.change("project", "set", text="Destination only")
        with self.assertRaisesRegex(ValueError, "existing source and target"):
            self.resolve("use-text", text="Reviewed")
        self.target.path("project").unlink()
        self.source.change("project", "set", text="Source only")
        with self.assertRaisesRegex(ValueError, "existing source and target"):
            self.resolve("use-source")
        self.assertFalse(self.target.path("project").exists())
        self.assertFalse(list(self.storage.glob("resolution-backup-*")))

    def test_mode_strategy_and_text_changes_require_distinct_reviews(self) -> None:
        self.seed(vanished=False)
        copy = relocate_memory_project(self.storage, str(self.old), self.new)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.resolve(receipt=copy)
        preview = self.resolve()
        with self.assertRaisesRegex(ValueError, "changed"):
            relocate_memory_project(
                self.storage,
                str(self.old),
                self.new,
                expected_sha256=str(preview["preview_sha256"]),
            )
        with self.assertRaisesRegex(ValueError, "changed"):
            self.resolve("use-source", receipt=preview)
        text = self.resolve("use-text", text="One")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.resolve("use-text", text="Two", receipt=text)
        parent = MemoryStore(self.storage, self.old.parent)
        parent.change("project", "set", text="Ancestor")
        ancestor = resolve_memory_project(
            self.storage, self.old, self.old.parent, strategy="use-source"
        )
        with self.assertRaisesRegex(ValueError, "changed"):
            relocate_memory_project(
                self.storage,
                str(self.old),
                self.old.parent,
                strategy="use-source",
                expected_sha256=str(ancestor["preview_sha256"]),
            )

    def test_source_presence_and_record_changes_reject_stale_resolution(self) -> None:
        self.seed()
        preview = self.resolve()
        self.old.mkdir()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.resolve(receipt=preview)
        self.old.rmdir()
        for store in (self.source, self.target):
            with self.subTest(workspace=store.workspace):
                preview = self.resolve()
                path = store.path("project")
                replacement = self.storage / "replacement"
                replacement.write_bytes(path.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, path)
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.resolve(receipt=preview)
        self.assertFalse(list(self.storage.glob("resolution-backup-*")))

    def test_resolution_rejects_source_aliases_and_unsafe_snapshots(self) -> None:
        self.seed()
        self.old.symlink_to(self.new, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.resolve()
        self.old.unlink()
        source = self.source.path("project")
        source.chmod(0o644)
        with self.assertRaises(ValueError):
            self.resolve()
        source.chmod(0o600)
        alias = self.storage / "alias"
        os.link(source, alias)
        with self.assertRaises(ValueError):
            self.resolve()
        alias.unlink()
        payload = source.read_bytes()
        source.write_bytes(payload.replace(b"Source decisions", b"Tampered content"))
        with self.assertRaises(ValueError):
            self.resolve()
        self.assertFalse(list(self.storage.glob("resolution-backup-*")))

    def test_shared_lock_blocks_apply_and_memory_change_requires_refresh(self) -> None:
        self.seed()
        active = self.target.load()
        preview = self.resolve()
        with (self.storage / "memory.lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(self.resolve(), preview)
            with self.assertRaises(BlockingIOError):
                self.resolve(receipt=preview)
        self.resolve(receipt=preview)
        with self.assertRaises(MemoryChangedError):
            self.target.check(active)

    def test_reappearing_source_after_durable_backup_preserves_old_target(self) -> None:
        self.seed()
        preview = self.resolve()
        target_before = self.target.path("project").read_bytes()
        fsync = os.fsync

        def reappear(fd: int) -> None:
            fsync(fd)
            if stat.S_ISDIR(os.fstat(fd).st_mode) and not self.old.exists():
                self.old.mkdir()

        with (
            patch(
                "mos_eisley.conversation_memory_migration.os.fsync",
                side_effect=reappear,
            ),
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            self.resolve(receipt=preview)
        self.assertEqual(self.target.path("project").read_bytes(), target_before)
        self.assertEqual(Path(str(preview["backup_path"])).read_bytes(), target_before)
        self.assertFalse(list(self.storage.glob(".memory-resolution-*")))

    def test_process_death_before_and_after_replacement_preserves_backup_and_source(
        self,
    ) -> None:
        for stage in ("before", "after"):
            with self.subTest(stage=stage):
                self.seed()
                preview = self.resolve("use-source")
                source_before = self.source.path("project").read_bytes()
                target_before = self.target.path("project").read_bytes()
                code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.conversation_memory_migration import relocate_memory_project
replace = os.replace
def interrupted(*args, **kwargs):
    if sys.argv[5] == 'after':
        replace(*args, **kwargs)
    os._exit(77)
with patch('mos_eisley.conversation_memory_migration.os.replace',
           side_effect=interrupted):
    relocate_memory_project(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]),
                            strategy='use-source', expected_sha256=sys.argv[4])
"""
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        code,
                        str(self.storage),
                        str(self.old),
                        str(self.new),
                        str(preview["preview_sha256"]),
                        stage,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 77, result.stderr)
                self.assertEqual(
                    self.source.path("project").read_bytes(), source_before
                )
                self.assertEqual(
                    Path(str(preview["backup_path"])).read_bytes(), target_before
                )
                snapshot = self.target.read("project")
                assert snapshot is not None
                self.assertEqual(
                    snapshot.document.text,
                    "Source decisions" if stage == "after" else "Destination decisions",
                )
                self.assertFalse(self.old.exists())
                if stage == "after":
                    with self.assertRaisesRegex(ValueError, "changed"):
                        self.resolve("use-source", receipt=preview)

    def test_cli_resolution_is_explicit_and_recovery_flags_cannot_mix(self) -> None:
        self.seed()
        target_before = self.target.path("project").read_bytes()

        def launch(*options: str) -> subprocess.CompletedProcess[str]:
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
                    *options,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

        for flags in (
            ("--text", "Unexpected"),
            ("--strategy", "use-text"),
            ("--strategy", "use-source", "--text", "Unexpected"),
            (
                "--strategy",
                "use-source",
                "--temporary-name",
                ".memory-migration-" + "0" * 32 + ".tmp",
            ),
            ("--strategy", "keep-target", "--target-sha256", "0" * 64),
            ("--strategy", "invalid"),
            ("--strategy", "use-source", "--apply"),
        ):
            with self.subTest(flags=flags):
                result = launch(*flags)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(
                    self.target.path("project").read_bytes(), target_before
                )
        with self.assertRaisesRegex(ValueError, "not both"):
            relocate_memory_project(
                self.storage,
                str(self.old),
                self.new,
                strategy="keep-target",
                temporary_name=".memory-migration-" + "0" * 32 + ".tmp",
            )
        preview = launch("--strategy", "use-text", "--text", "Reviewed CLI content")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        receipt = json.loads(preview.stdout)
        applied = launch(
            "--strategy",
            "use-text",
            "--text",
            "Reviewed CLI content",
            "--apply",
            "--expected-sha256",
            receipt["preview_sha256"],
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(
            json.loads(applied.stdout)["result"]["document"]["text"],
            "Reviewed CLI content",
        )
