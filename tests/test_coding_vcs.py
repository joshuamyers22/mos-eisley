"""Creator-owned tests for exact isolated VCS staging and integration."""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase

from mos_eisley.coding_child import (
    CodeFile,
    CodeSnapshot,
    CodingBrief,
    CodingPatch,
    FileChange,
)
from mos_eisley.conversation_agents import ImplementationAssignment
from mos_eisley.core.models import digest
from mos_eisley.run.coding_vcs import CodingVCS
from mos_eisley.task_state import ResourceCeiling


def make_brief(
    workspace: Path, worktree: Path, commit: str, snapshot: CodeSnapshot
) -> CodingBrief:
    plan = "Implement addition without changing creator tests."
    tests = CodeSnapshot(
        files=tuple(f for f in snapshot.files if f.path.startswith("tests/"))
    )
    return CodingBrief(
        assignment=ImplementationAssignment(
            task_id="addition",
            parent_task_id="parent",
            objective=plan,
            provider="fixture",
            model="tool-reviewer-v1",
            effort="high",
            workspace=str(workspace),
            worktree=str(worktree),
            plan_sha256=digest(plan.encode()),
            tests_sha256=tests.sha256,
            allowance=ResourceCeiling(
                input_bytes=32000,
                output_bytes=16384,
                attempts=1,
                cost_microusd=0,
                review_rounds=0,
                correction_cycles=0,
            ),
        ),
        base_commit=commit,
        snapshot=snapshot,
        plan=plan,
        interfaces="add(a, b)",
        acceptance="Both positive and negative inputs pass.",
        owned_paths=("adder.py",),
        test_paths=("tests/test_adder.py",),
    )


def good_patch(brief: CodingBrief) -> CodingPatch:
    old = next(f for f in brief.snapshot.files if f.path == "adder.py")
    return CodingPatch(
        brief_sha256=brief.sha256,
        summary="Implement addition.",
        changes=(
            FileChange(
                file=CodeFile(
                    path="adder.py", content="def add(a, b):\n    return a + b\n"
                ),
                before_sha256=old.sha256,
            ),
        ),
    )


class CodingVCSTests(TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "adder.py").write_text("def add(a, b):\n    return 0\n")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/test_adder.py").write_text(
            "import unittest\nfrom adder import add\n"
            "class Tests(unittest.TestCase):\n    def test_add(self):\n"
            "        self.assertEqual(add(2, 3), 5)\n"
            "        self.assertEqual(add(-4, 1), -3)\n"
        )
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Creator tests before delegation",
        )
        self.broker = CodingVCS(Path("/usr/bin/git"), self.repo, self.root / "staging")
        commit, snapshot = self.broker.snapshot(("adder.py", "tests/test_adder.py"))
        self.brief = make_brief(
            self.repo, self.root / "staging/child", commit, snapshot
        )

    def tearDown(self) -> None:
        self.broker.close()
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        return (
            subprocess.check_output(["git", "-C", str(self.repo), *args])
            .decode()
            .strip()
        )

    def test_stage_isolated_worktree_then_exact_integration(self) -> None:
        patch = good_patch(self.brief)
        diff = self.broker.stage(self.brief, patch)
        self.assertIn("+    return a + b", diff)
        self.assertIn("return 0", (self.repo / "adder.py").read_text())
        self.assertEqual(self.git("rev-parse", "HEAD"), self.brief.base_commit)
        commit = self.broker.integrate(self.brief, patch, digest(diff.encode()))
        self.assertEqual(self.git("rev-parse", "HEAD"), commit)
        self.assertIn("return a + b", (self.repo / "adder.py").read_text())
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(
            (self.repo / "tests/test_adder.py").read_text(),
            self.brief.snapshot.files[1].content,
        )
        with self.assertRaises(ValueError):
            self.broker.integrate(self.brief, patch, digest(diff.encode()))

    def test_protected_stale_duplicate_noop_and_traversal_patches_rejected(
        self,
    ) -> None:
        for path in (
            "tests/test_adder.py",
            "../escape.py",
            "/tmp/escape.py",
            ".git/hooks.py",
            "a/../escape.py",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                patch = CodingPatch(
                    brief_sha256=self.brief.sha256,
                    summary="Bad",
                    changes=(
                        FileChange(
                            file=CodeFile(path=path, content="bad"), before_sha256=None
                        ),
                    ),
                )
                self.broker.stage(self.brief, patch)
        patch = good_patch(self.brief)
        for changed in (
            patch.model_copy(update={"changes": patch.changes * 2}),
            patch.model_copy(update={"brief_sha256": "0" * 64}),
            patch.model_copy(
                update={
                    "changes": (
                        patch.changes[0].model_copy(update={"before_sha256": "0" * 64}),
                    )
                }
            ),
        ):
            with self.assertRaises(ValueError):
                self.broker.stage(self.brief, changed)
        old = self.brief.snapshot.files[0]
        noop = patch.model_copy(
            update={"changes": (FileChange(file=old, before_sha256=old.sha256),)}
        )
        with self.assertRaises(ValueError):
            self.broker.stage(self.brief, noop)

    def test_dirty_parent_or_changed_stage_blocks_integration(self) -> None:
        patch = good_patch(self.brief)
        diff = self.broker.stage(self.brief, patch)
        (self.repo / "untracked").write_text("changed")
        with self.assertRaises(ValueError):
            self.broker.integrate(self.brief, patch, digest(diff.encode()))
        (self.repo / "untracked").unlink()
        stage = Path(self.brief.assignment.worktree or "")
        (stage / "tests/test_adder.py").write_text("weakened")
        with self.assertRaises(ValueError):
            self.broker.integrate(self.brief, patch, digest(diff.encode()))
        self.assertIn("return 0", (self.repo / "adder.py").read_text())

    def test_symlinks_and_unowned_worktrees_are_rejected(self) -> None:
        (self.repo / "adder.py").unlink()
        (self.repo / "adder.py").symlink_to(self.repo / "tests/test_adder.py")
        with self.assertRaises(ValueError):
            self.broker.snapshot(("adder.py", "tests/test_adder.py"))
        brief = self.brief.model_copy(
            update={
                "assignment": self.brief.assignment.model_copy(
                    update={"worktree": str(self.root / "outside")}
                )
            }
        )
        with self.assertRaises(ValueError):
            self.broker.stage(brief, good_patch(brief))

    def test_hooks_filters_and_external_diff_are_never_executed(self) -> None:
        marker = self.root / "executed"
        hook = self.repo / ".git/hooks/post-checkout"
        hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
        hook.chmod(0o700)
        self.git("config", "diff.external", f"touch {marker}")
        self.git("config", "core.fsmonitor", f"touch {marker}")
        patch = good_patch(self.brief)
        diff = self.broker.stage(self.brief, patch)
        self.broker.integrate(self.brief, patch, digest(diff.encode()))
        self.assertFalse(marker.exists())

    def test_attributes_and_filters_rejected_before_checkout(self) -> None:
        marker = self.root / "filter-executed"
        self.git("config", "filter.hostile.smudge", f"touch {marker}")
        with self.assertRaises(ValueError):
            self.broker.stage(self.brief, good_patch(self.brief))
        self.assertFalse(marker.exists())
        self.assertFalse(Path(self.brief.assignment.worktree or "").exists())
        self.git("config", "--remove-section", "filter.hostile")
        (self.repo / ".gitattributes").write_text("*.py filter=hostile\n")
        self.git("add", ".gitattributes")
        self.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Untrusted attributes",
        )
        with self.assertRaises(ValueError):
            self.broker.snapshot(("adder.py", "tests/test_adder.py"))
        self.assertFalse(marker.exists())

    def test_info_attributes_includes_and_hidden_index_rejected(self) -> None:
        attributes = self.repo / ".git/info/attributes"
        attributes.write_text("*.py filter=hostile\n")
        with self.assertRaises(ValueError):
            self.broker.stage(self.brief, good_patch(self.brief))
        attributes.unlink()
        self.git("config", "include.path", str(self.root / "external-config"))
        with self.assertRaises(ValueError):
            self.broker.snapshot(("adder.py", "tests/test_adder.py"))
        self.git("config", "--unset", "include.path")
        self.git("update-index", "--assume-unchanged", "adder.py")
        (self.repo / "adder.py").write_text("hidden modification\n")
        with self.assertRaises(ValueError):
            self.broker.snapshot(("adder.py", "tests/test_adder.py"))

    def test_exact_diff_receipt_and_duplicate_stage_required(self) -> None:
        patch = good_patch(self.brief)
        diff = self.broker.stage(self.brief, patch)
        with self.assertRaises(ValueError):
            self.broker.stage(self.brief, patch)
        with self.assertRaises(ValueError):
            self.broker.integrate(self.brief, patch, "0" * 64)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.brief.base_commit)
        self.broker.integrate(self.brief, patch, digest(diff.encode()))

    def test_close_removes_only_exact_registered_worktrees(self) -> None:
        patch = good_patch(self.brief)
        self.broker.stage(self.brief, patch)
        stage = Path(self.brief.assignment.worktree or "")
        unrelated = self.root / "staging/unregistered"
        unrelated.mkdir()
        sentinel = unrelated / "preserve.txt"
        sentinel.write_text("Do not delete unregistered work.")
        self.broker.close()
        self.assertFalse(stage.exists())
        self.assertTrue(sentinel.exists())
        self.assertEqual(self.git("rev-parse", "HEAD"), self.brief.base_commit)
        with self.assertRaises(ValueError):
            self.broker.stage(self.brief, patch)

    def test_close_preserves_changed_or_uncertain_work(self) -> None:
        self.broker.stage(self.brief, good_patch(self.brief))
        stage = Path(self.brief.assignment.worktree or "")
        (stage / "adder.py").write_text("Unexpected work must be retained.\n")
        self.broker.close()
        self.assertTrue(stage.exists())
        self.assertEqual(
            (stage / "adder.py").read_text(), "Unexpected work must be retained.\n"
        )
        self.assertEqual(self.git("rev-parse", "HEAD"), self.brief.base_commit)

    def test_parent_or_stage_ambient_ignored_files_block_integration(self) -> None:
        patch = good_patch(self.brief)
        diff = self.broker.stage(self.brief, patch)
        stage = Path(self.brief.assignment.worktree or "")
        (stage / "unknown.py").write_text('print("unassigned")\n')
        with self.assertRaises(ValueError):
            self.broker.integrate(self.brief, patch, digest(diff.encode()))
        (stage / "unknown.py").unlink()
        exclude = self.repo / ".git/info/exclude"
        exclude.write_text("ambient.py\n")
        (self.repo / "ambient.py").write_text("hidden ambient work\n")
        with self.assertRaises(ValueError):
            self.broker.integrate(self.brief, patch, digest(diff.encode()))

    def test_symlinked_staging_root_and_private_root_permissions(self) -> None:
        alias = self.root / "alias"
        alias.symlink_to(self.root / "staging", target_is_directory=True)
        with self.assertRaises(ValueError):
            CodingVCS(Path("/usr/bin/git"), self.repo, alias)
        public = self.root / "public"
        public.mkdir(mode=0o755)
        with self.assertRaises(ValueError):
            CodingVCS(Path("/usr/bin/git"), self.repo, public)

    def test_failed_ff_acknowledgement_is_retained_and_never_replayed(self) -> None:
        class RejectingMerge(CodingVCS):
            def _git(self, cwd: Path, *args: str) -> str:
                if args[0] == "merge":
                    raise ValueError("Simulated lost integration acknowledgement.")
                return super()._git(cwd, *args)

        self.broker.close()
        self.broker = RejectingMerge(
            Path("/usr/bin/git"), self.repo, self.root / "staging"
        )
        patch = good_patch(self.brief)
        diff = self.broker.stage(self.brief, patch)
        with self.assertRaises(ValueError):
            self.broker.integrate(self.brief, patch, digest(diff.encode()))
        stage = Path(self.brief.assignment.worktree or "")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.brief.base_commit)
        with self.assertRaises(ValueError):
            self.broker.integrate(self.brief, patch, digest(diff.encode()))
        self.broker.close()
        self.assertTrue(stage.exists())
        self.assertIn("return a + b", (stage / "adder.py").read_text())

    def test_checkout_byte_ceiling_rejects_large_unassigned_blobs(self) -> None:
        (self.repo / "large.txt").write_bytes(b"x" * 2_000_001)
        self.git("add", "large.txt")
        self.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Exceed isolated checkout ceiling",
        )
        with self.assertRaises(ValueError):
            self.broker.snapshot(("adder.py", "tests/test_adder.py"))

    def test_final_verification_reads_actual_integrated_repository(self) -> None:
        patch = good_patch(self.brief)
        diff = self.broker.stage(self.brief, patch)
        with self.assertRaises(ValueError):
            self.broker.integrated_snapshot(self.brief, patch, self.brief.base_commit)
        commit = self.broker.integrate(self.brief, patch, digest(diff.encode()))
        self.assertEqual(
            self.broker.integrated_snapshot(self.brief, patch, commit),
            patch.apply(self.brief),
        )
        with self.assertRaises(ValueError):
            self.broker.integrated_snapshot(self.brief, patch, self.brief.base_commit)
        (self.repo / "tests/test_adder.py").write_text("weakened after integration")
        with self.assertRaises(ValueError):
            self.broker.integrated_snapshot(self.brief, patch, commit)

    def test_omitted_existing_source_cannot_be_replaced_as_new(self) -> None:
        tests = CodeSnapshot(files=(self.brief.snapshot.files[1],))
        brief = make_brief(
            self.repo, self.root / "staging/child", self.brief.base_commit, tests
        )
        patch = CodingPatch(
            brief_sha256=brief.sha256,
            summary="Pretend existing source is new.",
            changes=(
                FileChange(
                    file=CodeFile(path="adder.py", content="replacement\n"),
                    before_sha256=None,
                ),
            ),
        )
        with self.assertRaises(ValueError):
            self.broker.stage(brief, patch)
        self.assertFalse(Path(brief.assignment.worktree or "").exists())
        self.assertIn("return 0", (self.repo / "adder.py").read_text())

    def test_new_owned_source_is_integrated_and_read_from_actual_tree(self) -> None:
        brief = self.brief.model_copy(
            update={
                "owned_paths": ("adder.py", "utility.py"),
            }
        )
        patch = CodingPatch(
            brief_sha256=brief.sha256,
            summary="Add explicitly owned utility.",
            changes=(
                FileChange(
                    file=CodeFile(
                        path="utility.py", content="def value():\n    return 1\n"
                    ),
                    before_sha256=None,
                ),
            ),
        )
        diff = self.broker.stage(brief, patch)
        self.assertFalse((self.repo / "utility.py").exists())
        commit = self.broker.integrate(brief, patch, digest(diff.encode()))
        self.assertEqual(
            self.broker.integrated_snapshot(brief, patch, commit),
            patch.apply(brief),
        )
        self.assertEqual(
            (self.repo / "utility.py").read_text(), "def value():\n    return 1\n"
        )

    def test_nested_directory_cannot_impersonate_repository_root(self) -> None:
        with self.assertRaises(ValueError):
            CodingVCS(
                Path("/usr/bin/git"), self.repo / "tests", self.root / "nested-staging"
            )

    def test_owned_operation_rejects_prestart_cancellation(self) -> None:
        cancelled = Event()
        cancelled.set()
        calls: list[str] = []
        with self.assertRaises(InterruptedError):
            self.broker.run_operation(lambda: calls.append("called"), 5, cancelled)
        self.assertEqual(calls, [])
        self.assertEqual(self.git("rev-parse", "HEAD"), self.brief.base_commit)

    def _install_slow_git(self) -> Path:
        marker = self.root / "slow-git-pid"
        executable = self.root / "slow-git"
        executable.write_text(
            f"#!{sys.executable}\n"
            "import os,time\nfrom pathlib import Path\n"
            f"Path({str(marker)!r}).write_text(str(os.getpid()))\n"
            "time.sleep(30)\n"
        )
        executable.chmod(0o700)
        self.broker.git = executable
        return marker

    def test_operation_cancellation_kills_its_exact_git_process(self) -> None:
        marker = self._install_slow_git()
        cancelled = Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                self.broker.run_operation,
                lambda: self.broker.snapshot(("adder.py", "tests/test_adder.py")),
                10,
                cancelled,
            )
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(marker.exists())
                pid = int(marker.read_text())
                cancelled.set()
                with self.assertRaises(InterruptedError):
                    future.result(timeout=3)
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)
            finally:
                cancelled.set()
        self.broker.git = Path("/usr/bin/git")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.brief.base_commit)

    def test_aggregate_deadline_kills_command_before_per_command_limit(self) -> None:
        marker = self._install_slow_git()
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            self.broker.run_operation(
                lambda: self.broker.snapshot(("adder.py", "tests/test_adder.py")),
                1,
                Event(),
            )
        self.assertLess(time.monotonic() - started, 3)
        self.assertTrue(marker.exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int(marker.read_text()), 0)
        self.broker.git = Path("/usr/bin/git")

    def test_waiting_operation_cancellation_does_not_cancel_active_owner(self) -> None:
        started, release = Event(), Event()
        active_cancelled, waiting_cancelled = Event(), Event()
        waiting_calls: list[str] = []

        def first() -> str:
            started.set()
            self.assertTrue(release.wait(timeout=5))
            return "first complete"

        with ThreadPoolExecutor(max_workers=2) as pool:
            active = pool.submit(self.broker.run_operation, first, 10, active_cancelled)
            self.assertTrue(started.wait(timeout=3))
            waiting = pool.submit(
                self.broker.run_operation,
                lambda: waiting_calls.append("called"),
                10,
                waiting_cancelled,
            )
            try:
                waiting_cancelled.set()
                with self.assertRaises(InterruptedError):
                    waiting.result(timeout=3)
            finally:
                release.set()
            self.assertEqual(active.result(timeout=3), "first complete")
        self.assertEqual(waiting_calls, [])
        self.assertFalse(active_cancelled.is_set())

    def test_cancelled_commit_is_consumed_and_recoverable(self) -> None:
        class CancelAfterCommit(CodingVCS):
            cancelled: Event

            def _git(self, cwd: Path, *args: str) -> str:
                output = super()._git(cwd, *args)
                if args[0] == "commit":
                    self.cancelled.set()
                return output

        self.broker.close()
        broker = CancelAfterCommit(
            Path("/usr/bin/git"), self.repo, self.root / "staging"
        )
        self.broker = broker
        cancelled = Event()
        broker.cancelled = cancelled
        patch = good_patch(self.brief)
        diff = broker.stage(self.brief, patch)
        with self.assertRaises(InterruptedError):
            broker.run_operation(
                lambda: broker.integrate(self.brief, patch, digest(diff.encode())),
                20,
                cancelled,
            )
        self.assertEqual(self.git("rev-parse", "HEAD"), self.brief.base_commit)
        with self.assertRaises(ValueError):
            broker.integrate(self.brief, patch, digest(diff.encode()))
        broker.close()
        stage = Path(self.brief.assignment.worktree or "")
        self.assertTrue(stage.exists())
        self.assertIn("return a + b", (stage / "adder.py").read_text())
