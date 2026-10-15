"""Review inspection preserves exact identities without granting authority."""

import asyncio
import io
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase

import test_project_guidance_review as guidance_fixture
from prompt_toolkit.application import in_terminal
from prompt_toolkit.application.current import set_app
from prompt_toolkit.data_structures import Size
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from test_conversation_tui import controller, until
from test_review_controller import ControllerFixture

from mos_eisley.conversation_git_review_tui import GitReviewTUI
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_forget import MemoryForget
from mos_eisley.conversation_review import (
    ConversationLiveReviewPacket,
    ConversationReviewPacket,
)
from mos_eisley.conversation_review_companion import ReviewCompanion
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes
from mos_eisley.demo import demo_inputs
from mos_eisley.review_approval_terminal import TerminalReviewApproval


class CompanionTests(TestCase):
    def test_selected_live_packet_retains_every_exact_hash_and_full_brief(self) -> None:
        fixture = guidance_fixture.GuidedReviewTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        packet = ConversationLiveReviewPacket(
            brief=fixture.prepared.brief,
            prepared_sha256=fixture.prepared.sha256,
            configuration_sha256="1" * 64,
            campaign_seal_sha256="2" * 64,
            campaign_evidence_sha256="3" * 64,
            manifest_sha256="4" * 64,
            guidance_review=fixture.prepared,
        )
        before = canonical_bytes(packet)
        companion = ReviewCompanion(packet)
        companion.toggle()
        for value in (
            packet.prepared_sha256,
            packet.configuration_sha256,
            packet.campaign_seal_sha256,
            packet.campaign_evidence_sha256,
            packet.manifest_sha256,
            packet.brief.brief_id,
        ):
            self.assertIn(value, companion.details.text)
        self.assertIn("signed launch and phase approvals", companion.details.text)
        companion.close()
        self.assertEqual(canonical_bytes(packet), before)
        self.assertFalse(companion.visible)

    def test_preview_details_escape_untrusted_text_and_stale_receipts_are_labelled(
        self,
    ) -> None:
        companion = ReviewCompanion()
        receipt: dict[str, object] = {
            "type": "conversation.memory.replace.preview",
            "preview_sha256": "f" * 64,
            "scope": "project",
            "path": "/tmp/项目\x1b[2J\nfile",
            "after_text": "new\x1b[31m\u202e\nReason: forged",
        }
        companion.receive(receipt)
        self.assertNotIn("\x1b", companion.details.text)
        self.assertNotIn("\u202e", companion.details.text)
        self.assertIn("\\u001b", companion.details.text)
        self.assertIn("f" * 64, companion.details.text)
        self.assertIn("/memory apply-replace " + "f" * 64, companion.details.text)
        companion.receive({"type": "conversation.unavailable", "text": "changed"})
        self.assertIn("Historical preview", companion.heading(120))
        companion.receive(
            {"type": "conversation.memory.replace.discarded", "text": "discarded"}
        )
        self.assertIn("Discarded", companion.heading(120))
        self.assertNotIn("/memory apply-replace", companion.details.text)
        self.assertNotIn("f" * 64, companion.details.text)

    def test_missing_hash_is_not_repaired_or_exposed_as_an_apply_command(self) -> None:
        companion = ReviewCompanion()
        companion.receive(
            {"type": "conversation.memory.forget.preview", "text": "preview"}
        )
        self.assertIn("Incomplete receipt", companion.heading(120))
        self.assertNotIn("apply-forget", companion.details.text)


class NarrowOutput(DummyOutput):
    def get_size(self) -> Size:
        return Size(rows=24, columns=64)


class CompanionKeyboardTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.loop_errors: list[dict[str, object]] = []
        asyncio.get_running_loop().set_exception_handler(
            lambda loop, context: self.loop_errors.append(context)
        )

    async def asyncTearDown(self) -> None:
        self.assertEqual(self.loop_errors, [])

    async def test_companion_and_error_fit_a_narrow_terminal_without_hiding_composer(
        self,
    ) -> None:
        for kind in (ConversationTUI, GitReviewTUI):
            with self.subTest(renderer=kind.__name__), create_pipe_input() as input:
                ui = kind(controller(), input=input, output=NarrowOutput())
                draft = Document("retained\ndraft", 3)
                ui.editor.set_document(draft)
                ui.review_companion.toggle()
                ui.activity.expanded = True
                ui.emit({"type": "conversation.error", "text": "Request failed"})
                task = asyncio.create_task(ui.run())
                try:
                    await until(lambda ui=ui: ui.app.is_running)
                    await asyncio.sleep(0.1)
                    screen = ui.app.renderer.last_rendered_screen
                    assert screen is not None
                    self.assertIn(
                        ui.editor_control,
                        [window.content for window in ui.app.layout.visible_windows],
                    )
                    self.assertEqual(ui.editor.document, draft)
                    self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
                    with set_app(ui.app):
                        self.assertLessEqual(
                            ui.app.layout.container.preferred_height(64, 24).min, 24
                        )
                finally:
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)

    async def test_inspect_scroll_cancel_and_preview_discard_preserve_draft_and_focus(
        self,
    ) -> None:
        brief, cassette = demo_inputs()
        packet = ConversationReviewPacket(brief=brief, cassette=cassette)
        for kind in (ConversationTUI, GitReviewTUI):
            with (
                self.subTest(renderer=kind.__name__),
                TemporaryDirectory() as temporary,
                create_pipe_input() as input,
            ):
                chat = controller()
                store = MemoryStore(
                    Path(temporary) / "memory", Path(chat.state.workspace)
                )
                store.change(
                    "project",
                    "set",
                    text="Keep this. Remove exactly.\n" + "retained\n" * 80,
                )
                forget = MemoryForget(store)
                receipt = forget.command("/memory forget project Remove exactly.")
                assert receipt is not None
                before_file = store.path("project").read_bytes()
                before_state = canonical_bytes(chat.state)
                ui = kind(chat, packet, input=input, output=DummyOutput())
                draft = Document("Unsent\nmultiline draft", 9)
                ui.editor.set_document(draft)
                task = asyncio.create_task(ui.run())
                try:
                    await until(lambda ui=ui: ui.app.is_running)
                    input.send_text("\x0f")
                    await until(lambda ui=ui: ui.review_companion.visible)
                    self.assertIn(brief.brief_id, ui.review_companion.details.text)
                    input.send_text("\x1b\x1b[6~")
                    await until(
                        lambda ui=ui: (
                            ui.review_companion.details.buffer.cursor_position > 0
                        )
                    )
                    self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
                    self.assertEqual(ui.editor.document, draft)
                    input.send_text("\x07")
                    await until(lambda ui=ui: not ui.review_companion.visible)
                    ui.app.layout.focus(ui.transcript)
                    input.send_text("\x0f")
                    await until(lambda ui=ui: ui.review_companion.visible)
                    self.assertTrue(ui.app.layout.has_focus(ui.transcript))
                    input.send_text("\x07")
                    await until(lambda ui=ui: not ui.review_companion.visible)
                    self.assertTrue(ui.app.layout.has_focus(ui.transcript))
                    ui.app.layout.focus(ui.editor_control)
                    ui.emit(receipt)
                    self.assertTrue(ui.review_companion.visible)
                    self.assertIn(
                        str(receipt["preview_sha256"]), ui.review_companion.details.text
                    )
                    ui.emit({"type": "conversation.update", "text": "Routine update"})
                    self.assertEqual(ui.editor.document, draft)
                    self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
                    input.send_text("\x07")
                    await until(lambda ui=ui: not ui.review_companion.visible)
                    self.assertIsNotNone(forget.pending)
                    self.assertEqual(store.path("project").read_bytes(), before_file)
                    self.assertEqual(canonical_bytes(chat.state), before_state)
                    self.assertTrue(ui.queue.empty())
                    discarded = forget.command("/memory discard-forget")
                    assert discarded is not None
                    ui.emit(discarded)
                    self.assertIsNone(forget.pending)
                    self.assertEqual(ui.editor.document, draft)
                    self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
                    self.assertNotIn("apply-forget", ui.review_companion.details.text)
                finally:
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)


class CeremonySuspensionTests(ControllerFixture, IsolatedAsyncioTestCase):
    async def test_show_and_cancel_return_to_existing_conversation_draft_and_focus(
        self,
    ) -> None:
        for kind in (ConversationTUI, GitReviewTUI):
            with self.subTest(renderer=kind.__name__), create_pipe_input() as input:
                ui = kind(controller(), input=input, output=DummyOutput())
                draft = Document("Keep this unsent draft", 7)
                ui.editor.set_document(draft)
                task = asyncio.create_task(ui.run())
                answers = iter(("show", "cancel"))
                output = io.StringIO()

                async def read_line(
                    prompt: str, values: Iterator[str] = answers
                ) -> str:
                    return next(values)

                try:
                    await until(lambda ui=ui: ui.app.is_running)
                    with set_app(ui.app):
                        async with in_terminal():
                            result = await TerminalReviewApproval(
                                read_line, output
                            ).approve(self.controller.preview)
                    self.assertIsNone(result)
                    self.assertEqual(ui.editor.document, draft)
                    self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
                    self.assertTrue(ui.queue.empty())
                    self.assertEqual(self.controller.phase, "prepared")
                    self.assertEqual(self.base.ledger.snapshot().entries, 0)
                    self.assertIn("Action:", output.getvalue())
                    self.assertIn("Scope:", output.getvalue())
                    self.assertIn("Reason:", output.getvalue())
                    self.assertIn(self.controller.preview.sha256, output.getvalue())
                finally:
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)
