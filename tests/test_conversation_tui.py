"""Real keyboard editing, shared orchestration, paste isolation and terminal cleanup."""

import asyncio
import json
import os
import pty
import select
import subprocess
import sys
import termios
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, MULTILINE_PROMPT, demo_cassette
from mos_eisley.conversation_input import ConversationSubmission
from mos_eisley.conversation_review import (
    REVIEW_FOLLOWUP,
    ConversationReviewPacket,
    review_summary,
    run_conversation_review,
)
from mos_eisley.conversation_tui import ConversationTUI, EditorBuffer, display_text
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import ModelRequest, ModelResponse
from mos_eisley.demo import demo_inputs


async def until(predicate: Callable[[], bool]) -> None:
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.01)


def controller(*, multiline: bool = False) -> ConversationController:
    cassette = demo_cassette(multiline=multiline)
    return ConversationController(
        ConversationController.fresh(Path.cwd(), cassette), cassette, lambda state: None
    )


class TUITests(IsolatedAsyncioTestCase):
    async def test_full_session_rejects_review_without_losing_draft(self) -> None:
        chat = controller()
        for _ in range(16):
            chat.submit("saved pending message")
        brief, cassette = demo_inputs()
        packet = ConversationReviewPacket(brief=brief, cassette=cassette)
        with create_pipe_input() as input:
            ui = ConversationTUI(chat, packet, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("Review this change.\r")
                await until(lambda: "message limit" in ui.notice)
                self.assertEqual(ui.editor.text, "Review this change.")
                self.assertEqual(chat.state.exchanges_consumed, 0)
                self.assertEqual(len(chat.state.entries), 16)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_full_input_queue_retains_commands_and_stop_takes_priority(
        self,
    ) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(controller(), input=input, output=DummyOutput())
            for _ in range(32):
                ui.queue.put_nowait("/help")
            ui.editor.insert_text("/steer retained instruction")
            ui.send()
            self.assertEqual(ui.editor.text, "/steer retained instruction")
            self.assertIn("queue is full", ui.notice)
            self.assertTrue(ui.control("/stop", priority=True))
            self.assertEqual(ui.queue.qsize(), 1)
            self.assertEqual(ui.queue.get_nowait(), "/stop")
            self.assertEqual(ui.editor.text, "")

    async def test_closed_input_exits_without_saving_an_unsent_draft(self) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(controller(), input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("unsent before input closed")
                await until(lambda: ui.editor.text == "unsent before input closed")
                input.close()
                await asyncio.wait_for(task, 3)
                self.assertEqual(ui.controller.state.entries, ())
                self.assertEqual(ui.editor.text, "")
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_edit_multiline_paste_and_contextual_followup(self) -> None:
        chat = controller(multiline=True)
        with create_pipe_input() as input:
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                # Bracketed paste is inserted, never dispatched automatically.
                input.send_text(
                    "\x1b[200~" + MULTILINE_PROMPT.replace("10", "11") + "\x1b[201~"
                )
                await until(lambda: "11" in ui.editor.text)
                self.assertEqual(chat.state.entries, ())
                # Up to the preceding line, End, Backspace, type 0.
                input.send_text("\x1b[A\x1b[F\x7f0")
                await until(lambda: ui.editor.text == MULTILINE_PROMPT)
                input.send_text("\r")
                await until(
                    lambda: (
                        len(chat.state.entries) == 1
                        and chat.state.entries[0].status == "completed"
                    )
                )
                self.assertEqual(ui.editor.text, "")
                input.send_text(DEMO_PROMPTS[1] + "\r")
                await until(
                    lambda: (
                        len(chat.state.entries) == 2
                        and chat.state.entries[1].status == "completed"
                    )
                )
                # The controller publishes completion before the terminal handles
                # its event and refreshes the transcript.
                await until(
                    lambda: "You gave me a boundary of ten." in ui.transcript.text
                )
                self.assertIn("You gave me a boundary of ten.", ui.transcript.text)
                self.assertIn("2/2 attempts", ui.status())
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_alt_enter_newline_and_focus_controls(self) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(controller(), input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("first\x1b\rsecond")
                await until(lambda: ui.editor.text == "first\nsecond")
                self.assertEqual(ui.controller.state.entries, ())
                input.send_text("\t")
                await until(lambda: ui.app.layout.has_focus(ui.transcript))
                input.send_text("\x1b[5~\x1b[6~\t")
                await until(lambda: ui.app.layout.has_focus(ui.editor_control))
                input.send_text("\x15")
                await until(lambda: ui.editor.text == "")
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_pasted_slash_command_is_literal_even_when_single_line(self) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(controller(), input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("\x1b[200~/quit\x1b[201~")
                await until(lambda: ui.editor.text == "/quit")
                self.assertFalse(task.done())
                self.assertEqual(ui.controller.state.entries, ())
                input.send_text("\r")
                await until(lambda: len(ui.controller.state.entries) == 1)
                self.assertEqual(ui.controller.state.entries[0].text, "/quit")
                self.assertIsNone(ui.controller.state.entries[0].review_packet)
                self.assertFalse(task.done())
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_overflow_cannot_submit_a_partial_paste(self) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(controller(), input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("retained\x1b[200~" + "x" * 8001 + "\x1b[201~")
                await until(lambda: ui.editor.invalid)
                self.assertEqual(ui.editor.text, "retained")
                ui.send()
                self.assertEqual(ui.controller.state.entries, ())
                input.send_text("\x15" + DEMO_PROMPTS[0] + "\r")
                await until(
                    lambda: (
                        len(ui.controller.state.entries) == 1
                        and ui.controller.state.entries[0].status == "completed"
                    )
                )
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_resume_stays_paused_until_f4(self) -> None:
        chat = controller()
        chat.submit(DEMO_PROMPTS[0])
        with create_pipe_input() as input:
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("unsent draft")
                await until(lambda: ui.editor.text == "unsent draft")
                self.assertEqual(chat.state.exchanges_consumed, 0)
                input.send_text("\x1bOS")
                await until(lambda: chat.state.entries[0].status == "completed")
                self.assertEqual(ui.editor.text, "unsent draft")
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)
            self.assertEqual(ui.editor.text, "")
            self.assertNotIn("unsent draft", repr(chat.state))

    async def test_review_roundtrip_and_expandable_findings(self) -> None:
        brief, cassette = demo_inputs()
        packet = ConversationReviewPacket(brief=brief, cassette=cassette)
        recording = demo_cassette(review_summary(await run_conversation_review(packet)))
        chat = ConversationController(
            ConversationController.fresh(Path.cwd(), recording),
            recording,
            lambda state: None,
        )
        with create_pipe_input() as input:
            ui = ConversationTUI(chat, packet, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                for text, count in (
                    (DEMO_PROMPTS[0], 1),
                    ("/review", 2),
                    (REVIEW_FOLLOWUP, 3),
                ):
                    input.send_text(text + "\r")
                    await until(
                        lambda count=count: (
                            len(chat.state.entries) == count
                            and chat.state.entries[-1].status == "completed"
                        )
                    )
                input.send_text("\x1bOR")
                await until(lambda: ui.details)
                self.assertIn("Evidence:", ui.transcript.text)
                self.assertIn("Restore quantity >= 10.", ui.transcript.text)
                self.assertEqual(chat.state.exchanges_consumed, 2)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_rejected_submission_retains_editor_text(self) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(controller(), input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("Review this change.\r")
                await until(lambda: "--review-packet" in ui.notice)
                self.assertEqual(ui.editor.text, "Review this change.")
                self.assertEqual(ui.controller.state.entries, ())
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_stop_and_quit_cancel_children_and_preserve_only_submitted_input(
        self,
    ) -> None:
        for stop in (True, False):
            with self.subTest(stop=stop):
                await self.check_stop(stop)

    async def check_stop(self, stop: bool) -> None:
        with create_pipe_input() as input:
            chat = controller()
            started = asyncio.Event()

            class WaitingClient:
                async def complete(self, request: ModelRequest) -> ModelResponse:
                    started.set()
                    await asyncio.Event().wait()
                    raise AssertionError("cancelled client cannot complete")

            step = chat.step

            async def waiting_step(
                *, on_started: Callable[[], None] | None = None
            ) -> bool:
                return await step(WaitingClient(), on_started=on_started)

            with patch.object(chat, "step", side_effect=waiting_step):
                ui = ConversationTUI(chat, input=input, output=DummyOutput())
                task = asyncio.create_task(ui.run())
                try:
                    await until(lambda: ui.app.is_running)
                    input.send_text(DEMO_PROMPTS[0] + "\r")
                    await asyncio.wait_for(started.wait(), 2)
                    input.send_text(DEMO_PROMPTS[1] + "\r")
                    await until(lambda: len(chat.state.entries) == 2 and not ui.sending)
                    input.send_text("PRIVATE UNSENT")
                    await until(lambda: ui.editor.text == "PRIVATE UNSENT")
                    input.send_text("\x03" if stop else "\x04")
                    if stop:
                        await until(lambda: chat.state.entries[0].status == "cancelled")
                        self.assertFalse(task.done())
                        self.assertEqual(ui.editor.text, "")
                        input.send_text("\x04")
                    await asyncio.wait_for(task, 3)
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            self.assertEqual(chat.state.entries[0].status, "cancelled")
            self.assertEqual(
                chat.state.entries[1].status, "cancelled" if stop else "queued"
            )
            self.assertEqual(chat.state.entries[1].steering_for, 0)
            self.assertNotIn("PRIVATE UNSENT", repr(chat.state))

    async def test_stop_before_submission_task_starts_does_not_send_later(self) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(controller(), input=input, output=DummyOutput())
            ui.editor.insert_text(DEMO_PROMPTS[0])
            ui.send()
            ui.control("/stop", priority=True)
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                self.assertFalse(ui.sending)
                self.assertEqual(ui.controller.state.entries, ())
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_storage_failure_exits_without_claiming_submission(self) -> None:
        chat = controller()
        with (
            create_pipe_input() as input,
            patch.object(chat, "save", side_effect=OSError("storage unavailable")),
        ):
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            await until(lambda: ui.app.is_running)
            input.send_text(DEMO_PROMPTS[0] + "\r")
            with self.assertRaisesRegex(OSError, "storage unavailable"):
                await asyncio.wait_for(task, 3)
            self.assertEqual(chat.state.entries, ())
            self.assertEqual(ui.editor.text, "")
            self.assertFalse(ui.app.is_running)

    async def test_cancelled_editor_handoff_never_dispatches(self) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(controller(), input=input, output=DummyOutput())
            accepted: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            accepted.cancel()
            ui.queue.put_nowait(ConversationSubmission(DEMO_PROMPTS[0], True, accepted))
            ui.queue.put_nowait("/quit")
            await asyncio.wait_for(ui.run(), 3)
            self.assertEqual(ui.controller.state.entries, ())


class TUIContractTests(TestCase):
    def test_editor_history_bounds_and_control_rendering(self) -> None:
        notices: list[str] = []
        editor = EditorBuffer(notices.append, lambda: False)
        for _ in range(40):
            editor.save_to_undo_stack()
            editor.insert_text("x")
        self.assertLessEqual(len(editor.undo_documents), 32)
        editor.undo()
        self.assertEqual(len(editor.text), 39)
        editor.redo()
        self.assertEqual(len(editor.text), 40)
        editor.set_document(Document("\n" * 256))
        self.assertTrue(editor.invalid)
        self.assertEqual(len(editor.text), 40)
        editor.clear()
        self.assertEqual(editor.undo_documents, [])
        self.assertEqual(editor.redo_documents, [])
        self.assertEqual(
            display_text("hello\n\x1b[31m\u202e"), "hello\n\\u001b[31m\\u202e"
        )

    def test_tui_requires_a_terminal_before_creating_storage(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "chat",
                    "--tui",
                    "--cassette",
                    str(root / "missing.json"),
                    "--storage",
                    str(root / "sessions"),
                ],
                input="",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("--tui requires terminal", result.stderr)
            self.assertFalse((root / "sessions").exists())

    def test_real_terminal_defaults_to_tui_and_restores_terminal_modes(self) -> None:
        for bare in (False, True):
            with self.subTest(bare=bare):
                self.check_real_terminal(bare=bare)

    def check_real_terminal(self, *, bare: bool) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = root / "cassette.json"
            cassette.write_bytes(canonical_bytes(demo_cassette()))
            master, slave = pty.openpty()
            original = termios.tcgetattr(slave)
            arguments = (
                []
                if bare
                else [
                    "chat",
                    "--cassette",
                    str(cassette),
                    "--storage",
                    str(root / "sessions"),
                    "--workspace",
                    str(root),
                ]
            )
            process = subprocess.Popen(
                [sys.executable, "-m", "mos_eisley.cli", *arguments],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env={**os.environ, "TERM": "xterm-256color", "HOME": str(root)},
                start_new_session=True,
            )
            output = bytearray()
            storage = root / (".mos-eisley-sessions" if bare else "sessions")

            def answer_saved() -> bool:
                for path in storage.glob("*.json"):
                    entries = json.loads(path.read_bytes())["state"]["entries"]
                    if (
                        entries
                        and entries[0]["answer"] == "The fixture boundary is ten."
                    ):
                        return True
                return False

            def read_until(
                text: bytes, ready: Callable[[], bool] | None = None
            ) -> None:
                deadline = time.monotonic() + 10
                while text not in output or (ready is not None and not ready()):
                    if time.monotonic() >= deadline:
                        raise AssertionError(
                            "expected terminal output did not arrive: "
                            + repr(output[-5000:])
                        )
                    readable, _, _ = select.select([master], [], [], 0.1)
                    if readable:
                        data = os.read(master, 16384)
                        output.extend(data)
                        if b"\x1b[6n" in data:
                            os.write(master, b"\x1b[1;1R")

            try:
                read_until(b"\x1b[?1049h")
                read_until(b"Directory:")
                if bare:
                    # Startup details can exceed the live viewport. Scroll to the
                    # welcome notice instead of assuming it is initially visible.
                    os.write(master, b"\x1b[5~\x0c")
                    read_until(b"live conversations are not connected yet")
                    os.write(master, b"\t")
                os.write(master, (DEMO_PROMPTS[0] + "\r").encode())
                # A differential repaint can reuse old glyphs via cursor moves.
                # Request a full repaint before matching contiguous answer bytes.
                read_until(b"\x1b[?1049h", answer_saved)
                os.write(master, b"\x0c")
                read_until(b"The fixture boundary is ten.")
                os.write(master, b"\x04")
                read_until(b"conversation.saved")
                self.assertEqual(process.wait(timeout=5), 0)
                self.assertIn(b"\x1b[?1049l", output)
                restored = termios.tcgetattr(slave)
                # BSD marks retyping pending when canonical input is restored;
                # compare mode bits, excluding that kernel-maintained state flag.
                restored[3] &= ~getattr(termios, "PENDIN", 0)
                original[3] &= ~getattr(termios, "PENDIN", 0)
                self.assertEqual(restored, original)
                storage = root / (".mos-eisley-sessions" if bare else "sessions")
                self.assertEqual(len(list(storage.glob("*.json"))), 1)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                os.close(master)
                os.close(slave)
