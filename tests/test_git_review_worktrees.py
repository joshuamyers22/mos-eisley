"""Standard and real Mos-managed worktrees retain the read-only review boundary."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import test_coding_vcs as coding_fixture
import test_git_review_ranges as range_fixture
from test_conversation_git_review import packet_for
from test_git_review import RepositoryFixture

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.core.models import canonical_bytes
from mos_eisley.git_review import (
    GitReadBroker,
    GitReviewScope,
    GitReviewSelection,
    freeze_git_scope,
    revalidate_git_scope,
)
from mos_eisley.git_review_cli import parse_review_selection
from mos_eisley.providers.recorded import RecordedReviewer
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.review_source import read_review_source


class WorktreeFixture(RepositoryFixture):
    def setUp(self) -> None:
        super().setUp()
        self.parent = self.root
        self.linked_temp = TemporaryDirectory()
        self.git(
            "worktree", "add", "--detach", str(Path(self.linked_temp.name) / "child")
        )
        self.root = Path(self.linked_temp.name).resolve() / "child"
        self.path = self.root / "pricing.py"
        self.admin = Path((self.root / ".git").read_text()[8:].strip())
        self.common = self.parent / ".git"

    def tearDown(self) -> None:
        self.linked_temp.cleanup()
        super().tearDown()


def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mode)
        for path in root.rglob("*")
        if path.is_file()
    }


class WorktreeScopeTests(WorktreeFixture, TestCase):
    def test_linked_scope_pins_shared_and_local_identity_and_is_read_only(self) -> None:
        self.path.write_text("changed child\n")
        before = (snapshot(self.parent), snapshot(self.root))
        scope = freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))
        self.assertEqual(scope.schema_version, 2)
        assert scope.worktree is not None
        self.assertEqual(scope.worktree.admin, str(self.admin))
        self.assertEqual(scope.worktree.common, str(self.common))
        self.assertEqual(scope.git_inode, self.admin.stat().st_ino)
        self.assertEqual(
            scope.worktree.common_identity.inode, self.common.stat().st_ino
        )
        self.assertIn("+changed child", scope.brief().diff)
        self.assertEqual(
            GitReviewScope.model_validate_json(canonical_bytes(scope)), scope
        )
        revalidate_git_scope(scope)
        self.assertEqual(before, (snapshot(self.parent), snapshot(self.root)))

    def test_all_presets_use_worktree_head_index_and_selected_source(self) -> None:
        self.path.write_text("committed child\n")
        commit = self.commit("child change")
        self.path.write_text("staged child\n")
        self.git("add", "pricing.py")
        self.path.write_text("unstaged child\n")
        (self.root / "new.txt").write_text("untracked child\n")
        for command in (
            "/review --uncommitted",
            "/review --base main",
            f"/review --commit {commit}",
            "/review --range pricing.py:1-1",
        ):
            with self.subTest(command=command):
                scope = freeze_git_scope(self.root, parse_review_selection(command))
                self.assertEqual(scope.head, commit)
                self.assertTrue(scope.complete)
                self.assertNotIn(
                    "discount()",
                    scope.brief().diff if scope.selection.kind == "files" else "",
                )
        scope = freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))
        self.assertIn("[staged]", scope.brief().diff)
        self.assertIn("[unstaged]", scope.brief().diff)
        self.assertTrue(any(f.untracked for f in scope.files))
        self.assertIn("quantity >=", (self.parent / "pricing.py").read_text())

    def test_redirects_bad_backlinks_and_nonstandard_common_paths_precede_git(
        self,
    ) -> None:
        for path, bad in (
            (self.root / ".git", b"gitdir: relative/path\n"),
            (self.root / ".git", b"gitdir: /arbitrary/repository\n"),
            (self.root / ".git", b"gitdir: /bad/../repo/.git/worktrees/a\n"),
            (self.root / ".git", b"gitdir: \xff\n"),
            (self.root / ".git", b"gitdir: " + b"x" * 4096),
            (self.admin / "commondir", b"/arbitrary/.git\n"),
            (self.admin / "commondir", b"../../other\n"),
            (self.admin / "gitdir", os.fsencode(self.parent / ".git") + b"\n"),
        ):
            with self.subTest(path=path, bad=bad[:80]):
                original = path.read_bytes()
                try:
                    path.write_bytes(bad)
                    self.assert_rejected_before_git()
                finally:
                    path.write_bytes(original)

    def assert_rejected_before_git(self) -> None:
        with patch("mos_eisley.git_review.subprocess.Popen") as process:
            with self.assertRaises((ValueError, OSError)):
                GitReadBroker(self.root)
            process.assert_not_called()

    def test_pointer_links_and_unsafe_permissions_rejected_before_git(self) -> None:
        for path in (
            self.root / ".git",
            self.admin / "commondir",
            self.admin / "gitdir",
        ):
            for kind in ("symlink", "hardlink", "permissions"):
                with self.subTest(path=path, kind=kind):
                    data, mode = path.read_bytes(), path.stat().st_mode
                    backup = path.with_name(path.name + ".saved")
                    try:
                        if kind == "permissions":
                            path.chmod(0o666)
                        else:
                            path.rename(backup)
                            if kind == "symlink":
                                path.symlink_to(backup)
                            else:
                                os.link(backup, path)
                        self.assert_rejected_before_git()
                    finally:
                        path.unlink()
                        if backup.exists():
                            backup.rename(path)
                        else:
                            path.write_bytes(data)
                        path.chmod(mode)

    def test_common_namespace_and_admin_symlinks_rejected_before_git(self) -> None:
        for path in (self.common, self.common / "worktrees", self.admin):
            with self.subTest(path=path):
                backup = path.with_name(path.name + ".saved")
                path.rename(backup)
                try:
                    path.symlink_to(backup, target_is_directory=True)
                    self.assert_rejected_before_git()
                finally:
                    path.unlink()
                    backup.rename(path)

    def test_wrong_owner_and_writable_metadata_directories_fail_before_git(
        self,
    ) -> None:
        with patch(
            "mos_eisley.git_review_metadata.os.getuid", return_value=os.getuid() + 1
        ):
            self.assert_rejected_before_git()
        for path in (
            self.root,
            self.parent,
            self.common,
            self.common / "worktrees",
            self.admin,
        ):
            with self.subTest(path=path):
                mode = path.stat().st_mode
                path.chmod(0o777)
                try:
                    self.assert_rejected_before_git()
                finally:
                    path.chmod(mode)

    def test_config_and_external_objects_fail_before_git(self) -> None:
        for path, data in (
            (self.common / "config", b"[include]\npath=/outside\n"),
            (self.common / "config.worktree", b"[include]\npath=/outside\n"),
            (self.admin / "config.worktree", b"[include]\npath=/outside\n"),
            (self.common / "objects/info/alternates", b"/outside\n"),
            (self.common / "objects/info/http-alternates", b"https://invalid\n"),
            (self.common / "objects/unsafe.promisor", b""),
        ):
            with self.subTest(path=path):
                original = path.read_bytes() if path.exists() else None
                path.write_bytes(data)
                try:
                    self.assert_rejected_before_git()
                finally:
                    if original is None:
                        path.unlink()
                    else:
                        path.write_bytes(original)

    def test_changed_pointer_and_config_rejected_before_next_process(self) -> None:
        for path in (self.admin / "gitdir", self.common / "config"):
            with self.subTest(path=path):
                broker = GitReadBroker(self.root)
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"\n")
                    with patch("mos_eisley.git_review.subprocess.Popen") as process:
                        with self.assertRaises(ValueError):
                            broker.capture(GitReviewSelection(kind="uncommitted"))
                        process.assert_not_called()
                finally:
                    path.write_bytes(original)
                    broker.close()

    def test_replaced_pointer_or_admin_invalidates_identical_source(self) -> None:
        for path in (
            self.root / ".git",
            self.admin / "commondir",
            self.admin / "gitdir",
        ):
            with self.subTest(path=path):
                scope = self.changed_scope()
                backup = path.with_name(path.name + ".saved")
                path.rename(backup)
                path.write_bytes(backup.read_bytes())
                try:
                    with self.assertRaisesRegex(ValueError, "scope changed"):
                        revalidate_git_scope(scope)
                finally:
                    path.unlink()
                    backup.rename(path)
        scope = self.changed_scope()
        backup = self.admin.with_name("saved-admin")
        self.admin.rename(backup)
        self.admin.mkdir()
        shutil.copytree(backup, self.admin, dirs_exist_ok=True)
        try:
            with self.assertRaisesRegex(ValueError, "scope changed"):
                revalidate_git_scope(scope)
        finally:
            shutil.rmtree(self.admin)
            backup.rename(self.admin)

    def test_replaced_shared_repository_or_namespace_is_stale(self) -> None:
        for path in (self.common, self.common / "worktrees"):
            with self.subTest(path=path):
                scope = self.changed_scope()
                backup = path.with_name(path.name + ".saved")
                path.rename(backup)
                shutil.copytree(backup, path)
                try:
                    with self.assertRaisesRegex(ValueError, "scope changed"):
                        revalidate_git_scope(scope)
                finally:
                    shutil.rmtree(path)
                    backup.rename(path)

    def test_metadata_change_between_capture_passes_aborts_acquisition(self) -> None:
        original = GitReadBroker.capture
        calls = 0

        def capture(
            broker: GitReadBroker,
            selection: GitReviewSelection,
            *,
            disclose_unavailable: bool = False,
        ) -> GitReviewScope:
            nonlocal calls
            scope = original(
                broker, selection, disclose_unavailable=disclose_unavailable
            )
            calls += 1
            if calls == 2:
                (self.admin / "gitdir").write_text(str(self.parent / ".git") + "\n")
            return scope

        self.path.write_text("changed child\n")
        with (
            patch.object(GitReadBroker, "capture", capture),
            self.assertRaisesRegex(ValueError, "reciprocal"),
        ):
            freeze_git_scope(self.root, GitReviewSelection(kind="uncommitted"))

    def test_helpers_disabled_and_parent_source_excluded(self) -> None:
        sentinel = self.parent / "helper-ran"
        helper = self.parent / "helper"
        helper.write_text(f"#!/bin/sh\ntouch '{sentinel}'\nexit 1\n")
        helper.chmod(0o700)
        for key in ("core.fsmonitor", "diff.external", "diff.custom.textconv"):
            self.git("config", key, str(helper))
        (self.root / ".gitattributes").write_text("*.py diff=custom\n")
        (self.parent / "pricing.py").write_text("PARENT-PRIVATE-SOURCE\n")
        scope = self.changed_scope()
        self.assertNotIn("PARENT-PRIVATE", scope.brief().diff)
        self.assertFalse(sentinel.exists())

    def test_live_source_guard_accepts_binding_and_rejects_stale_metadata(self) -> None:
        scope = self.changed_scope()
        with TemporaryDirectory() as directory:
            artifact = Path(directory) / "scope.json"
            artifact.write_bytes(canonical_bytes(scope))
            self.assertEqual(
                read_review_source(artifact, scope.scope_id, self.root, scope.brief()),
                scope,
            )
            other = self.parent
            with self.assertRaisesRegex(ValueError, "owner's exact"):
                read_review_source(artifact, scope.scope_id, other, scope.brief())
            (self.admin / "gitdir").write_text(str(other / ".git") + "\n")
            with patch("asyncio.create_subprocess_exec") as child:
                with self.assertRaisesRegex(ValueError, "reciprocal"):
                    read_review_source(
                        artifact, scope.scope_id, self.root, scope.brief()
                    )
                child.assert_not_called()

    def test_cli_and_slash_frozen_briefs_match(self) -> None:
        self.path.write_text("changed child\n")
        scope = freeze_git_scope(
            self.root, parse_review_selection("/review --range pricing.py:1-1")
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "review-scope",
                "-C",
                str(self.root),
                "--range",
                "pricing.py:1-1",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["scope"], scope.model_dump(mode="json"))
        self.assertEqual(payload["brief"], scope.brief().model_dump(mode="json"))


class ManagedProducerTests(TestCase):
    def test_real_coding_vcs_stage_review_retains_exact_integration(self) -> None:
        fixture = coding_fixture.CodingVCSTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        patch = coding_fixture.good_patch(fixture.brief)
        staged_diff = fixture.broker.stage(fixture.brief, patch)
        worktree = fixture.brief.assignment.worktree
        assert worktree is not None
        child = Path(worktree)
        before = (snapshot(fixture.repo), snapshot(child))
        scope = freeze_git_scope(child, GitReviewSelection(kind="uncommitted"))
        self.assertEqual(scope.schema_version, 2)
        self.assertIn("+    return a + b", scope.brief().diff)
        revalidate_git_scope(scope)
        self.assertEqual(before, (snapshot(fixture.repo), snapshot(child)))
        from mos_eisley.core.models import digest

        commit = fixture.broker.integrate(
            fixture.brief, patch, digest(staged_diff.encode())
        )
        self.assertEqual(commit, fixture.git("rev-parse", "HEAD"))


class WorktreeConversationTests(WorktreeFixture, range_fixture.RangeConversationTests):
    async def test_both_stores_preserve_binding_and_stale_resume_calls_no_critic(
        self,
    ) -> None:
        scope = self.changed_scope()
        packet = packet_for(scope)
        cassette = demo_cassette()
        for store_type in (ConversationStore, SQLiteConversationStore):
            with (
                self.subTest(store=store_type.__name__),
                TemporaryDirectory() as directory,
            ):
                storage = Path(directory) / "sessions"
                state = ConversationController.fresh(self.root, cassette)
                with store_type(storage, state.session_id, self.root) as store:
                    store.save(state)
                    chat = ConversationController(state, cassette, store.save)
                    chat.submit_review(packet)
                with store_type(
                    storage, state.session_id, self.root, create=False
                ) as store:
                    state = store.load()
                    self.assertEqual(state.entries[0].review_packet, packet)
                    self.path.write_text("stale child\n")
                    chat = ConversationController(state, cassette, store.save)
                    with patch.object(RecordedReviewer, "critique") as critic:
                        with self.assertRaisesRegex(ValueError, "scope changed"):
                            await chat.step()
                        critic.assert_not_called()
                    self.assertEqual(chat.state.entries[0].status, "queued")
                self.path.write_text("if quantity > 10:\n    discount()\n")

    async def test_plain_terminal_uses_frozen_brief_without_chat_spend(self) -> None:
        scope = self.changed_scope()
        cassette = demo_cassette()
        controller = ConversationController(
            ConversationController.fresh(self.root, cassette),
            cassette,
            lambda state: None,
        )
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait("/review --uncommitted")
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        await terminal(controller, queue, events.append, packet_for(scope))
        self.assertIsNotNone(controller.state.entries[0].review_result)
        self.assertEqual(controller.state.exchanges_consumed, 0)
