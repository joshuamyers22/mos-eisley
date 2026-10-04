"""Real Git checkout tests for the conversation diff read boundary."""

import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation_directory import DirectorySelection
from mos_eisley.conversation_git import (
    ChangeKind,
    DiffBasis,
    GitReadError,
    GitState,
    GitWorkspaceReader,
)
from mos_eisley.conversation_git_isolation import isolated_command


class GitWorkspaceTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        found = shutil.which("git")
        assert found is not None
        self.git = Path(found).resolve()
        self.run_git("init", "-q")
        self.run_git("config", "user.name", "Test")
        self.run_git("config", "user.email", "test@example.invalid")

    def run_git(self, *arguments: str) -> bytes:
        result = subprocess.run(
            [str(self.git), *arguments],
            cwd=self.root,
            env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"},
            capture_output=True,
            check=True,
            timeout=10,
        )
        return result.stdout

    def reader(self, path: Path | None = None) -> GitWorkspaceReader:
        return GitWorkspaceReader(
            DirectorySelection.inspect(path or self.root), self.git
        )

    def commit(self, path: str, text: str = "before\n") -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        self.run_git("add", "--", path)
        self.run_git("commit", "-qm", "base")

    def test_non_git_and_unborn_head_are_explicit(self) -> None:
        self.assertEqual(self.reader().snapshot().state, GitState.UNBORN)
        outside = self.base / "outside"
        outside.mkdir()
        self.assertEqual(self.reader(outside).snapshot().state, GitState.NON_GIT)
        (self.root / "new.txt").write_text("new\n")
        self.run_git("add", "new.txt")
        snapshot = self.reader().snapshot()
        self.assertEqual(snapshot.state, GitState.UNBORN)
        self.assertEqual(snapshot.changes[0].staged_added, 1)

    def test_staged_unstaged_untracked_and_frozen_patch(self) -> None:
        self.commit("tracked.txt")
        target = self.root / "tracked.txt"
        target.write_text("staged\n")
        self.run_git("add", "tracked.txt")
        target.write_text("working\n")
        (self.root / "new.txt").write_text("untracked\n")
        reader = self.reader()
        snapshot = reader.snapshot()
        self.assertEqual(snapshot.state, GitState.READY)
        self.assertTrue(snapshot.complete)
        changes = {entry.path: entry for entry in snapshot.changes}
        self.assertEqual(changes["tracked.txt"].staged, "M")
        self.assertEqual(changes["tracked.txt"].unstaged, "M")
        self.assertEqual(changes["tracked.txt"].staged_added, 1)
        self.assertEqual(changes["tracked.txt"].unstaged_removed, 1)
        self.assertEqual(changes["new.txt"].kind, ChangeKind.UNTRACKED)
        self.assertIn(
            b"+staged", reader.patch(snapshot, "tracked.txt", DiffBasis.STAGED).data
        )
        self.assertIn(
            b"+working", reader.patch(snapshot, "tracked.txt", DiffBasis.UNSTAGED).data
        )
        with self.assertRaisesRegex(GitReadError, "comparison"):
            reader.patch(snapshot, "tracked.txt", "invalid")  # type: ignore[arg-type]
        target.write_text("changed again\n")
        with self.assertRaisesRegex(GitReadError, "snapshot changed"):
            reader.patch(snapshot, "tracked.txt", DiffBasis.UNSTAGED)

    def test_subdirectory_scope_excludes_other_paths_and_crossing_rename(self) -> None:
        self.commit("inside/old.txt")
        self.run_git("mv", "inside/old.txt", "outside.txt")
        (self.root / "inside" / "new.txt").write_text("inside\n")
        reader = self.reader(self.root / "inside")
        snapshot = reader.snapshot()
        self.assertTrue(snapshot.complete)
        self.assertEqual(
            {entry.path for entry in snapshot.changes}, {"old.txt", "new.txt"}
        )
        self.assertTrue(all("outside" not in entry.path for entry in snapshot.changes))

    def test_rename_delete_and_binary_counts(self) -> None:
        self.commit("old.txt", "same\n")
        self.run_git("mv", "old.txt", "new.txt")
        reader = self.reader()
        entry = reader.snapshot().changes[0]
        self.assertEqual(
            (entry.path, entry.old_path, entry.staged), ("new.txt", "old.txt", "R")
        )
        patch_data = reader.patch(reader.snapshot(), "new.txt", DiffBasis.STAGED).data
        self.assertIn(b"rename from old.txt", patch_data)
        self.assertIn(b"rename to new.txt", patch_data)
        self.run_git("commit", "-qm", "rename")
        self.run_git("rm", "new.txt")
        self.assertEqual(self.reader().snapshot().changes[0].staged, "D")
        self.run_git("commit", "-qm", "delete")
        (self.root / "blob.bin").write_bytes(b"\0\xff\0")
        self.run_git("add", "blob.bin")
        binary = self.reader().snapshot().changes[0]
        self.assertIsNone(binary.staged_added)
        self.assertIsNone(binary.staged_removed)

    def test_nested_directory_deletion_is_a_valid_change(self) -> None:
        self.commit("nested/deep/file.txt")
        self.run_git("rm", "nested/deep/file.txt")
        snapshot = self.reader().snapshot()
        self.assertTrue(snapshot.complete)
        self.assertEqual(snapshot.changes[0].path, "nested/deep/file.txt")
        self.assertEqual(snapshot.changes[0].staged, "D")

    def test_hostile_git_helpers_do_not_execute(self) -> None:
        self.commit("tracked.txt")
        marker = self.base / "executed"
        helper = self.base / "helper.sh"
        helper.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
        helper.chmod(0o700)
        self.run_git("config", "core.fsmonitor", str(helper))
        self.run_git("config", "diff.external", str(helper))
        self.run_git("config", "diff.bad.command", str(helper))
        self.run_git("config", "diff.bad.textconv", str(helper))
        self.run_git("config", "filter.evil.clean", str(helper))
        self.run_git("config", "filter.evil.process", str(helper))
        (self.root / ".gitattributes").write_text("*.txt diff=bad filter=evil\n")
        (self.root / "tracked.txt").write_text("after\n")
        reader = self.reader()
        snapshot = reader.snapshot()
        self.assertIn(
            b"+after", reader.patch(snapshot, "tracked.txt", DiffBasis.UNSTAGED).data
        )
        self.assertFalse(marker.exists())

    def test_concurrent_config_rewrite_cannot_execute_new_helper(self) -> None:
        self.commit("tracked.txt")
        (self.root / "tracked.txt").write_text("changed\n")
        marker = self.base / "helper-executed"
        helper = self.base / "helper.sh"
        helper.write_text(f"#!/bin/sh\nprintf ran > '{marker}'\ncat\n")
        helper.chmod(0o700)
        reader = self.reader()
        baseline = reader.snapshot()
        scanned = Event()
        rewritten = Event()
        raced_command: list[str] = []

        def before_launch(executable: Path, arguments: list[str]) -> list[str]:
            if (
                "diff" in arguments
                and "--no-color" in arguments
                and not scanned.is_set()
            ):
                raced_command.extend(arguments)
                scanned.set()
                if not rewritten.wait(5):
                    raise AssertionError("Git configuration rewrite did not finish")
            return isolated_command(executable, arguments)

        def rewrite() -> None:
            if not scanned.wait(5):
                return
            self.run_git("config", "filter.raced.clean", str(helper))
            (self.root / ".gitattributes").write_text("*.txt filter=raced\n")
            rewritten.set()

        worker = Thread(target=rewrite)
        worker.start()
        try:
            with (
                patch(
                    "mos_eisley.conversation_git.isolated_command",
                    side_effect=before_launch,
                ),
                self.assertRaises(GitReadError),
            ):
                reader.patch(baseline, "tracked.txt", DiffBasis.UNSTAGED)
        finally:
            worker.join(timeout=5)
        self.assertTrue(rewritten.is_set())
        self.assertFalse(marker.exists())
        # Run the exact raced argv without the OS boundary. The helper must
        # execute, proving the confined read encountered a real exploit path.
        self.run_git(*raced_command)
        self.assertTrue(marker.exists())

    def test_snapshot_and_patch_leave_index_untouched(self) -> None:
        self.commit("tracked.txt")
        (self.root / "tracked.txt").write_text("after\n")
        index = self.root / ".git" / "index"
        before = index.stat()
        reader = self.reader()
        snapshot = reader.snapshot()
        reader.patch(snapshot, "tracked.txt", DiffBasis.UNSTAGED)
        after = index.stat()
        self.assertEqual(
            (before.st_ino, before.st_mtime_ns),
            (after.st_ino, after.st_mtime_ns),
        )
        self.assertFalse((self.root / ".git" / "index.lock").exists())

    def test_unsafe_filenames_are_omitted_with_incomplete_notice(self) -> None:
        self.commit("tracked.txt")
        (self.root / "bad\nname.txt").write_text("untrusted")
        reader = self.reader()
        snapshot = reader.snapshot()
        self.assertFalse(snapshot.complete)
        self.assertIn("omitted", snapshot.omission or "")
        self.assertEqual(snapshot.changes, ())

    def test_staged_content_change_invalidates_same_count_snapshot(self) -> None:
        self.commit("tracked.txt")
        (self.root / "tracked.txt").write_text("one\n")
        self.run_git("add", "tracked.txt")
        reader = self.reader()
        snapshot = reader.snapshot()
        (self.root / "tracked.txt").write_text("two\n")
        self.run_git("add", "tracked.txt")
        with self.assertRaisesRegex(GitReadError, "snapshot changed"):
            reader.patch(snapshot, "tracked.txt", DiffBasis.STAGED)

    def test_config_change_invalidates_patch_snapshot(self) -> None:
        self.commit("tracked.txt")
        (self.root / "tracked.txt").write_text("after\n")
        reader = self.reader()
        snapshot = reader.snapshot()
        self.run_git("config", "diff.algorithm", "minimal")
        with self.assertRaisesRegex(GitReadError, "snapshot changed"):
            reader.patch(snapshot, "tracked.txt", DiffBasis.UNSTAGED)

    def test_linked_worktree_binds_external_git_directory(self) -> None:
        self.commit("tracked.txt")
        worktree = self.base / "linked-worktree"
        self.run_git("worktree", "add", "-qb", "linked", str(worktree))
        (worktree / "tracked.txt").write_text("changed\n")
        reader = self.reader(worktree)
        self.assertEqual(reader.snapshot().changes[0].path, "tracked.txt")
        git_dir = reader.git_dir
        self.assertIsNotNone(git_dir)
        assert git_dir is not None
        self.assertNotEqual(git_dir.path, worktree)

    def test_untracked_symlink_is_listed_only_and_replacement_fails(self) -> None:
        self.commit("tracked.txt")
        outside = self.base / "outside-secret"
        outside.write_text("secret")
        (self.root / "linked.txt").symlink_to(outside)
        reader = self.reader()
        snapshot = reader.snapshot()
        self.assertEqual(snapshot.changes[0].path, "linked.txt")
        self.assertEqual(snapshot.changes[0].kind, ChangeKind.UNTRACKED)
        old = self.base / "old-repo"
        self.root.rename(old)
        self.root.mkdir()
        with self.assertRaisesRegex(GitReadError, "changed"):
            reader.snapshot()

    def test_limits_refuse_oversized_inventory_and_patch(self) -> None:
        self.commit("tracked.txt")
        (self.root / "tracked.txt").write_text("many\n" * 200)
        reader = self.reader()
        with (
            patch("mos_eisley.conversation_git.MAX_INVENTORY_BYTES", 10),
            self.assertRaisesRegex(GitReadError, "resource limit"),
        ):
            reader.snapshot()
        snapshot = reader.snapshot()
        with (
            patch("mos_eisley.conversation_git.MAX_PATCH_BYTES", 10),
            self.assertRaisesRegex(GitReadError, "resource limit"),
        ):
            reader.patch(snapshot, "tracked.txt", DiffBasis.UNSTAGED)
