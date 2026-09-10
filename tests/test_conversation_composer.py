"""Multiline dispatch, unsent-data isolation, paste bounds and real terminal input."""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import (
    DEMO_PROMPTS,
    MULTILINE_PROMPT,
    _input_reader,  # pyright: ignore[reportPrivateUsage]
    demo_cassette,
    terminal,
)
from mos_eisley.conversation_composer import ConversationComposer
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import ModelRequest, ModelResponse
from mos_eisley.demo import demo_inputs


class ComposerTerminalTests(IsolatedAsyncioTestCase):
    def controller(
        self,
        *,
        multiline: bool = False,
        save: Callable[[ConversationState], None] = lambda state: None,
    ) -> ConversationController:
        cassette = demo_cassette(multiline=multiline)
        return ConversationController(
            ConversationController.fresh(Path.cwd(), cassette), cassette, save
        )

    async def run_lines(
        self,
        controller: ConversationController,
        *lines: str | Exception | None,
        packet: ConversationReviewPacket | None = None,
    ) -> list[dict[str, object]]:
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        for line in lines:
            queue.put_nowait(line)
        events: list[dict[str, object]] = []
        await asyncio.wait_for(terminal(controller, queue, events.append, packet), 3)
        return events

    async def test_multiline_exact_request_and_contextual_followup(self) -> None:
        controller = self.controller(multiline=True)
        events = await self.run_lines(
            controller,
            "/compose",
            *MULTILINE_PROMPT.split("\n"),
            "/send",
            DEMO_PROMPTS[1],
            None,
        )
        self.assertEqual(controller.state.entries[0].text, MULTILINE_PROMPT)
        self.assertEqual(
            controller.state.entries[1].answer, "You gave me a boundary of ten."
        )
        self.assertEqual(controller.state.exchanges_consumed, 2)
        self.assertEqual(sum(e["type"] == "composer.sent" for e in events), 1)

    async def test_unsent_draft_never_reaches_store_events_or_dispatch(self) -> None:
        for ending in (None, "/quit", "/stop", "/discard"):
            with self.subTest(ending=ending):
                saved: list[ConversationState] = []
                controller = self.controller(save=saved.append)
                events = await self.run_lines(
                    controller, "/compose", "PRIVATE UNSENT TEXT", ending, None
                )
                self.assertEqual(controller.state.entries, ())
                self.assertEqual(controller.state.exchanges_consumed, 0)
                self.assertNotIn("PRIVATE UNSENT TEXT", repr(saved) + repr(events))
                self.assertEqual(
                    sum(e["type"] == "composer.discarded" for e in events), 1
                )

    async def test_drafting_does_not_resume_a_saved_queue(self) -> None:
        controller = self.controller()
        controller.submit(DEMO_PROMPTS[0])
        await self.run_lines(controller, "/compose", "unsent", "/discard", None)
        self.assertEqual(controller.state.entries[0].status, "queued")
        self.assertEqual(controller.state.exchanges_consumed, 0)

    async def test_commands_and_review_intent_inside_draft_stay_literal(self) -> None:
        brief, cassette = demo_inputs()
        packet = ConversationReviewPacket(brief=brief, cassette=cassette)
        for text in (
            "/review",
            "Review this change.",
            "//quit",
            "//send",
            "///path",
            "/continue",
        ):
            with self.subTest(text=text):
                controller = self.controller()
                with patch("mos_eisley.conversation.run_conversation_review") as review:
                    await self.run_lines(
                        controller, "/compose", text, "/send", None, packet=packet
                    )
                review.assert_not_called()
                self.assertEqual(
                    controller.state.entries[0].text,
                    text[1:] if text.startswith("//") else text,
                )
                self.assertIsNone(controller.state.entries[0].review_packet)

    async def test_empty_duplicate_and_outside_commands_preserve_draft(self) -> None:
        controller = self.controller()
        events = await self.run_lines(
            controller,
            "/send",
            "/discard",
            "/compose",
            "/send",
            "/compose",
            DEMO_PROMPTS[0],
            "/send",
            None,
        )
        self.assertEqual(sum(e["type"] == "composer.error" for e in events), 4)
        self.assertEqual(controller.state.entries[0].status, "completed")

    async def test_oversize_paste_cannot_submit_a_truncated_message(self) -> None:
        for lines in (("x" * 4000, "y" * 4000), ("",) * 257):
            with self.subTest(length=len(lines)):
                controller = self.controller()
                events = await self.run_lines(
                    controller,
                    "/compose",
                    *lines,
                    "/send",
                    DEMO_PROMPTS[0],
                    "/send",
                    "/discard",
                    "/compose",
                    DEMO_PROMPTS[0],
                    "/send",
                    None,
                )
                self.assertEqual(len(controller.state.entries), 1)
                self.assertEqual(controller.state.entries[0].status, "completed")
                self.assertEqual(sum(e["type"] == "composer.sent" for e in events), 1)

    async def test_capacity_rejection_keeps_draft_until_explicit_discard(self) -> None:
        controller = self.controller()
        for _ in range(16):
            controller.submit("saved queue")
        events = await self.run_lines(
            controller, "/compose", "still unsent", "/send", "/discard", None
        )
        self.assertEqual(controller.state.exchanges_consumed, 0)
        self.assertIn("conversation.unavailable", [e["type"] for e in events])
        self.assertIn("composer.discarded", [e["type"] for e in events])
        self.assertNotIn("composer.sent", [e["type"] for e in events])

    async def test_storage_failure_is_fatal_and_never_claims_sent(self) -> None:
        controller = self.controller()
        events: list[dict[str, object]] = []
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        for line in ("/compose", DEMO_PROMPTS[0], "/send", None):
            queue.put_nowait(line)
        with (
            patch.object(controller, "save", side_effect=ValueError("storage changed")),
            self.assertRaisesRegex(ValueError, "storage changed"),
        ):
            await terminal(controller, queue, events.append)
        self.assertEqual(controller.state.entries, ())
        self.assertNotIn("composer.sent", [e["type"] for e in events])
        self.assertNotIn("composer.error", [e["type"] for e in events])

    async def test_composing_during_active_request_and_stop_cancels_both(self) -> None:
        controller = self.controller()
        started, drafted = asyncio.Event(), asyncio.Event()

        class WaitingClient:
            async def complete(self, request: ModelRequest) -> ModelResponse:
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("cancelled client cannot complete")

        step = controller.step

        async def waiting_step(**kwargs: object) -> bool:
            return await step(WaitingClient())

        events: list[dict[str, object]] = []

        def emit(event: dict[str, object]) -> None:
            events.append(event)
            if event["type"] == "composer.updated":
                drafted.set()

        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait(DEMO_PROMPTS[0])
        with patch.object(controller, "step", side_effect=waiting_step):
            task = asyncio.create_task(terminal(controller, queue, emit))
            try:
                await asyncio.wait_for(started.wait(), 2)
                queue.put_nowait("/compose")
                queue.put_nowait("unsent while running")
                await asyncio.wait_for(drafted.wait(), 2)
                self.assertEqual(controller.state.entries[0].status, "running")
                self.assertEqual(len(controller.state.entries), 1)
                queue.put_nowait("/stop")
                queue.put_nowait(None)
                await asyncio.wait_for(task, 2)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(controller.state.entries[0].status, "cancelled")
        self.assertEqual(controller.state.exchanges_consumed, 1)
        self.assertIn("composer.discarded", [e["type"] for e in events])

    async def test_sent_draft_waits_for_active_reply_and_keeps_context(self) -> None:
        controller = self.controller(multiline=True)
        started, release, sent = asyncio.Event(), asyncio.Event(), asyncio.Event()

        class WaitingClient:
            async def complete(self, request: ModelRequest) -> ModelResponse:
                started.set()
                await release.wait()
                response = controller.cassette.exchanges[0].response
                assert response is not None
                return response

        step = controller.step

        async def waiting_step(*, on_started: Callable[[], None] | None = None) -> bool:
            return await step(
                WaitingClient() if controller.state.exchanges_consumed == 0 else None,
                on_started=on_started,
            )

        def emit(event: dict[str, object]) -> None:
            if event["type"] == "composer.sent":
                sent.set()

        controller.submit(MULTILINE_PROMPT)
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait("/continue")
        with patch.object(controller, "step", side_effect=waiting_step):
            task = asyncio.create_task(terminal(controller, queue, emit))
            try:
                await asyncio.wait_for(started.wait(), 2)
                for line in ("/compose", DEMO_PROMPTS[1], "/send"):
                    queue.put_nowait(line)
                await asyncio.wait_for(sent.wait(), 2)
                self.assertEqual(
                    [entry.status for entry in controller.state.entries],
                    ["running", "queued"],
                )
                self.assertEqual(controller.state.exchanges_consumed, 1)
                release.set()
                queue.put_nowait(None)
                await asyncio.wait_for(task, 2)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(
            controller.state.entries[1].answer, "You gave me a boundary of ten."
        )

    async def test_reader_backpressure_preserves_unicode_blank_lines_and_eof(
        self,
    ) -> None:
        read_fd, write_fd = os.pipe()
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue(maxsize=2)
        # Split a UTF-8 character over the reader's 4 KB boundary.
        source = (
            "x" * 4095 + "é\n" + "\n".join(f"line-{i}" for i in range(100)) + "\n\nlast"
        )
        os.write(write_fd, source.encode())
        os.close(write_fd)
        stop = _input_reader(read_fd, queue)
        received: list[str] = []
        try:
            while True:
                line = await asyncio.wait_for(queue.get(), 2)
                if line is None:
                    break
                self.assertIsInstance(line, str)
                assert isinstance(line, str)
                received.append(line)
        finally:
            stop()
            await asyncio.sleep(0)
            os.close(read_fd)
        self.assertEqual(received, source.split("\n"))

    async def test_invalid_or_oversize_reader_input_cannot_be_sent(self) -> None:
        for data in (b"\xff", b"x" * 8001 + b"\n/send\n", b"x" * 8001):
            with self.subTest(size=len(data)), TemporaryDirectory() as directory:
                path = Path(directory) / "input"
                path.write_bytes(data)
                queue: asyncio.Queue[str | Exception | None] = asyncio.Queue(maxsize=2)
                with path.open("rb") as stream:
                    stop = _input_reader(stream.fileno(), queue)
                    try:
                        self.assertIsInstance(
                            await asyncio.wait_for(queue.get(), 2), ValueError
                        )
                    finally:
                        stop()
                        await asyncio.sleep(0)


class ComposerCLITests(TestCase):
    def test_exact_draft_limit_and_whitespace_preservation(self) -> None:
        composer = ConversationComposer()
        composer.begin()
        composer.append("  é" + "x" * 7997)
        self.assertEqual(len(composer.message()), 8000)
        self.assertTrue(composer.message().startswith("  é"))
        composer.clear()
        composer.begin()
        composer.append(" first  ")
        composer.append("")
        composer.append(" last ")
        self.assertEqual(composer.message(), " first  \n\n last ")

    def test_real_multiline_demo_pipe_and_second_process_resume(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = root / "cassette.json"
            command = [sys.executable, "-m", "mos_eisley.cli"]
            subprocess.run(
                command
                + ["conversation-demo", "--multiline", "--output", str(cassette)],
                check=True,
                capture_output=True,
            )
            options = [
                "--cassette",
                str(cassette),
                "--storage",
                str(root / "sessions"),
                "--workspace",
                str(root),
                "--json",
            ]
            first = subprocess.run(
                command + ["chat", *options],
                input="/compose\n" + MULTILINE_PROMPT + "\n/send\n",
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            events = [json.loads(line) for line in first.stdout.splitlines()]
            session_id = events[-1]["session_id"]
            snapshot = json.loads(
                (root / "sessions" / f"{session_id}.json").read_text()
            )
            self.assertEqual(snapshot["state"]["entries"][0]["text"], MULTILINE_PROMPT)
            second = subprocess.run(
                command + ["resume", session_id, *options],
                input=DEMO_PROMPTS[1] + "\n",
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            self.assertIn("You gave me a boundary of ten.", second.stdout)

    def test_large_redirected_draft_is_one_message_and_control_output_is_escaped(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = root / "cassette.json"
            cassette.write_bytes(canonical_bytes(demo_cassette()))
            messages = root / "messages.txt"
            text = "\n".join(["line"] * 100 + ["\x1b[31mcode"])
            messages.write_text("/compose\n" + text + "\n/send\n")
            with messages.open() as stream:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "chat",
                        "--cassette",
                        str(cassette),
                        "--storage",
                        str(root / "sessions"),
                    ],
                    stdin=stream,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=True,
                )
            self.assertNotIn("\x1b", result.stdout)
            self.assertIn("\\u001b", result.stdout)
            self.assertIn("composer.sent", result.stdout)
            path = next((root / "sessions").glob("*.json"))
            entries = json.loads(path.read_text())["state"]["entries"]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["text"], text)
