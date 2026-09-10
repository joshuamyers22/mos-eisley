"""Bound refinements, recovery context, frozen reviews and serialized requests."""

import asyncio
import json
import os
import selectors
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from mos_eisley.conversation import (
    ConversationController,
    ConversationEntry,
    ConversationState,
    context_for,
    conversation_config,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_review import REVIEW_PROMPT, ConversationReviewPacket
from mos_eisley.core.agent import AgentFailure, build_request
from mos_eisley.core.budget import resolve_budget
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest, ModelResponse, TextBlock, Turn, Usage
from mos_eisley.core.registry import fixture_registry
from mos_eisley.demo import demo_inputs
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.tools.none import NoToolsDispatcher

REFINEMENT = "Use eleven instead."


def recovery_cassette() -> AgentCassette:
    # Expected requests are explicit: unanswered original + refinement, followed
    # by that exact completed exchange and the next contextual question.
    exchanges = [demo_cassette().exchanges[0]]
    turns = (
        Turn(
            role="user",
            blocks=(TextBlock(text=DEMO_PROMPTS[0]), TextBlock(text=REFINEMENT)),
        ),
    )
    for followup in (False, True):
        if followup:
            turns += (Turn(role="user", blocks=(TextBlock(text=DEMO_PROMPTS[1]),)),)
        config = conversation_config(turns)
        resolved = fixture_registry().resolve(
            config.provider, config.model, config.effort
        )
        request = build_request(
            config,
            resolved,
            resolve_budget(resolved.spec, resolved.effort, config.budget),
            NoToolsDispatcher(),
            turns,
        )
        response = ModelResponse(
            turn=Turn(
                role="assistant",
                blocks=(TextBlock(text="The fixture boundary is eleven."),),
            ),
            stop_reason="end_turn",
            usage=Usage(input=100, output=30),
        )
        exchanges.append(
            AgentExchange(
                request_sha256=digest(canonical_bytes(request)), response=response
            )
        )
        turns += (response.turn,)
    return AgentCassette(exchanges=tuple(exchanges))


class WaitingClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.requests: list[ModelRequest] = []
        self.fail = fail

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        self.started.set()
        await self.release.wait()
        if self.fail:
            raise ValueError("recorded failure")
        response = demo_cassette().exchanges[0].response
        assert response is not None
        return response


def make_controller(cassette: AgentCassette | None = None) -> ConversationController:
    cassette = cassette or demo_cassette()
    return ConversationController(
        ConversationController.fresh(Path.cwd(), cassette),
        cassette,
        lambda state: None,
    )


class SteeringTests(IsolatedAsyncioTestCase):
    async def test_binding_and_dispatch_at_next_request_boundary(self) -> None:
        controller = make_controller()
        controller.submit(DEMO_PROMPTS[0])
        client = WaitingClient()
        task = asyncio.create_task(controller.step(client))
        try:
            await asyncio.wait_for(client.started.wait(), 2)
            original = canonical_bytes(client.requests[0])
            controller.steer(DEMO_PROMPTS[1])
            self.assertEqual(controller.state.entries[1].steering_for, 0)
            self.assertEqual(controller.state.entries[1].status, "queued")
            self.assertEqual(controller.state.exchanges_consumed, 1)
            self.assertEqual(canonical_bytes(client.requests[0]), original)
            with self.assertRaisesRegex(ValueError, "already active"):
                await controller.step()
            client.release.set()
            await task
            await controller.step()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(controller.state.entries[1].steering_for, 0)
        self.assertEqual(
            controller.state.entries[1].answer, "You gave me a boundary of ten."
        )
        self.assertEqual(len(client.requests), 1)

    async def test_ordinary_input_binds_only_when_submitted_during_chat(self) -> None:
        controller = make_controller()
        controller.submit(DEMO_PROMPTS[0])
        self.assertIsNone(controller.state.entries[0].steering_for)
        client = WaitingClient()
        task = asyncio.create_task(controller.step(client))
        try:
            await asyncio.wait_for(client.started.wait(), 2)
            controller.submit("first refinement")
            controller.submit("second refinement")
            self.assertEqual(
                [e.steering_for for e in controller.state.entries], [None, 0, 0]
            )
            client.release.set()
            await task
            controller.submit("after the reply")
            self.assertIsNone(controller.state.entries[-1].steering_for)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_failed_target_retains_intent_for_explicit_continuation(self) -> None:
        controller = make_controller(recovery_cassette())
        controller.submit(DEMO_PROMPTS[0])
        client = WaitingClient(fail=True)
        task = asyncio.create_task(controller.step(client))
        try:
            await asyncio.wait_for(client.started.wait(), 2)
            controller.submit(REFINEMENT)
            client.release.set()
            with self.assertRaises((AgentFailure, ValueError)):
                await task
            self.assertEqual(controller.state.entries[0].status, "failed")
            self.assertEqual(len(context_for(controller.state, 1)), 1)
            await controller.step()
            controller.submit(DEMO_PROMPTS[1])
            await controller.step()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(
            controller.state.entries[-1].answer, "The fixture boundary is eleven."
        )
        self.assertEqual(controller.state.exchanges_consumed, 3)

    async def test_terminal_failure_pauses_bound_steering_until_continue(self) -> None:
        controller = make_controller(recovery_cassette())
        client = WaitingClient(fail=True)
        step = controller.step
        queued = asyncio.Event()
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait(DEMO_PROMPTS[0])

        async def waiting_step(*, on_started: Callable[[], None] | None = None) -> bool:
            return await step(client, on_started=on_started)

        def emit(event: dict[str, object]) -> None:
            if event.get("steering_for") == 0:
                queued.set()

        with patch.object(controller, "step", side_effect=waiting_step):
            task = asyncio.create_task(terminal(controller, queue, emit))
            try:
                await asyncio.wait_for(client.started.wait(), 2)
                queue.put_nowait("/steer " + REFINEMENT)
                await asyncio.wait_for(queued.wait(), 2)
                client.release.set()
                queue.put_nowait(None)
                await asyncio.wait_for(task, 2)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(
            [e.status for e in controller.state.entries], ["failed", "queued"]
        )
        self.assertEqual(controller.state.exchanges_consumed, 1)
        queue.put_nowait("/continue")
        queue.put_nowait(None)
        await terminal(controller, queue, lambda event: None)
        self.assertEqual(controller.state.entries[1].status, "completed")

    async def test_unavailable_steering_does_not_resume_or_create_messages(
        self,
    ) -> None:
        controller = make_controller()
        controller.submit(DEMO_PROMPTS[0])
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        for line in ("/steer", "/steer missing active task", None):
            queue.put_nowait(line)
        events: list[dict[str, object]] = []
        await terminal(controller, queue, events.append)
        self.assertEqual(len(controller.state.entries), 1)
        self.assertEqual(controller.state.exchanges_consumed, 0)
        self.assertEqual(
            sum(e["type"] == "conversation.unavailable" for e in events), 2
        )
        with self.assertRaisesRegex(ValueError, "active chat"):
            controller.steer("unavailable")

    async def test_review_cannot_receive_steering_or_mutate_its_frozen_packet(
        self,
    ) -> None:
        brief, cassette = demo_inputs()
        packet = ConversationReviewPacket(brief=brief, cassette=cassette)
        controller = make_controller()
        controller.submit_review(packet)
        started = asyncio.Event()

        async def waiting_review(packet: ConversationReviewPacket) -> None:
            started.set()
            await asyncio.Event().wait()

        with patch(
            "mos_eisley.conversation.run_conversation_review",
            side_effect=waiting_review,
        ):
            task = asyncio.create_task(controller.step())
            try:
                await asyncio.wait_for(started.wait(), 2)
                with self.assertRaisesRegex(ValueError, "active chat"):
                    controller.steer("change the critic brief")
                controller.submit("question after review")
                self.assertIsNone(controller.state.entries[1].steering_for)
                self.assertEqual(controller.state.entries[0].review_packet, packet)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_steering_save_failure_does_not_publish_or_dispatch_refinement(
        self,
    ) -> None:
        controller = make_controller()
        controller.submit(DEMO_PROMPTS[0])
        client = WaitingClient()
        task = asyncio.create_task(controller.step(client))
        try:
            await asyncio.wait_for(client.started.wait(), 2)
            with (
                patch.object(controller, "save", side_effect=OSError("disk full")),
                self.assertRaises(OSError),
            ):
                controller.steer(REFINEMENT)
            self.assertEqual(len(controller.state.entries), 1)
            self.assertEqual(controller.state.exchanges_consumed, 1)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(len(client.requests), 1)

    async def test_composer_send_binds_at_submission_and_stop_cancels_chain(
        self,
    ) -> None:
        controller = make_controller()
        client = WaitingClient()
        step = controller.step
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        sent = asyncio.Event()
        queue.put_nowait(DEMO_PROMPTS[0])

        async def waiting_step(*, on_started: Callable[[], None] | None = None) -> bool:
            return await step(client, on_started=on_started)

        def emit(event: dict[str, object]) -> None:
            if event["type"] == "composer.sent":
                sent.set()

        with patch.object(controller, "step", side_effect=waiting_step):
            task = asyncio.create_task(terminal(controller, queue, emit))
            try:
                await asyncio.wait_for(client.started.wait(), 2)
                for line in ("/compose", "/steer literal draft text", "/send"):
                    queue.put_nowait(line)
                await asyncio.wait_for(sent.wait(), 2)
                self.assertEqual(controller.state.entries[1].steering_for, 0)
                self.assertEqual(
                    controller.state.entries[1].text, "/steer literal draft text"
                )
                queue.put_nowait("/stop")
                queue.put_nowait(None)
                await asyncio.wait_for(task, 2)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(
            [e.status for e in controller.state.entries], ["cancelled", "cancelled"]
        )
        self.assertEqual(controller.state.exchanges_consumed, 1)


class SteeringContractTests(TestCase):
    def test_unanswered_chain_preserves_intent_without_inventing_answers(self) -> None:
        controller = make_controller()
        state = controller.state.model_copy(
            update={
                "exchanges_consumed": 2,
                "entries": (
                    ConversationEntry(text="original task", status="interrupted"),
                    ConversationEntry(
                        text="first refinement", status="failed", steering_for=0
                    ),
                    ConversationEntry(text="next refinement", steering_for=1),
                ),
            }
        )
        state = ConversationState.model_validate_json(state.model_dump_json())
        self.assertEqual(
            context_for(state, 2),
            (
                Turn(
                    role="user",
                    blocks=(
                        TextBlock(text="original task"),
                        TextBlock(text="first refinement"),
                        TextBlock(text="next refinement"),
                    ),
                ),
            ),
        )

    def test_invalid_targets_and_review_entries_are_rejected_on_resume(self) -> None:
        controller = make_controller()
        brief, cassette = demo_inputs()
        packet = ConversationReviewPacket(brief=brief, cassette=cassette)
        for target, index in (
            (ConversationEntry(text="queued"), 0),
            (ConversationEntry(text="never dispatched", status="cancelled"), 0),
            (ConversationEntry(text="failed", status="failed"), 1),
            (ConversationEntry(text="failed", status="failed"), 2),
            (
                ConversationEntry(
                    text=REVIEW_PROMPT, status="cancelled", review_packet=packet
                ),
                0,
            ),
        ):
            with self.subTest(index=index, target=target.status):
                state = controller.state.model_copy(
                    update={
                        "exchanges_consumed": int(target.status == "failed"),
                        "entries": (
                            target,
                            ConversationEntry(text="refinement", steering_for=index),
                        ),
                    }
                )
                with self.assertRaises(ValueError):
                    ConversationState.model_validate_json(state.model_dump_json())
        with self.assertRaises(ValueError):
            ConversationEntry(text=REVIEW_PROMPT, review_packet=packet, steering_for=0)
        for target in (-1, 16, True):
            with self.assertRaises(ValueError):
                ConversationEntry.model_validate_json(
                    json.dumps({"text": "refinement", "steering_for": target})
                )

    def test_old_snapshot_encoding_stays_unchanged(self) -> None:
        controller = make_controller()
        controller.submit(DEMO_PROMPTS[0])
        encoded = canonical_bytes(controller.state)
        self.assertNotIn(b"steering_for", encoded)
        self.assertEqual(
            canonical_bytes(ConversationState.model_validate_json(encoded)), encoded
        )

    def test_killed_process_retains_bound_intent_for_explicit_resume(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = root / "cassette.json"
            cassette.write_bytes(canonical_bytes(recovery_cassette()))
            # Hold only the synthetic recorded client; exercise the real CLI,
            # store and signal/process recovery without a network provider.
            script = """import asyncio
from mos_eisley.providers.agent_recorded import RecordedAgentClient
from mos_eisley.cli import main
async def wait(self, request):
    await asyncio.Event().wait()
RecordedAgentClient.complete = wait
raise SystemExit(main())
"""
            options = [
                "--cassette",
                str(cassette),
                "--storage",
                str(root / "sessions"),
                "--workspace",
                str(root),
                "--json",
            ]
            process = subprocess.Popen(
                [sys.executable, "-c", script, "chat", *options],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert process.stdin is not None and process.stdout is not None
            output = process.stdout
            pending = bytearray()
            selection = selectors.DefaultSelector()
            selection.register(process.stdout, selectors.EVENT_READ)

            def read_event(kind: str) -> dict[str, object]:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    while b"\n" in pending:
                        line, _, rest = pending.partition(b"\n")
                        pending[:] = rest
                        event = json.loads(line)
                        if event["type"] == kind:
                            return event
                    if selection.select(timeout=0.1):
                        data = os.read(output.fileno(), 4096)
                        if not data:
                            raise AssertionError("child closed before expected event")
                        pending.extend(data)
                raise AssertionError("child did not emit expected event")

            try:
                opened = read_event("conversation.opened")
                process.stdin.write((DEMO_PROMPTS[0] + "\n").encode())
                process.stdin.flush()
                read_event("message.running")
                process.stdin.write(("/steer " + REFINEMENT + "\n").encode())
                process.stdin.flush()
                self.assertEqual(read_event("message.queued")["steering_for"], 0)
                process.kill()
                process.communicate(timeout=5)
            finally:
                selection.close()
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)
            session_id = str(opened["session_id"])
            snapshot_path = root / "sessions" / f"{session_id}.json"
            before = json.loads(snapshot_path.read_text())["state"]
            self.assertEqual(
                [e["status"] for e in before["entries"]], ["running", "queued"]
            )
            command = [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "resume",
                session_id,
                *options,
            ]
            subprocess.run(
                command,
                input="",
                text=True,
                capture_output=True,
                check=True,
                timeout=15,
            )
            paused = json.loads(snapshot_path.read_text())["state"]
            self.assertEqual(
                [e["status"] for e in paused["entries"]], ["interrupted", "queued"]
            )
            self.assertEqual(paused["exchanges_consumed"], 1)
            result = subprocess.run(
                command,
                input="/continue\n" + DEMO_PROMPTS[1] + "\n",
                text=True,
                capture_output=True,
                check=True,
                timeout=15,
            )
            self.assertIn("The fixture boundary is eleven.", result.stdout)
            after = json.loads(snapshot_path.read_text())["state"]
            self.assertEqual(
                [e["status"] for e in after["entries"]],
                ["interrupted", "completed", "completed"],
            )
            self.assertEqual(after["exchanges_consumed"], 3)
            self.assertEqual(after["entries"][1]["steering_for"], 0)
