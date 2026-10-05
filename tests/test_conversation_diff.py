"""Real Git diffs, source provenance, historical findings and responsive controls."""

import asyncio
import fcntl
import json
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.selection import SelectionState
from test_conversation_tui import until
from test_git_review import RepositoryFixture

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_diff import (
    DiffAttachment,
    DiffRefresh,
    DiffSnapshot,
    attach_lines,
    attachment_sources,
    attachment_suffix,
    capture_diff,
    file_identity,
    patch_lines,
)
from mos_eisley.conversation_diff_commands import DiffCommands
from mos_eisley.conversation_findings import retained_findings
from mos_eisley.conversation_git_review_tui import GitReviewTUI as ConversationTUI
from mos_eisley.conversation_git_review_tui import display_text
from mos_eisley.conversation_input import ConversationSubmission
from mos_eisley.conversation_pending import PendingTextLimits
from mos_eisley.conversation_review import ConversationReviewPacket, review_summary
from mos_eisley.conversation_state import ConversationEntry, WorkingConversationState
from mos_eisley.core.models import (
    CriticRequest,
    CriticResult,
    CriticSpec,
    Critique,
    Evidence,
    Finding,
    JudgeDecision,
    JudgeRequest,
    ReviewPolicy,
    ReviewResult,
    Verdict,
    canonical_bytes,
    digest,
)
from mos_eisley.core.protocol import ModelRequest, ModelResponse
from mos_eisley.git_review import GitReadBroker
from mos_eisley.providers.recorded import Cassette, CriticRecording
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


def completed_review(scope: DiffSnapshot, *, upheld: bool = True) -> ConversationEntry:
    brief = scope.scope.brief()
    finding = Finding(
        location="pricing.py:1",
        category="correctness",
        impact="high",
        claim="Synthetic boundary finding.",
        evidence=Evidence(
            source="diff",
            quote="+if quantity > 10:",
            explanation="Synthetic changed line.",
        ),
        suggested_fix="Restore the inclusive fixture boundary.",
    )
    critique = Critique(findings=(finding,))
    critic = CriticSpec(
        id="fixture-critic",
        provider="fixture",
        model="fixture",
        persona="Check fixture.",
    )
    judge = JudgeDecision(
        upheld=(finding.finding_id,) if upheld else (),
        rationale="Synthetic disposition.",
    )
    request = JudgeRequest(brief=brief, findings=(finding,))
    packet = ConversationReviewPacket(
        schema_version=3,
        git_scope=scope.scope,
        brief=brief,
        cassette=Cassette(
            brief_id=brief.brief_id,
            critics=(
                CriticRecording(
                    critic=critic,
                    request_sha256=digest(
                        canonical_bytes(
                            CriticRequest(brief=brief, persona=critic.persona)
                        )
                    ),
                    response=critique,
                ),
            ),
            judge_request_sha256=digest(canonical_bytes(request)),
            judge_response=judge,
        ),
        policy=ReviewPolicy(min_critics=1, min_providers=1),
    )
    result = ReviewResult(
        critics=(CriticResult(critic=critic, status="completed", critique=critique),),
        judge_request=request,
        judge_decision=judge,
        verdict=Verdict(
            brief_id=brief.brief_id,
            decision="revise" if upheld else "accept",
            findings=(finding,) if upheld else (),
            required_changes=(finding.finding_id,) if upheld else (),
            rationale="Synthetic only.",
        ),
    )
    return ConversationEntry(
        text="Review this change.",
        status="completed",
        review_packet=packet,
        review_result=result,
        answer=review_summary(result),
    )


class DiffTests(RepositoryFixture, TestCase):
    def test_real_pty_panel_focus_resize_and_draft_preservation(self) -> None:
        self.changed_scope()
        with TemporaryDirectory() as directory:
            storage = Path(directory)
            cassette = storage / "cassette.json"
            cassette.write_bytes(canonical_bytes(demo_cassette()))
            master, slave = pty.openpty()
            original = termios.tcgetattr(slave)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 120, 0, 0))
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "chat",
                    "--tui",
                    "--cassette",
                    str(cassette),
                    "--workspace",
                    str(self.root),
                    "--storage",
                    str(storage / "sessions"),
                ],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env={**os.environ, "TERM": "xterm-256color"},
                start_new_session=True,
            )
            output = bytearray()

            def read_until(value: bytes) -> None:
                deadline = time.monotonic() + 10
                while value not in output:
                    if time.monotonic() >= deadline:
                        raise AssertionError(repr(output[-4000:]))
                    readable, _, _ = select.select([master], [], [], 0.1)
                    if readable:
                        data = os.read(master, 16384)
                        output.extend(data)
                        if b"\x1b[6n" in data:
                            os.write(master, b"\x1b[1;1R")

            try:
                read_until(b"Directory:")
                os.write(master, b"PRESERVED DRAFT\x1b[21~\x0c")
                read_until(b"Basis:")
                read_until(b"PRESERVED DRAFT")
                self.assertIn(b"Conversation", output)
                for columns in (80, 120):
                    output.clear()
                    fcntl.ioctl(
                        slave,
                        termios.TIOCSWINSZ,
                        struct.pack("HHHH", 32, columns, 0, 0),
                    )
                    os.kill(process.pid, signal.SIGWINCH)
                    os.write(master, b"\x0c")
                    read_until(b"Basis:")
                    read_until(b"PRESERVED DRAFT")
                output.clear()
                os.write(master, b"\x1b[21~\x0c")
                read_until(b"Conversation")
                read_until(b"PRESERVED DRAFT")
                os.write(master, b"\x04")
                read_until(b"conversation.saved")
                self.assertEqual(process.wait(timeout=5), 0)
                restored = termios.tcgetattr(slave)
                restored[3] &= ~getattr(termios, "PENDIN", 0)
                original[3] &= ~getattr(termios, "PENDIN", 0)
                self.assertEqual(restored, original)
                saved = json.loads(
                    next((storage / "sessions").glob("*.json")).read_bytes()
                )
                self.assertEqual(saved["state"]["entries"], [])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                os.close(master)
                os.close(slave)

    def test_no_changes_and_unborn_untracked(self) -> None:
        snapshot = capture_diff(self.root)
        self.assertEqual(snapshot.total_files, 0)
        self.assertIn("No changes.", snapshot.describe())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            import subprocess

            subprocess.run(["/usr/bin/git", "init", "-q", str(root)], check=True)
            (root / "new").write_text("new source\n")
            unborn = capture_diff(root)
            self.assertIsNone(unborn.scope.head)
            self.assertTrue(unborn.scope.files[0].untracked)
            self.assertIn("(unborn)", unborn.basis_label)

    def test_staged_revert_keeps_both_comparisons_and_exact_rows(self) -> None:
        self.changed_scope()
        self.git("add", "pricing.py")
        self.path.write_text("if quantity >= 10:\n    discount()\n")
        snapshot = capture_diff(self.root)
        file = snapshot.scope.files[0]
        rows = patch_lines(file)
        changes = [r for r in rows if r.old == 1 or r.new == 1]
        self.assertEqual({r.basis for r in changes}, {"staged", "unstaged"})
        self.assertTrue(file.staged and file.unstaged)
        selected = next(
            i + 1 for i, r in enumerate(rows) if r.text.startswith("+if quantity >")
        )
        attachment = attach_lines(snapshot, file.path, selected, selected)
        self.assertEqual(
            (attachment.old_start, attachment.new_start, attachment.basis),
            (None, 1, "staged"),
        )
        self.assertEqual(attachment.excerpt, "+if quantity > 10:\n")

    def test_pages_are_partial_and_do_not_open_unselected_paths(self) -> None:
        for index in range(70):
            (self.root / f"new-{index:03d}").write_text("new source\n")
        with patch.object(GitReadBroker, "_blob", wraps=None) as read:
            # New files have no blobs; verify page capture uses only its eight names.
            read.return_value = None
            first = capture_diff(self.root)
        self.assertEqual(
            (first.total_files, len(first.scope.files), first.next_offset), (70, 8, 8)
        )
        second = capture_diff(self.root, 8)
        self.assertFalse(
            set(f.path for f in first.scope.files)
            & set(f.path for f in second.scope.files)
        )
        self.assertIn("Partial file list", first.describe())
        with self.assertRaises(ValueError):
            capture_diff(self.root, 99)

    def test_aggregate_bytes_reduce_page_without_claiming_completeness(self) -> None:
        for index in range(8):
            (self.root / f"new-{index}").write_text("x" * 14000 + "\n")
        snapshot = capture_diff(self.root)
        self.assertLess(len(snapshot.scope.files), 8)
        self.assertEqual(snapshot.total_files, 8)
        self.assertIsNotNone(snapshot.next_offset)

    def test_omissions_and_hostile_display_do_not_read_sources(self) -> None:
        (self.root / ".agents").mkdir()
        (self.root / ".agents" / "secret").write_text("DO NOT ATTACH\n")
        (self.root / "binary").write_bytes(b"\x00secret")
        (self.root / "large").write_text("z" * 17000)
        (self.root / "link").symlink_to(self.path)
        (self.root / "escape\x1b[31m").write_text("hostile\x1b[2J\n")
        snapshot = capture_diff(self.root)
        omissions = {f.path: f.omission for f in snapshot.scope.files}
        self.assertEqual(omissions[".agents/secret"], "protected")
        self.assertEqual(omissions["binary"], "binary")
        self.assertEqual(omissions["large"], "oversized")
        self.assertEqual(omissions["link"], "unavailable")
        self.assertNotIn("DO NOT ATTACH", snapshot.describe())
        self.assertNotIn("\x1b", display_text(snapshot.describe()))
        with self.assertRaises(ValueError):
            attach_lines(snapshot, "binary", 1, 1)

    def test_deletions_renames_and_untracked_separate_status(self) -> None:
        self.git("mv", "pricing.py", "renamed.py")
        (self.root / "untracked").write_text("new\n")
        snapshot = capture_diff(self.root)
        files = {f.path: f for f in snapshot.scope.files}
        self.assertEqual(set(files), {"pricing.py", "renamed.py", "untracked"})
        self.assertTrue(files["pricing.py"].staged)
        self.assertTrue(files["renamed.py"].staged)
        self.assertTrue(files["untracked"].untracked)
        rows = patch_lines(files["pricing.py"])
        index = next(i + 1 for i, r in enumerate(rows) if r.old == 1)
        deleted = attach_lines(snapshot, "pricing.py", index, index)
        self.assertEqual((deleted.old_start, deleted.new_start), (1, None))

    def test_frozen_attachment_bytes_cannot_change_or_admit_mismatched_metadata(
        self,
    ) -> None:
        self.changed_scope()
        snapshot = capture_diff(self.root)
        rows = patch_lines(snapshot.scope.files[0])
        index = next(i + 1 for i, r in enumerate(rows) if r.new == 1)
        attachment = attach_lines(snapshot, "pricing.py", index, index)
        self.path.write_text("different now\n")
        self.assertNotEqual(
            file_identity(capture_diff(self.root).scope.files[0]),
            attachment.file_sha256,
        )
        self.assertIn("quantity > 10", attachment.excerpt)
        with self.assertRaises(ValueError):
            DiffAttachment.model_validate(
                {**attachment.model_dump(), "excerpt": "changed"}
            )
        with self.assertRaises(ValueError):
            ConversationEntry(
                text="missing source envelope", diff_attachments=(attachment,)
            )
        with self.assertRaises(ValueError):
            attach_lines(snapshot, "pricing.py", 1, 2)

    def test_crlf_unicode_and_unterminated_source_coordinates(self) -> None:
        self.path.write_bytes("α\r\nβ\u2028γ\nlast".encode())
        snapshot = capture_diff(self.root)
        added = [
            r
            for r in patch_lines(snapshot.scope.files[0])
            if r.new is not None and r.old is None
        ]
        self.assertEqual([r.new for r in added], [1, 2, 3])
        self.assertEqual(added[0].text, "+α\r\n")
        self.assertEqual(added[1].text, "+β\u2028γ\n")

    def test_unsafe_git_configuration_remains_rejected(self) -> None:
        self.changed_scope()
        self.git("config", "extensions.worktreeConfig", "true")
        with self.assertRaisesRegex(ValueError, "configuration"):
            capture_diff(self.root)


class DiffAsyncTests(RepositoryFixture, IsolatedAsyncioTestCase):
    def chat(self) -> ConversationController:
        cassette = demo_cassette()
        return ConversationController(
            ConversationController.fresh(self.root, cassette),
            cassette,
            lambda state: None,
        )

    async def test_fix_storage_failure_is_fatal_without_claiming_admission(
        self,
    ) -> None:
        self.changed_scope()
        entry = completed_review(capture_diff(self.root))
        chat = self.chat()
        chat.state = ConversationState.model_validate(
            {**chat.state.model_dump(), "entries": (entry,)}
        )
        key = retained_findings(chat.state.entries)[0].key
        accepted: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        queue: asyncio.Queue[str | ConversationSubmission | None] = asyncio.Queue()
        queue.put_nowait(ConversationSubmission("/diff fix " + key, False, accepted))
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        with (
            patch.object(chat, "save", side_effect=ValueError("storage changed")),
            self.assertRaisesRegex(ValueError, "storage changed"),
        ):
            await terminal(chat, queue, events.append)
        self.assertEqual(len(chat.state.entries), 1)
        self.assertTrue(accepted.cancelled())
        self.assertFalse(any(event["type"] == "message.queued" for event in events))

    async def test_cancelled_fix_handoff_cannot_admit_after_background_read(
        self,
    ) -> None:
        chat = self.chat()
        started, release = asyncio.Event(), asyncio.Event()

        async def execute(command: str) -> str:
            started.set()
            await release.wait()
            return "Fix this synthetic finding."

        accepted: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        queue: asyncio.Queue[str | ConversationSubmission | None] = asyncio.Queue()
        queue.put_nowait(
            ConversationSubmission("/diff fix synthetic-key", False, accepted)
        )
        queue.put_nowait(None)
        with patch.object(DiffCommands, "execute", side_effect=execute):
            task = asyncio.create_task(terminal(chat, queue, lambda event: None))
            await asyncio.wait_for(started.wait(), 2)
            accepted.cancel()
            release.set()
            await asyncio.wait_for(task, 2)
        self.assertEqual(chat.state.entries, ())
        self.assertEqual(chat.state.exchanges_consumed, 0)

    async def test_saved_attachment_cannot_retarget_another_workspace(self) -> None:
        self.changed_scope()
        snapshot = capture_diff(self.root)
        row = next(
            i + 1
            for i, r in enumerate(patch_lines(snapshot.scope.files[0]))
            if r.new == 1
        )
        attachment = attach_lines(snapshot, "pricing.py", row, row)
        foreign = DiffAttachment.model_validate(
            {**attachment.model_dump(), "workspace": str(self.root / "elsewhere")}
        )
        entry = ConversationEntry(
            text="Explain" + attachment_suffix((foreign,)), diff_attachments=(foreign,)
        )
        chat = self.chat()
        with self.assertRaisesRegex(ValueError, "another workspace"):
            ConversationState.model_validate_json(
                json.dumps(
                    {
                        **chat.state.model_dump(mode="json"),
                        "entries": [entry.model_dump(mode="json")],
                    }
                )
            )
        with self.assertRaisesRegex(ValueError, "another workspace"):
            chat.submit(entry.text, diff_attachments=(foreign,))
        self.assertEqual(chat.state.entries, ())

    async def test_admitted_source_is_in_actual_author_request_and_completed_entry(
        self,
    ) -> None:
        self.changed_scope()
        snapshot = capture_diff(self.root)
        row = next(
            i + 1
            for i, r in enumerate(patch_lines(snapshot.scope.files[0]))
            if r.new == 1
        )
        attachment = attach_lines(snapshot, "pricing.py", row, row)
        chat = self.chat()
        requests: list[ModelRequest] = []
        response = chat.cassette.exchanges[0].response
        assert response is not None

        class Client:
            async def complete(self, request: ModelRequest) -> ModelResponse:
                requests.append(request)
                return response

        with (
            TemporaryDirectory() as directory,
            SQLiteConversationStore(
                Path(directory) / "sessions", chat.state.session_id, self.root
            ) as store,
        ):
            store.save(chat.state)
            chat.save = store.save
            chat.submit(
                "Explain" + attachment_suffix((attachment,)),
                diff_attachments=(attachment,),
            )
            self.assertTrue(await chat.step(Client()))
            self.assertIn(
                "Untrusted frozen source attachments", requests[0].model_dump_json()
            )
            self.assertIn(attachment.excerpt_sha256, requests[0].model_dump_json())
            self.assertEqual(chat.state.entries[0].diff_attachments, (attachment,))
            self.assertEqual(chat.state.entries[0].status, "completed")
            self.assertIsNotNone(chat.state.entries[0].request_admission)
            working = store.load_working()
            self.assertEqual(working.entries[0].diff_attachments, (attachment,))
            restored = store.load()
            self.assertEqual(restored.entries[0].diff_attachments, (attachment,))

    async def test_mouse_selection_survives_refresh_and_clears_on_source_change(
        self,
    ) -> None:
        self.changed_scope()
        with create_pipe_input() as input:
            ui = ConversationTUI(self.chat(), input=input, output=DummyOutput())
            ui.diff_refresh.snapshot = capture_diff(self.root)
            ui.render_diff()
            document = ui.diff_pane.buffer.document
            rows = patch_lines(ui.diff_refresh.snapshot.scope.files[0])
            row = next(i for i, r in enumerate(rows) if r.new == 1)
            start = document.translate_row_col_to_index(
                ui.diff_patch_header_rows + row, 0
            )
            end = document.translate_row_col_to_index(
                ui.diff_patch_header_rows + row + 1, 0
            )
            ui.diff_pane.buffer.set_document(
                Document(document.text, end, SelectionState(start)),
                bypass_readonly=True,
            )
            ui.diff_pane.buffer.selection_state = SelectionState(start)
            (self.root / "aaa").write_text("unrelated\n")
            ui.diff_refresh.snapshot = capture_diff(self.root)
            ui.render_diff()
            self.assertIsNotNone(ui.diff_pane.buffer.document.selection)
            self.assertEqual(ui.diff_selected_path, "pricing.py")
            self.path.write_text("source changed\n")
            ui.diff_refresh.snapshot = capture_diff(self.root)
            ui.render_diff()
            self.assertIsNone(ui.diff_pane.buffer.document.selection)
            self.assertIn("selection cleared", ui.notice)

    async def test_attachment_freshness_after_source_disappears_from_diff(self) -> None:
        self.changed_scope()
        snapshot = capture_diff(self.root)
        row = next(
            i + 1
            for i, r in enumerate(patch_lines(snapshot.scope.files[0]))
            if r.new == 1
        )
        attachment = attach_lines(snapshot, "pricing.py", row, row)
        self.assertTrue(attachment_sources((attachment,))[attachment.excerpt_sha256])
        self.path.write_text("if quantity >= 10:\n    discount()\n")
        self.assertEqual(capture_diff(self.root).total_files, 0)
        self.assertFalse(attachment_sources((attachment,))[attachment.excerpt_sha256])
        self.path.unlink()
        self.assertFalse(attachment_sources((attachment,))[attachment.excerpt_sha256])

    async def test_non_git_directory_is_explicitly_unavailable(self) -> None:
        with (
            TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "Non-Git"),
        ):
            capture_diff(Path(directory))

    async def test_archived_findings_and_attachment_provenance_survive_resume(
        self,
    ) -> None:
        self.changed_scope()
        snapshot = capture_diff(self.root)
        review_entry = completed_review(snapshot)
        chat = self.chat()
        chat.state = ConversationState.model_validate(
            {**chat.state.model_dump(), "entries": (review_entry,)}
        )
        with (
            TemporaryDirectory() as directory,
            SQLiteConversationStore(
                Path(directory) / "sessions", chat.state.session_id, self.root
            ) as store,
        ):
            store.save(chat.state)
            working = store.load_working()
            assert isinstance(working, WorkingConversationState)
            findings = retained_findings(working.entries, store.load_working_entry)
            assert review_entry.review_result is not None
            self.assertEqual(
                findings[0].finding.finding_id,
                review_entry.review_result.verdict.findings[0].finding_id,
            )
            resumed_chat = ConversationController(
                working,
                chat.cassette,
                store.save_working,
                load_entry=store.load_working_entry,
            )
            commands = DiffCommands(resumed_chat, lambda event: None)
            await commands.execute("/diff findings")
            feedback = await commands.execute(
                "/diff feedback " + findings[0].key + " Check this carefully"
            )
            assert feedback is not None
            resumed_chat.submit(
                feedback + attachment_suffix(commands.attachments),
                diff_attachments=commands.attachments,
            )
            resumed = store.load_working()
            linked = retained_findings(resumed.entries, store.load_working_entry)
            self.assertEqual(linked[0].correction_positions, (1,))
            self.assertEqual(resumed.entries[1].diff_attachments, commands.attachments)
            self.assertEqual(linked[0].disposition, "upheld; required correction")

    async def test_typed_fix_rejection_retains_command_and_frozen_feedback(
        self,
    ) -> None:
        self.changed_scope()
        entry = completed_review(capture_diff(self.root))
        chat = self.chat()
        chat.state = ConversationState.model_validate(
            {**chat.state.model_dump(), "entries": (entry,)}
        )
        chat.pending_limits = PendingTextLimits(max_bytes=4000)
        chat.submit("x" * 4000)
        key = retained_findings(chat.state.entries)[0].key
        with create_pipe_input() as input:
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                command = "/diff fix " + key
                ui.editor.insert_text(command)
                ui.send()
                await until(lambda: not ui.sending)
                self.assertEqual(ui.editor.text, command)
                self.assertEqual(len(chat.state.entries), 2)
                self.assertEqual(len(ui.diff_attachments), 1)
                self.assertIn("Pending text", ui.notice)
                # Repeat the rejected request without duplicating source provenance.
                ui.send()
                await until(lambda: not ui.sending)
                self.assertEqual(len(ui.diff_attachments), 1)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_plain_json_commands_expose_same_snapshot_rows_and_findings(
        self,
    ) -> None:
        self.changed_scope()
        chat = self.chat()
        events: list[dict[str, object]] = []
        commands = DiffCommands(chat, events.append)
        await commands.execute("/diff")
        expected = capture_diff(self.root)
        self.assertEqual(events[-1]["snapshot"], expected.model_dump(mode="json"))
        await commands.execute("/diff lines pricing.py 0")
        self.assertEqual(
            events[-1]["rows"],
            [r.model_dump(mode="json") for r in patch_lines(expected.scope.files[0])],
        )
        before = chat.state
        row = next(
            i + 1
            for i, r in enumerate(patch_lines(expected.scope.files[0]))
            if r.new == 1
        )
        await commands.execute(f"/diff attach pricing.py {row} {row}")
        self.assertIs(chat.state, before)
        self.assertEqual(len(commands.attachments), 1)
        await commands.execute("/diff remove 1")
        self.assertEqual(commands.attachments, ())
        with self.assertRaises(ValueError):
            await commands.execute("/diff attach pricing.py 0 99")

    async def test_unmapped_locations_and_partial_views_never_invent_coordinates(
        self,
    ) -> None:
        self.changed_scope()
        snapshot = capture_diff(self.root)
        entry = completed_review(snapshot)
        assert entry.review_result is not None
        original = entry.review_result.verdict.findings[0]
        from mos_eisley.conversation_findings import finding_location

        for location in (
            "pricing.py:999",
            "elsewhere.py:1",
            "pricing.py:2",
            "pricing.py:2-1",
            "pricing.py:1 extra",
        ):
            finding = Finding.model_validate(
                {**original.model_dump(), "location": location}
            )
            self.assertIsNone(finding_location(finding, snapshot))
        with create_pipe_input() as input:
            ui = ConversationTUI(self.chat(), input=input, output=DummyOutput())
            ui.diff_refresh.snapshot = snapshot
            ui.render_diff()
            self.assertIn("pricing.py", ui.diff_pane.text)
            ui.emit(
                {
                    "type": "conversation.diff_finding_source",
                    "finding": retained_findings((entry,))[0].model_dump(mode="json"),
                    "snapshot": snapshot.model_dump(mode="json"),
                }
            )
            self.assertIn("Historical finding", ui.diff_pane.text)
            self.assertIn(
                "+if quantity > 10", ui.diff_pane.buffer.document.current_line
            )

    async def test_live_refresh_preserves_selected_path_when_earlier_file_added(
        self,
    ) -> None:
        self.changed_scope()
        with create_pipe_input() as input:
            ui = ConversationTUI(self.chat(), input=input, output=DummyOutput())
            ui.diff_refresh.snapshot = capture_diff(self.root)
            ui.render_diff()
            self.assertEqual(ui.diff_selected_path, "pricing.py")
            (self.root / "aaa.py").write_text("new\n")
            ui.diff_refresh.snapshot = capture_diff(self.root)
            ui.render_diff()
            self.assertEqual(ui.diff_selected_path, "pricing.py")
            self.assertEqual(ui.diff_file, 1)

    async def test_findings_dispositions_stale_sources_and_no_false_resolution(
        self,
    ) -> None:
        self.changed_scope()
        snapshot = capture_diff(self.root)
        upheld, rejected = (
            completed_review(snapshot),
            completed_review(snapshot, upheld=False),
        )
        views = retained_findings((upheld, rejected))
        self.assertEqual(len(views), 2)
        self.assertFalse(views[0].stale)
        self.assertEqual((views[0].path, views[0].start), ("pricing.py", 1))
        self.assertEqual(views[0].disposition, "upheld; required correction")
        self.assertEqual(views[1].disposition, "not upheld")
        self.path.write_text("corrected source\n")
        stale = retained_findings((upheld, rejected))
        self.assertTrue(all(f.stale for f in stale))
        self.assertTrue(
            all("resolution requires independent" in f.describe() for f in stale)
        )
        self.path.unlink()
        self.assertTrue(retained_findings((upheld,))[0].stale)

    async def test_findings_navigation_feedback_and_fix_use_exact_retained_keys(
        self,
    ) -> None:
        self.changed_scope()
        chat = self.chat()
        entry = completed_review(capture_diff(self.root))
        chat.state = ConversationState.model_validate(
            {**chat.state.model_dump(), "entries": (entry,)}
        )
        events: list[dict[str, object]] = []
        commands = DiffCommands(chat, events.append)
        await commands.execute("/diff findings")
        key = commands.findings[0].key
        before = chat.state
        self.assertIsNone(await commands.execute(f"/diff finding {key}"))
        self.assertEqual(events[-1]["type"], "conversation.diff_finding_source")
        self.assertIs(chat.state, before)
        text = await commands.execute(f"/diff feedback {key} Explain this boundary")
        self.assertIn("Explain this boundary", text or "")
        self.assertEqual(
            commands.attachments[0].finding_id, commands.findings[0].finding.finding_id
        )
        commands.attachments = ()
        fix = await commands.execute(f"/diff fix {key}")
        self.assertIn("plan/test", fix or "")
        self.assertIs(chat.state, before)
        self.path.write_text("concurrent edit\n")
        with self.assertRaisesRegex(ValueError, "Stale"):
            await commands.execute(f"/diff fix {key}")

    async def test_both_stores_retain_admitted_attachment_and_correction_link(
        self,
    ) -> None:
        self.changed_scope()
        snapshot = capture_diff(self.root)
        row = next(
            i + 1
            for i, r in enumerate(patch_lines(snapshot.scope.files[0]))
            if r.new == 1
        )
        attachment = attach_lines(snapshot, "pricing.py", row, row)
        for store_type in (ConversationStore, SQLiteConversationStore):
            with (
                self.subTest(store=store_type.__name__),
                TemporaryDirectory() as directory,
            ):
                chat = self.chat()
                with store_type(
                    Path(directory) / "sessions", chat.state.session_id, self.root
                ) as store:
                    store.save(chat.state)
                    chat.save = store.save
                    chat.submit(
                        "Explain" + attachment_suffix((attachment,)),
                        diff_attachments=(attachment,),
                    )
                    loaded = store.load()
                    self.assertEqual(loaded.entries[0].diff_attachments, (attachment,))
                    self.assertTrue(
                        loaded.entries[0].text.endswith(
                            attachment_suffix((attachment,))
                        )
                    )
                self.assertEqual(
                    json.loads(loaded.model_dump_json())["entries"][0][
                        "diff_attachments"
                    ][0]["excerpt"],
                    attachment.excerpt,
                )

    async def test_refresh_coalesces_and_rejects_obsolete_workspace_results(
        self,
    ) -> None:
        self.changed_scope()
        snapshot = capture_diff(self.root)
        started, release = threading.Event(), threading.Event()
        calls: list[Path] = []
        published: list[str] = []
        workspace = self.root

        def reader(path: Path, offset: int) -> DiffSnapshot:
            calls.append(path)
            started.set()
            release.wait(3)
            if path != self.root:
                raise ValueError("new workspace unavailable")
            return snapshot

        refresh = DiffRefresh(lambda: published.append("published"), lambda: workspace)
        with patch("mos_eisley.conversation_diff.capture_diff", side_effect=reader):
            refresh.request()
            await asyncio.to_thread(started.wait, 2)
            for _ in range(20):
                refresh.request(replace=True)
            workspace = self.root / "other"
            refresh.request(replace=True)
            release.set()
            await until(lambda: not refresh.loading)
            self.assertIsNone(refresh.snapshot)
            self.assertEqual(len(calls), 2)
            self.assertEqual(published, ["published"])
            self.assertIn("new workspace", refresh.error or "")
        refresh.close()

    async def test_stop_remains_responsive_during_plain_diff_read(self) -> None:
        self.changed_scope()
        started, release = threading.Event(), threading.Event()
        snapshot = capture_diff(self.root)

        def reader(path: Path, offset: int) -> DiffSnapshot:
            started.set()
            release.wait(3)
            return snapshot

        chat = self.chat()
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        events: list[dict[str, object]] = []
        with patch(
            "mos_eisley.conversation_diff_commands.capture_diff", side_effect=reader
        ):
            task = asyncio.create_task(terminal(chat, queue, events.append))
            queue.put_nowait("/diff")
            await asyncio.to_thread(started.wait, 2)
            queue.put_nowait("/quit")
            await asyncio.wait_for(task, 1)
            release.set()
            self.assertFalse(any(e["type"] == "conversation.diff" for e in events))
        self.assertEqual(chat.state.entries, ())

    async def test_tui_draft_focus_attachment_refresh_rejection_retry_and_close(
        self,
    ) -> None:
        self.changed_scope()
        with create_pipe_input() as input:
            chat = self.chat()
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                ui.editor.insert_text("Explain selected lines")
                ui.toggle_diff()
                await until(lambda: ui.diff_refresh.snapshot is not None)
                self.assertEqual(ui.editor.text, "Explain selected lines")
                snapshot = ui.diff_refresh.snapshot
                assert snapshot is not None
                row = next(
                    i
                    for i, r in enumerate(patch_lines(snapshot.scope.files[0]))
                    if r.new == 1
                )
                ui.diff_pane.buffer.cursor_position = (
                    ui.diff_pane.buffer.document.translate_row_col_to_index(
                        ui.diff_patch_header_rows + row, 0
                    )
                )
                input.send_text("\x1b[23~")  # F11
                await until(lambda: bool(ui.diff_attachments))
                frozen = ui.diff_attachments
                self.path.write_text("changed externally\n")
                ui.diff_refresh.request(replace=True)
                await until(lambda: "source changed" in ui.attachment_preview())
                self.assertEqual(ui.diff_attachments, frozen)
                chat.pending_limits = PendingTextLimits(max_bytes=4000)
                chat.submit("x" * 4000)
                ui.app.layout.focus(ui.editor_control)
                ui.send(literal=True)
                await until(lambda: not ui.sending)
                self.assertEqual(ui.editor.text, "Explain selected lines")
                self.assertEqual(ui.diff_attachments, frozen)
                self.assertIn("Pending text", ui.notice)
                # Removing the budget barrier admits the same frozen source, even stale.
                chat.pending_limits = None
                ui.send(literal=True)
                await until(lambda: not ui.sending and ui.editor.text == "")
                self.assertEqual(chat.state.entries[-1].diff_attachments, frozen)
                self.assertIn("Untrusted frozen source", chat.state.entries[-1].text)
                ui.toggle_diff()
                self.assertFalse(ui.diff_visible)
                self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_tui_failure_is_explicit_and_keeps_previous_snapshot_and_draft(
        self,
    ) -> None:
        self.changed_scope()
        with create_pipe_input() as input:
            ui = ConversationTUI(self.chat(), input=input, output=DummyOutput())
            ui.editor.insert_text("unsent")
            ui.diff_refresh.snapshot = capture_diff(self.root)
            ui.render_diff()
            with patch(
                "mos_eisley.conversation_diff.capture_diff",
                side_effect=ValueError("unsafe configuration"),
            ):
                ui.diff_refresh.request()
                assert ui.diff_refresh.task is not None
                await ui.diff_refresh.task
            self.assertIn("STALE: refresh failed", ui.diff_pane.text)
            self.assertEqual(ui.editor.text, "unsent")
            ui.diff_refresh.close()
