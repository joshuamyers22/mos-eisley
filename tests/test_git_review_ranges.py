"""Literal file selection, bounded source excerpts and revision-bound comparisons."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase

from test_conversation_git_review import packet_for
from test_git_review import RepositoryFixture

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.git_review import (
    MAX_FILE_BYTES,
    GitReviewScope,
    GitReviewSelection,
    GitReviewTarget,
    freeze_git_scope,
    revalidate_git_scope,
)
from mos_eisley.git_review_cli import parse_review_selection
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


class FileRangeTests(RepositoryFixture, TestCase):
    def test_lf_coordinates_preserve_unicode_crlf_and_blank_lines(self) -> None:
        self.path.write_bytes("OUTSIDE-FIRST\r\nα\u2028β\r\n\r\nOUTSIDE-LAST".encode())
        scope = self.scope("/review --range pricing.py:2-3")
        self.assertIn("2: α\u2028β\r\n3: \r\n", scope.brief().diff)
        self.assertNotIn("OUTSIDE-", scope.brief().diff)

    def test_unborn_and_detached_head_allow_source_only_selection(self) -> None:
        self.git("checkout", "--detach", "HEAD")
        self.assertTrue(self.scope("/review --file pricing.py").complete)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["/usr/bin/git", "init", "-q", str(root)], check=True)
            (root / "new").write_text("source only\n")
            scope = freeze_git_scope(
                root, parse_review_selection("/review --range new:1-1")
            )
            self.assertIsNone(scope.head)
            self.assertIn("source only", scope.brief().diff)

    def scope(self, command: str) -> GitReviewScope:
        return freeze_git_scope(self.root, parse_review_selection(command))

    def test_source_only_whole_file_has_no_diff_and_pins_exact_bytes(self) -> None:
        scope = self.scope('/review --file pricing.py --criteria "Check the boundary."')
        self.assertEqual(scope.selection.kind, "files")
        self.assertIsNone(scope.base)
        self.assertIsNone(scope.target)
        self.assertEqual(scope.files[0].after_sha256, digest(self.path.read_bytes()))
        self.assertIn("1: if quantity >= 10:", scope.brief().diff)
        self.assertIn("no comparison diff", scope.brief().diff)
        self.assertEqual(scope.brief().spec, "Check the boundary.")
        self.assertIn("source-only", scope.preview_text())

    def test_disjoint_ranges_exclude_other_lines_and_normalize_selection_order(
        self,
    ) -> None:
        self.path.write_text("OUTSIDE-ONE\nselected two\nOUTSIDE-THREE\nselected four")
        first = self.scope("/review --range pricing.py:4-4 --range pricing.py:2-2")
        second = self.scope("/review --range pricing.py:2-2 --range pricing.py:4-4")
        self.assertEqual(first, second)
        self.assertIn("2: selected two", first.brief().diff)
        self.assertIn("4: selected four", first.brief().diff)
        self.assertIn("No newline at end of file", first.brief().diff)
        self.assertNotIn("OUTSIDE-", canonical_bytes(first).decode())
        self.assertEqual(len(first.files), 1)
        self.assertEqual(first.files[0].after_sha256, digest(self.path.read_bytes()))

    def test_range_comparison_preserves_original_line_numbers_and_excludes_context(
        self,
    ) -> None:
        self.path.write_text("OUTSIDE-FIRST\nold selected\nOUTSIDE-LAST\n")
        self.commit("three lines")
        self.path.write_text("OUTSIDE-FIRST\nnew selected\nOUTSIDE-LAST\n")
        scope = self.scope("/review --uncommitted --range pricing.py:2-2")
        self.assertIn("@@ -2 +2 @@", scope.brief().diff)
        self.assertIn("-old selected", scope.brief().diff)
        self.assertIn("+new selected", scope.brief().diff)
        self.assertNotIn("OUTSIDE-", scope.brief().diff)
        self.assertIn("excerpt comparisons", scope.brief().constraints)

    def test_staged_revert_is_preserved_within_selected_interval(self) -> None:
        self.path.write_text("if quantity > 10:\n    discount()\n")
        self.git("add", "pricing.py")
        self.path.write_text("if quantity >= 10:\n    discount()\n")
        scope = self.scope("/review --uncommitted --range pricing.py:1-1")
        self.assertIn("[staged]", scope.brief().diff)
        self.assertIn("+if quantity > 10:", scope.brief().diff)
        self.assertIn("[unstaged]", scope.brief().diff)
        self.assertIn("+if quantity >= 10:", scope.brief().diff)
        self.assertNotIn("discount()", scope.brief().diff)

    def test_narrowing_never_opens_unselected_working_files_or_blobs(self) -> None:
        with TemporaryDirectory() as outside:
            secret = Path(outside) / "secret"
            secret.write_text("OUTSIDE-SECRET")
            (self.root / "unsafe").symlink_to(secret)
            (self.root / "other.txt").write_text("OTHER-FILE-SECRET")
            self.path.write_text("selected change\n")
            scope = self.scope("/review --uncommitted --file pricing.py")
            self.assertEqual([file.path for file in scope.files], ["pricing.py"])
            self.assertNotIn("SECRET", scope.brief().diff)

    def test_missing_directory_and_unsafe_paths_fail(self) -> None:
        for command in (
            "/review --file missing",
            "/review --file .",
            "/review --file ../outside",
            "/review --file /outside",
            "/review --file a/../pricing.py",
            "/review --file a//b",
        ):
            with (
                self.subTest(command=command),
                self.assertRaises((ValueError, OSError)),
            ):
                self.scope(command)
        (self.root / "directory").mkdir()
        with self.assertRaises(ValueError):
            self.scope("/review --file directory")

    def test_invalid_duplicate_overlapping_or_ambiguous_selectors_fail(self) -> None:
        for command in (
            "/review",
            "/review --criteria only",
            "/review --range pricing.py:0-1",
            "/review --range pricing.py:2-1",
            "/review --range pricing.py:1",
            "/review --range pricing.py:1-2-3",
            "/review --range pricing.py:one-two",
            "/review --range pricing.py:١-٢",
            "/review --file pricing.py --file pricing.py",
            "/review --file pricing.py --range pricing.py:1-1",
            "/review --range pricing.py:1-2 --range pricing.py:2-2",
            "/review --file pricing.py --parent 1",
            "/review --uncommitted --base main --file pricing.py",
        ):
            with self.subTest(command=command), self.assertRaises(ValueError):
                parse_review_selection(command)
        for command in (
            "/review --range pricing.py:1-3",
            "/review --range pricing.py:3-3",
        ):
            with (
                self.subTest(command=command),
                self.assertRaisesRegex(ValueError, "line count"),
            ):
                self.scope(command)

    def test_literal_globs_spaces_colons_and_option_like_paths(self) -> None:
        for name in ("literal*.py", "space name.py", "colon:1-2", "-option.py"):
            (self.root / name).write_text("first\nsecond\n")
            scope = self.scope(f'/review --file="{name}"')
            self.assertEqual(scope.files[0].path, name)
        scope = self.scope('/review --range "colon:1-2:2-2"')
        self.assertEqual(scope.files[0].path, "colon:1-2")
        self.assertIn("2: second", scope.brief().diff)
        with self.assertRaises(ValueError):
            self.scope('/review --file "*.py"')

    def test_out_of_range_and_other_file_edits_have_explicit_staleness_behavior(
        self,
    ) -> None:
        scope = self.scope("/review --range pricing.py:1-1")
        (self.root / "unselected").write_text("unrelated change")
        revalidate_git_scope(scope)
        self.path.write_text("if quantity >= 10:\n    changed_outside_selection()\n")
        with self.assertRaisesRegex(ValueError, "scope changed"):
            revalidate_git_scope(scope)

    def test_base_and_commit_ranges_ignore_dirty_checkout(self) -> None:
        self.path.write_text("if quantity > 10:\n    discount()\n")
        commit = self.commit("changed boundary")
        self.path.write_text("DIRTY-SECRET\n")
        for command in (
            "/review --base HEAD --range pricing.py:1-1",
            f"/review --commit {commit} --range pricing.py:1-1",
        ):
            with self.subTest(command=command):
                scope = self.scope(command)
                self.assertNotIn("DIRTY-SECRET", scope.brief().diff)
                self.assertIn("quantity > 10", scope.brief().diff)
                self.assertEqual(scope.target, commit)

    def test_deleted_added_empty_unchanged_and_clipped_comparison_sources(self) -> None:
        self.path.unlink()
        deleted = self.scope("/review --uncommitted --range pricing.py:1-1")
        self.assertIn("before (deleted file)", deleted.brief().diff)
        self.assertIn("/dev/null", deleted.brief().diff)
        self.git("checkout", "--", "pricing.py")
        unchanged = self.scope("/review --uncommitted --file pricing.py")
        self.assertIn("No differences", unchanged.brief().diff)
        self.path.write_text("first\nsecond\nadded third\n")
        clipped = self.scope("/review --uncommitted --range pricing.py:3-3")
        self.assertIn("interval clipped", clipped.brief().diff)
        self.assertIn("+added third", clipped.brief().diff)
        (self.root / "empty").write_text("")
        self.assertIn(
            "Selected source is empty", self.scope("/review --file empty").brief().diff
        )
        (self.root / "new").write_text("selected new\n")
        added = self.scope("/review --uncommitted --range new:1-1")
        self.assertTrue(added.files[0].untracked)
        self.assertIn("+selected new", added.brief().diff)

    def test_protected_binary_and_large_explicit_files_are_disclosed(self) -> None:
        (self.root / "binary").write_bytes(b"\x00PRIVATE")
        (self.root / "large").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
        private = self.root / ".mos-eisley-memory"
        private.mkdir()
        (private / "synthetic").write_text("PRIVATE-MEMORY")
        scope = self.scope(
            "/review --file binary --file large "
            "--file .mos-eisley-memory/synthetic --file pricing.py"
        )
        self.assertFalse(scope.complete)
        self.assertEqual(
            {f.omission for f in scope.files},
            {None, "binary", "oversized", "protected"},
        )
        self.assertNotIn("PRIVATE", canonical_bytes(scope).decode())
        with self.assertRaises(ValueError):
            packet_for(scope)

    def test_source_with_mode_marker_cannot_leak_unselected_lines(self) -> None:
        self.path.write_text("Mode/presence change:\nselected\nUNSELECTED-SECRET\n")
        scope = self.scope("/review --uncommitted --range pricing.py:2-2")
        self.assertNotIn("UNSELECTED-SECRET", scope.brief().diff)

    def test_old_scope_json_and_brief_bytes_remain_unchanged(self) -> None:
        self.path.write_text("changed\n")
        scope = self.scope("/review --uncommitted")
        encoded = canonical_bytes(scope)
        self.assertNotIn(b'"targets"', encoded)
        restored = GitReviewScope.model_validate_json(encoded)
        self.assertEqual(canonical_bytes(restored), encoded)
        self.assertEqual(restored.brief(), scope.brief())
        with self.assertRaises(ValueError):
            GitReviewSelection(kind="files")
        with self.assertRaises(ValueError):
            GitReviewTarget(path="pricing.py", start=1)

    def test_cli_json_and_slash_scope_are_identical(self) -> None:
        args = ["--uncommitted", "--range", "pricing.py:1-1"]
        expected = self.scope("/review " + " ".join(args))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "review-scope",
                "-C",
                str(self.root),
                *args,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            GitReviewScope.model_validate_json(json.dumps(payload["scope"])), expected
        )
        self.assertEqual(payload["brief"], expected.brief().model_dump(mode="json"))


class RangeConversationTests(RepositoryFixture, IsolatedAsyncioTestCase):
    async def test_range_packet_survives_both_stores_and_stale_resume_calls_no_critic(
        self,
    ) -> None:
        from unittest.mock import patch

        from mos_eisley.providers.recorded import RecordedReviewer

        scope = freeze_git_scope(
            self.root, parse_review_selection("/review --range pricing.py:1-1")
        )
        packet = packet_for(scope)
        cassette = demo_cassette()
        for store_type in (ConversationStore, SQLiteConversationStore):
            with (
                self.subTest(store=store_type.__name__),
                TemporaryDirectory() as directory,
            ):
                root = Path(directory) / "sessions"
                state = ConversationController.fresh(self.root, cassette)
                with store_type(root, state.session_id, self.root) as store:
                    store.save(state)
                    chat = ConversationController(state, cassette, store.save)
                    chat.submit_review(packet)
                with store_type(
                    root, state.session_id, self.root, create=False
                ) as store:
                    state = store.load()
                    self.assertEqual(state.entries[0].review_packet, packet)
                    self.path.write_text(
                        "if quantity >= 10:\n    outside_range_changed()\n"
                    )
                    chat = ConversationController(state, cassette, store.save)
                    with (
                        patch.object(RecordedReviewer, "critique") as critic,
                        self.assertRaisesRegex(ValueError, "scope changed"),
                    ):
                        await chat.step()
                    critic.assert_not_called()
                    self.assertEqual(chat.state.entries[0].status, "queued")
                self.path.write_text("if quantity >= 10:\n    discount()\n")

    async def test_tui_range_scope_parity_and_rejection_preserves_draft(
        self,
    ) -> None:
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        from test_conversation_tui import until

        from mos_eisley.conversation_tui import ConversationTUI

        command = "/review --range pricing.py:1-1"
        scope = freeze_git_scope(self.root, parse_review_selection(command))
        cassette = demo_cassette()
        chat = ConversationController(
            ConversationController.fresh(self.root, cassette),
            cassette,
            lambda state: None,
        )
        with create_pipe_input() as input:
            ui = ConversationTUI(
                chat, packet_for(scope), input=input, output=DummyOutput()
            )
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text(command + "\r")
                await until(
                    lambda: (
                        bool(chat.state.entries)
                        and chat.state.entries[0].status == "completed"
                    )
                )
                self.assertEqual(
                    chat.state.entries[0].review_packet.git_scope
                    if chat.state.entries[0].review_packet
                    else None,
                    scope,
                )
                self.assertIn(scope.scope_id, ui.transcript.text)
                self.assertNotIn("discount()", ui.transcript.text)
                invalid = "/review --range pricing.py:1-99"
                input.send_text(invalid + "\r")
                await until(lambda: "line count" in ui.notice and not ui.sending)
                self.assertEqual(ui.editor.text, invalid)
                self.assertEqual(len(chat.state.entries), 1)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_exact_range_packet_dispatches_in_plain_terminal_without_chat_spend(
        self,
    ) -> None:
        command = "/review --range pricing.py:1-1"
        scope = freeze_git_scope(self.root, parse_review_selection(command))
        packet = packet_for(scope)
        cassette = demo_cassette()
        controller = ConversationController(
            ConversationController.fresh(self.root, cassette),
            cassette,
            lambda state: None,
        )
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait(command)
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        await terminal(controller, queue, events.append, packet)
        self.assertEqual(controller.state.exchanges_consumed, 0)
        self.assertIsNotNone(controller.state.entries[0].review_result)
        preview = next(e for e in events if e["type"] == "conversation.review_scope")
        self.assertEqual(preview["scope_id"], scope.scope_id)
        self.assertEqual(preview["selection"], scope.selection.model_dump(mode="json"))
