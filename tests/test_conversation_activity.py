"""Operation lifecycle and passive UI updates preserve the user's work."""

import asyncio
from unittest import IsolatedAsyncioTestCase, TestCase

from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from test_conversation_tui import controller, until

from mos_eisley.conversation_activity import ConversationActivity
from mos_eisley.conversation_git_review_tui import GitReviewTUI
from mos_eisley.conversation_state import ConversationEntry
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes


class ActivityTests(TestCase):
    def test_elapsed_stops_on_completion_and_restarts_for_next_operation(self) -> None:
        now = [100.0]
        activity = ConversationActivity(lambda: now[0])
        chat = controller()
        chat.state = chat.state.model_copy(
            update={
                "entries": (
                    ConversationEntry(
                        text="inspect", status="running", repository_inspection=True
                    ),
                    ConversationEntry(text="next", status="queued"),
                )
            }
        )
        activity.observe(chat.state)
        now[0] += 12
        self.assertIn("12s observed", activity.summary(120))
        self.assertIn("1 queued", activity.summary(120))
        self.assertIn("no writes", activity.details())
        chat.state = chat.state.model_copy(
            update={
                "entries": (
                    chat.state.entries[0].model_copy(update={"status": "failed"}),
                    chat.state.entries[1],
                )
            }
        )
        activity.observe(chat.state)
        now[0] += 90
        self.assertIn("Failed", activity.summary(120))
        self.assertIn("12s observed", activity.summary(120))
        chat.state = chat.state.model_copy(
            update={
                "entries": (
                    chat.state.entries[0],
                    chat.state.entries[1].model_copy(update={"status": "running"}),
                )
            }
        )
        activity.observe(chat.state)
        self.assertIn("0s observed", activity.summary(120))
        self.assertIn("Message [1]", activity.details())

    def test_cold_resume_does_not_invent_elapsed_or_active_calls(self) -> None:
        chat = controller()
        chat.state = chat.state.model_copy(
            update={
                "entries": (
                    ConversationEntry(text="prior", status="interrupted"),
                    ConversationEntry(text="next", status="queued"),
                )
            }
        )
        activity = ConversationActivity()
        activity.observe(chat.state)
        self.assertIn("Queued", activity.summary(80))
        self.assertNotIn("observed", activity.summary(80))
        self.assertIn("No active tool access", activity.details())

    def test_error_is_sanitized_bounded_and_survives_routine_updates(self) -> None:
        activity = ConversationActivity()
        self.assertTrue(
            activity.receive(
                {"type": "conversation.error", "text": "bad\x1b[2J\n" * 900}
            )
        )
        error = activity.error
        assert error is not None
        self.assertLessEqual(len(error[0]), 1200)
        self.assertNotIn("\x1b", activity.expanded_text())
        self.assertNotIn("\n", error[0])
        self.assertFalse(
            activity.receive({"type": "conversation.update", "text": "ready"})
        )
        self.assertIn(
            "failed messages are not retried automatically", activity.expanded_text()
        )
        self.assertIn("Ctrl-T", activity.error_text(40))
        self.assertEqual(activity.notice_text(error[0][:400]), "")
        self.assertEqual(activity.notice_text("A later update"), "A later update")


class ActivityKeyboardTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.loop_errors: list[dict[str, object]] = []
        asyncio.get_running_loop().set_exception_handler(
            lambda loop, context: self.loop_errors.append(context)
        )

    async def asyncTearDown(self) -> None:
        self.assertEqual(self.loop_errors, [])

    async def test_updates_and_expansion_preserve_draft_focus_and_browsing(
        self,
    ) -> None:
        for kind in (ConversationTUI, GitReviewTUI):
            with self.subTest(renderer=kind.__name__), create_pipe_input() as input:
                chat = controller()
                chat.submit("Remember that the fixture boundary is ten.")
                await chat.step()
                chat.state = chat.state.model_copy(
                    update={
                        "entries": (
                            chat.state.entries[0].model_copy(
                                update={"answer": "line\n" * 80}
                            ),
                        )
                    }
                )
                ui = kind(chat, input=input, output=DummyOutput())
                ui.editor.set_document(Document("Unsent\nmultiline draft", 6))
                ui.transcript.buffer.set_document(
                    Document(ui.transcript.text, 25), bypass_readonly=True
                )
                before = canonical_bytes(chat.state)
                task = asyncio.create_task(ui.run())
                try:
                    await until(lambda ui=ui: ui.app.is_running)
                    input.send_text("\x14")
                    await until(lambda ui=ui: ui.activity.expanded)
                    ui.emit(
                        {
                            "type": "conversation.error",
                            "text": "Context budget exceeded. Message remains queued.",
                        }
                    )
                    ui.emit(
                        {
                            "type": "conversation.update",
                            "text": "A later informational update",
                        }
                    )
                    ui.refresh()
                    await asyncio.sleep(1.1)  # Include a timer redraw.
                    self.assertEqual(
                        ui.editor.document, Document("Unsent\nmultiline draft", 6)
                    )
                    self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
                    self.assertEqual(ui.transcript.buffer.cursor_position, 25)
                    self.assertEqual(canonical_bytes(chat.state), before)
                    self.assertTrue(ui.queue.empty())
                    self.assertIsNotNone(ui.activity.error)
                    self.assertIn("Context budget", ui.activity.detail_view.text)
                    input.send_text("\x1b\x1b[B")
                    await until(
                        lambda ui=ui: ui.activity.detail_view.buffer.cursor_position > 0
                    )
                    self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
                    scroll = ui.transcript.window.vertical_scroll
                    chat.submit("Later queued work")
                    ui.emit({"type": "message.queued", "text": "Later queued work"})
                    await asyncio.sleep(0.1)
                    self.assertEqual(ui.transcript.buffer.cursor_position, 25)
                    self.assertEqual(ui.transcript.window.vertical_scroll, scroll)
                    self.assertEqual(
                        ui.editor.document, Document("Unsent\nmultiline draft", 6)
                    )
                    input.send_text("\x19")
                    await until(lambda ui=ui: ui.activity.error is None)
                    input.send_text("\x14")
                    await until(lambda ui=ui: not ui.activity.expanded)
                    self.assertEqual(
                        ui.editor.document, Document("Unsent\nmultiline draft", 6)
                    )
                finally:
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)
