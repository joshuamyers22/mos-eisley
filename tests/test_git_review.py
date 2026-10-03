"""Real-repository scope semantics, bounded reads and helper/escape negatives."""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.git_review import (
    MAX_FILE_BYTES,
    GitReadBroker,
    GitReviewScope,
    GitReviewSelection,
    _read_file,  # pyright: ignore[reportPrivateUsage]
    freeze_git_scope,
    revalidate_git_scope,
)
from mos_eisley.git_review_cli import parse_review_selection


class RepositoryFixture:
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Synthetic Author")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.path = self.root / "pricing.py"
        self.path.write_text("if quantity >= 10:\n    discount()\n")
        self.commit("initial")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", *args],
            cwd=self.root,
            env={
                "PATH": os.defpath,
                "LC_ALL": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
            },
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        ).strip()

    def commit(self, message: str) -> str:
        self.git("add", ".")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def changed_scope(self) -> GitReviewScope:
        self.path.write_text("if quantity > 10:\n    discount()\n")
        return freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))


class GitScopeTests(RepositoryFixture, TestCase):
    def test_submodule_configuration_is_not_inspected(self) -> None:
        self.git(
            "update-index",
            "--add",
            "--cacheinfo",
            "160000",
            self.git("rev-parse", "HEAD"),
            "nested",
        )
        self.git("commit", "-m", "synthetic gitlink")
        nested = self.root / "nested"
        nested.mkdir()
        (nested / ".git").write_text("gitdir: /unavailable/synthetic-submodule\n")
        scope = self.changed_scope()
        self.assertFalse(scope.complete)
        self.assertEqual(
            next(file for file in scope.files if file.path == "nested").omission,
            "submodule",
        )
        self.assertIn("+if quantity > 10", scope.brief().diff)

    def test_git_output_and_time_limits_fail_closed(self) -> None:
        broker = GitReadBroker(self.root)
        try:
            with (
                patch("mos_eisley.git_review.MAX_GIT_BYTES", 8),
                self.assertRaisesRegex(ValueError, "output limit"),
            ):
                broker._git("rev-parse", "HEAD")  # pyright: ignore[reportPrivateUsage]
            broker.deadline = 0
            with self.assertRaisesRegex(ValueError, "time limit"):
                broker._git("rev-parse", "HEAD")  # pyright: ignore[reportPrivateUsage]
        finally:
            broker.close()

    def test_file_count_limit_does_not_produce_a_partial_scope(self) -> None:
        for index in range(65):
            (self.root / f"new-{index:02d}").write_text("synthetic\n")
        with self.assertRaisesRegex(ValueError, "file limit"):
            freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))

    def test_aggregate_scope_limit_does_not_produce_a_partial_scope(self) -> None:
        for index in range(16):
            (self.root / f"new-{index:02d}").write_text("x" * 5000 + "\n")
        with self.assertRaisesRegex(ValueError, "byte limit"):
            freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))

    def test_cli_scope_preview_and_private_output(self) -> None:
        self.changed_scope()
        output = self.root / ".git" / "scope.json"
        command = [
            sys.executable,
            "-m",
            "mos_eisley.cli",
            "review-scope",
            "--workspace",
            str(self.root),
            "--uncommitted",
            "--output",
            str(output),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = json.loads(result.stdout)
        scope = GitReviewScope.model_validate_json(output.read_bytes())
        self.assertEqual(scope.scope_id, artifact["preview"]["scope_id"])
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertFalse(artifact["preview"]["live_review_available"])
        repeated = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertNotEqual(repeated.returncode, 0)

    def test_parent_directory_link_is_never_followed(self) -> None:
        with TemporaryDirectory() as outside:
            Path(outside, "secret").write_text("OUTSIDE")
            (self.root / "linked").symlink_to(outside, target_is_directory=True)
            descriptor = os.open(self.root, os.O_RDONLY)
            try:
                with self.assertRaises(OSError):
                    _read_file(descriptor, "linked/secret", MAX_FILE_BYTES)
            finally:
                os.close(descriptor)

    def test_mode_changes_are_frozen_even_with_content_changes(self) -> None:
        self.path.chmod(0o755)
        scope = freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))
        self.assertEqual(scope.files[0].after_mode, "100755")
        self.assertIn("mode changed", scope.brief().diff)
        self.path.write_text("changed text\n")
        self.git("add", "pricing.py")
        scope = freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))
        self.path.chmod(0o644)
        self.git("add", "pricing.py")
        with self.assertRaisesRegex(ValueError, "scope changed"):
            revalidate_git_scope(scope)

    def test_staged_unstaged_untracked_and_read_only_metadata(self) -> None:
        self.path.write_text("if quantity > 10:\n    discount()\n")
        self.git("add", "pricing.py")
        self.path.write_text("if quantity > 11:\n    discount()\n")
        (self.root / "new.py").write_text("new_file = True")
        before = {
            p.relative_to(self.root): p.read_bytes()
            for p in (self.root / ".git").rglob("*")
            if p.is_file()
        }
        scope = freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))
        self.assertTrue(scope.complete)
        tracked = next(file for file in scope.files if file.path == "pricing.py")
        self.assertTrue(tracked.staged)
        self.assertTrue(tracked.unstaged)
        self.assertIn("[staged]", tracked.patch)
        self.assertIn("+if quantity > 11:", tracked.patch)
        self.assertTrue(
            next(file for file in scope.files if file.path == "new.py").untracked
        )
        self.assertIn("No newline at end of file", scope.brief().diff)
        after = {
            p.relative_to(self.root): p.read_bytes()
            for p in (self.root / ".git").rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)

    def test_staged_edit_not_lost_when_worktree_returns_to_head(self) -> None:
        original = self.path.read_bytes()
        self.path.write_text("changed\n")
        self.git("add", "pricing.py")
        self.path.write_bytes(original)
        scope = freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))
        self.assertEqual(len(scope.files), 1)
        self.assertIn("+changed", scope.brief().diff)
        self.assertIn("[unstaged]", scope.brief().diff)

    def test_branch_comparison_uses_merge_base_and_ignores_dirty_checkout(self) -> None:
        initial = self.git("rev-parse", "HEAD")
        self.git("checkout", "-b", "feature")
        self.path.write_text("feature\n")
        feature = self.commit("feature")
        self.git("checkout", "main")
        (self.root / "main.txt").write_text("main-only\n")
        self.commit("main changed")
        self.git("checkout", "feature")
        self.path.write_text("dirty not in branch\n")
        scope = freeze_git_scope(
            self.root, GitReviewSelection(kind="base", reference="main")
        )
        self.assertEqual(scope.base, initial)
        self.assertEqual(scope.target, feature)
        self.assertEqual([file.path for file in scope.files], ["pricing.py"])
        self.assertNotIn("dirty not in branch", scope.brief().diff)

    def test_root_and_selected_commit(self) -> None:
        initial = self.git("rev-parse", "HEAD")
        scope = freeze_git_scope(
            self.root, GitReviewSelection(kind="commit", reference=initial)
        )
        self.assertIsNone(scope.base)
        self.assertIn("/dev/null", scope.brief().diff)
        self.path.write_text("later\n")
        later = self.commit("later")
        scope = freeze_git_scope(
            self.root, GitReviewSelection(kind="commit", reference=later)
        )
        self.assertEqual(scope.base, initial)
        self.assertEqual(scope.target, later)

    def test_merge_commit_requires_parent_and_bounds_it(self) -> None:
        self.git("checkout", "-b", "feature")
        (self.root / "feature.txt").write_text("feature\n")
        self.commit("feature")
        self.git("checkout", "main")
        (self.root / "main.txt").write_text("main\n")
        self.commit("main")
        self.git("merge", "--no-ff", "feature", "-m", "merge")
        with self.assertRaisesRegex(ValueError, "explicit parent"):
            freeze_git_scope(
                self.root, GitReviewSelection(kind="commit", reference="HEAD")
            )
        scope = freeze_git_scope(
            self.root, GitReviewSelection(kind="commit", reference="HEAD", parent=2)
        )
        self.assertEqual([file.path for file in scope.files], ["main.txt"])
        with self.assertRaisesRegex(ValueError, "does not exist"):
            freeze_git_scope(
                self.root, GitReviewSelection(kind="commit", reference="HEAD", parent=3)
            )

    def test_unborn_head_untracked_and_empty_scope(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            subprocess.run(
                ["/usr/bin/git", "init", str(root)], check=True, capture_output=True
            )
            (root / "new.txt").write_text("new\n")
            scope = freeze_git_scope(root, GitReviewSelection(kind="uncommitted"))
            self.assertIsNone(scope.head)
            self.assertTrue(scope.files[0].untracked)
        scope = freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))
        self.assertEqual(scope.files, ())
        with self.assertRaisesRegex(ValueError, "no reviewable"):
            scope.brief()

    def test_renames_deletions_and_empty_untracked(self) -> None:
        self.path.rename(self.root / "renamed.py")
        (self.root / "empty").touch()
        scope = freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))
        self.assertEqual(
            [file.path for file in scope.files], ["empty", "pricing.py", "renamed.py"]
        )
        self.assertIn("File presence changed", scope.files[0].patch)

    def test_source_index_head_and_configuration_changes_invalidate(self) -> None:
        for change in ("source", "index", "head", "configuration"):
            with self.subTest(change=change):
                scope = self.changed_scope()
                if change == "source":
                    self.path.write_text("newer\n")
                elif change == "index":
                    self.git("add", "pricing.py")
                elif change == "head":
                    self.commit("moved")
                else:
                    self.git("config", "review.synthetic", "changed")
                with self.assertRaisesRegex(ValueError, "scope changed"):
                    revalidate_git_scope(scope)
                self.git("reset", "--hard", "HEAD")

    def test_change_between_capture_passes_fails(self) -> None:
        original = GitReadBroker.capture
        calls = 0

        def capture(
            broker: GitReadBroker, selection: GitReviewSelection
        ) -> GitReviewScope:
            nonlocal calls
            calls += 1
            result = original(broker, selection)
            if calls == 1:
                self.path.write_text("concurrent edit\n")
            return result

        with (
            patch.object(GitReadBroker, "capture", capture),
            self.assertRaisesRegex(ValueError, "changed during"),
        ):
            freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))

    def test_helpers_and_inherited_git_overrides_are_not_used(self) -> None:
        marker = self.root / "helper-ran"
        helper = self.root / ".git" / "evil-helper"
        helper.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
        helper.chmod(0o700)
        (self.root / ".gitattributes").write_text("*.py diff=evil\n")
        self.commit("attributes")
        for key in (
            "core.fsmonitor",
            "diff.external",
            "diff.evil.textconv",
            "core.pager",
        ):
            self.git("config", key, str(helper))
        self.path.write_text("changed\n")
        with patch.dict(
            os.environ,
            {
                "GIT_EXTERNAL_DIFF": str(helper),
                "GIT_DIR": str(self.root / "missing"),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.fsmonitor",
                "GIT_CONFIG_VALUE_0": str(helper),
            },
        ):
            scope = freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))
        self.assertIn("+changed", scope.brief().diff)
        self.assertFalse(marker.exists())

    def test_symlink_hardlink_fifo_and_parent_escape_fail(self) -> None:
        with TemporaryDirectory() as outside:
            secret = Path(outside) / "secret"
            secret.write_text("OUTSIDE-CONTENT")
            for kind in ("symlink", "hardlink", "fifo", "parent"):
                with self.subTest(kind=kind):
                    new = self.root / "untracked"
                    if kind == "symlink":
                        new.symlink_to(secret)
                    elif kind == "hardlink":
                        os.link(secret, new)
                    elif kind == "fifo":
                        os.mkfifo(new)
                    else:
                        self.path.unlink()
                        self.path.symlink_to(secret)
                    try:
                        with self.assertRaises((ValueError, OSError)):
                            if kind == "fifo":
                                descriptor = os.open(self.root, os.O_RDONLY)
                                try:
                                    _read_file(descriptor, "untracked", MAX_FILE_BYTES)
                                finally:
                                    os.close(descriptor)
                            else:
                                freeze_git_scope(
                                    self.root, GitReviewSelection(kind="uncommitted")
                                )
                    finally:
                        if new.exists() or new.is_symlink():
                            new.unlink()
                        if self.path.is_symlink():
                            self.path.unlink()
                            self.git("checkout", "--", "pricing.py")

    def test_metadata_symlinks_config_includes_and_alternates_fail(self) -> None:
        link = self.root / ".git" / "unsafe"
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, "metadata links"):
            self.changed_scope()
        link.unlink()
        include = self.root / ".git" / "extra-config"
        include.write_text("# synthetic external config\n")
        self.git("config", "include.path", str(include))
        with (
            patch("mos_eisley.git_review.subprocess.Popen") as process,
            self.assertRaisesRegex(ValueError, "indirection"),
        ):
            self.changed_scope()
        process.assert_not_called()
        self.git("config", "--no-includes", "--unset", "include.path")
        worktree_config = self.root / ".git" / "config.worktree"
        worktree_config.write_text("[include]\npath = /outside\n")
        with (
            patch("mos_eisley.git_review.subprocess.Popen") as process,
            self.assertRaisesRegex(ValueError, "indirection"),
        ):
            self.changed_scope()
        process.assert_not_called()
        worktree_config.unlink()
        alternates = self.root / ".git" / "objects" / "info" / "alternates"
        alternates.write_text("/outside\n")
        with self.assertRaisesRegex(ValueError, "object stores"):
            self.changed_scope()

    def test_omissions_are_disclosed_and_no_ambient_private_content_is_read(
        self,
    ) -> None:
        (self.root / "binary").write_bytes(b"\x00secret")
        (self.root / "large").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
        private = self.root / ".mos-eisley-sessions"
        private.mkdir()
        (private / "session.json").write_text("PRIVATE-TRANSCRIPT")
        memory = self.root / ".mos-eisley-memory"
        memory.mkdir()
        (memory / "synthetic.json").write_text("PRIVATE-MEMORY")
        scope = self.changed_scope()
        self.assertFalse(scope.complete)
        self.assertEqual(
            {file.omission for file in scope.files},
            {None, "binary", "oversized", "protected"},
        )
        self.assertNotIn("PRIVATE-TRANSCRIPT", scope.model_dump_json())
        self.assertNotIn("PRIVATE-MEMORY", scope.model_dump_json())

    def test_ambiguous_missing_and_option_like_targets_fail(self) -> None:
        for text in (
            "/review --base main --commit HEAD",
            "/review --base -bad",
            "/review --uncommitted --parent 1",
            "/review --commit HEAD:pricing.py",
            "/review --commit HEAD~1",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_review_selection(text)
        with self.assertRaises(ValueError):
            freeze_git_scope(
                self.root, GitReviewSelection(kind="base", reference="missing")
            )
