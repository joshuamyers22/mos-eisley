"""Context admission preserves intent and rejects before persistence or dispatch."""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import Mock, patch

from mos_eisley.conversation import (
    ConversationController,
    ConversationEntry,
    ConversationMemoryContext,
    ConversationState,
    context_for,
    conversation_config,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_context import (
    ContextBudgetError,
    RequestContext,
    admit_context,
    context_turns,
)
from mos_eisley.conversation_input import ConversationInput
from mos_eisley.conversation_limits import DEFAULT_CONTEXT_BYTES
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_review import REVIEW_PROMPT, ConversationReviewPacket
from mos_eisley.core.agent import (
    AgentUsage,
    RequestBudgetError,
    build_request,
    check_request_budget,
)
from mos_eisley.core.budget import resolve_budget
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelRequest, ModelResponse, TextBlock, Turn
from mos_eisley.core.registry import fixture_registry
from mos_eisley.demo import demo_inputs
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.conversation_resume import inspect_sqlite_resume
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.tools.none import NoToolsDispatcher


class CapturingClient:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        response = demo_cassette().exchanges[0].response
        assert response is not None
        return response


@dataclass(frozen=True)
class TextMessage:
    text: str
    status: str = "queued"
    answer: str | None = None
    steering_for: int | None = None


class ContextSelectionTests(TestCase):
    def test_shared_provider_request_boundary_includes_request_envelope(self) -> None:
        config = conversation_config(
            (Turn(role="user", blocks=(TextBlock(text="x"),)),)
        )
        resolved = fixture_registry().resolve(
            config.provider, config.model, config.effort
        )
        budget = resolve_budget(resolved.spec, resolved.effort, config.budget)
        request = build_request(
            config, resolved, budget, NoToolsDispatcher(), config.initial_turns
        )
        size = len(canonical_bytes(request))
        self.assertEqual(
            check_request_budget(
                request, budget.model_copy(update={"usable_input": size})
            ),
            size,
        )
        with self.assertRaises(RequestBudgetError) as caught:
            check_request_budget(
                request, budget.model_copy(update={"usable_input": size - 1})
            )
        self.assertEqual(caught.exception.required_bytes, size)
        self.assertEqual(caught.exception.maximum_bytes, size - 1)

    def test_text_only_projection_preserves_completed_and_unanswered_ancestry(
        self,
    ) -> None:
        entries = (
            TextMessage("original intent", "interrupted"),
            TextMessage("refinement", "cancelled", steering_for=0),
            TextMessage("finish this", "completed", "done", 1),
            TextMessage("unrelated failed task", "failed"),
            TextMessage("next question"),
            TextMessage("future queued text"),
        )
        self.assertEqual(
            context_turns(entries, 4),
            (
                Turn(
                    role="user",
                    blocks=tuple(
                        TextBlock(text=text)
                        for text in ("original intent", "refinement", "finish this")
                    ),
                ),
                Turn(role="assistant", blocks=(TextBlock(text="done"),)),
                Turn(role="user", blocks=(TextBlock(text="next question"),)),
            ),
        )

    def test_completed_steering_target_is_not_duplicated(self) -> None:
        turns = context_turns(
            (
                TextMessage("first", "completed", "answer"),
                TextMessage("followup", steering_for=0),
            ),
            1,
        )
        self.assertEqual(len(turns), 3)
        self.assertEqual(turns[-1].blocks, (TextBlock(text="followup"),))

    def test_invalid_positions_and_links_fail_before_recursive_selection(self) -> None:
        for entries, index in (
            ((), 0),
            ((TextMessage("x"),), -1),
            ((TextMessage("x"),), 1),
            ((TextMessage("x"),) * 17, 0),
            ((TextMessage("x", steering_for=0),), 0),
            ((TextMessage("x", steering_for=-1),), 0),
        ):
            with (
                self.subTest(entries=entries, index=index),
                self.assertRaises(ValueError),
            ):
                context_turns(entries, index)

    def test_byte_boundary_counts_utf8_escaping_system_and_role_envelopes(self) -> None:
        turns = (Turn(role="user", blocks=(TextBlock(text='é\n"' * 900),)),)
        system = "saved memory\n" * 40
        expected = len(canonical_bytes(RequestContext(system=system, turns=turns)))
        self.assertGreater(expected, len(system) + 2700)
        self.assertEqual(admit_context(system, turns, expected), expected)
        with self.assertRaises(ContextBudgetError) as caught:
            admit_context(system, turns, expected - 1)
        self.assertEqual(caught.exception.required_bytes, expected)
        self.assertEqual(caught.exception.maximum_bytes, expected - 1)
        self.assertNotIn("saved memory", str(caught.exception))

    def test_invalid_limits_fail_without_admission(self) -> None:
        turns = (Turn(role="user", blocks=(TextBlock(text="x"),)),)
        for maximum in (0, 3999, 1_000_001, True):
            with self.subTest(maximum=maximum), self.assertRaises(ValueError):
                admit_context("", turns, maximum)


class ContextControllerTests(IsolatedAsyncioTestCase):
    async def test_provider_limit_cannot_be_bypassed_by_context_resize(self) -> None:
        cassette = AgentCassette(exchanges=demo_cassette().exchanges * 4)
        state = ConversationController.fresh(
            Path.cwd(), cassette, context_max_bytes=1_000_000
        )
        usage = AgentUsage(
            requests=1, tools=0, billed_input=1, billed_output=1, largest_request=1
        )
        state = ConversationState.model_validate(
            state.model_copy(
                update={
                    "exchanges_consumed": 6,
                    "entries": tuple(
                        ConversationEntry(
                            text="x" * 8000,
                            status="completed",
                            answer="y" * 8000,
                            usage=usage,
                        )
                        for _ in range(6)
                    )
                    + (ConversationEntry(text="next"),),
                }
            ).model_dump()
        )
        save = Mock()
        controller = ConversationController(state, cassette, save)
        client = CapturingClient()
        with self.assertRaises(RequestBudgetError) as caught:
            await controller.step(client)
        self.assertEqual(caught.exception.maximum_bytes, 79_800)
        self.assertGreater(caught.exception.required_bytes, 79_800)
        self.assertEqual(controller.state, state)
        self.assertEqual(client.requests, [])
        save.assert_not_called()
        queue = asyncio.Queue[ConversationInput]()
        queue.put_nowait("/continue")
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        await terminal(controller, queue, events.append)
        error = next(event for event in events if event["type"] == "conversation.error")
        self.assertIn("provider input limit is 79800", str(error["text"]))
        self.assertIn("no attempt was consumed", str(error["text"]))
        self.assertEqual(controller.state, state)
        save.assert_not_called()

    async def test_rejection_preserves_queue_revision_attempts_and_allows_retry(
        self,
    ) -> None:
        for store_type in (ConversationStore, SQLiteConversationStore):
            with self.subTest(store=store_type), TemporaryDirectory() as directory:
                root = Path(directory)
                cassette = demo_cassette()
                state = ConversationController.fresh(
                    root, cassette, context_max_bytes=4000
                )
                with store_type(root, state.session_id, root) as store:
                    store.save(state)
                    controller = ConversationController(state, cassette, store.save)
                    controller.submit("private prompt " * 400)
                    before = controller.state
                    client = CapturingClient()
                    started = Mock()
                    with self.assertRaises(ContextBudgetError):
                        await controller.step(client, on_started=started)
                    started.assert_not_called()
                    self.assertEqual(client.requests, [])
                    self.assertEqual(controller.state, before)
                    self.assertEqual(store.load(), before)
                    controller.resize_storage(8_000_000)
                    with self.assertRaises(ContextBudgetError):
                        await controller.step(client)
                    controller.resize_context(20_000)
                    await controller.step(client)
                    self.assertEqual(controller.state.exchanges_consumed, 1)
                    self.assertEqual(controller.state.entries[0].status, "completed")
                    self.assertEqual(len(client.requests), 1)
                    self.assertEqual(store.load(), controller.state)

    async def test_active_memory_counts_but_historical_artifacts_do_not(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            memory_store = MemoryStore(root / "memory", root)
            memory_store.change("user", "set", text="HISTORICAL_CONTEXT " * 600)
            memory = memory_store.load()
            cassette = demo_cassette(memory=memory)
            state = ConversationController.fresh(
                root, cassette, memory, context_max_bytes=4000
            )
            controller = ConversationController(state, cassette, lambda state: None)
            controller.submit(DEMO_PROMPTS[0])
            with self.assertRaises(ContextBudgetError):
                await controller.step()
            self.assertEqual(controller.state.exchanges_consumed, 0)
            controller.resize_context(30_000)
            await controller.step()
            # Retained memory belongs to the old request, never to the next one.
            prior = controller.state.entries[0].model_copy(
                update={"memory_context": ConversationMemoryContext(memory=memory)}
            )
            state = controller.state.model_copy(update={"entries": (prior,)})
            controller = ConversationController(state, cassette, lambda state: None)
            controller.refresh_memory(None, cassette, disabled=True)
            controller.resize_context(4000)
            controller.submit(DEMO_PROMPTS[1])
            client = CapturingClient()
            await controller.step(client)
            self.assertNotIn("HISTORICAL_CONTEXT", client.requests[0].model_dump_json())
            self.assertIsNotNone(controller.state.entries[0].memory_context)

    async def test_rejection_does_not_erase_steering_or_drop_older_completed_text(
        self,
    ) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(
            Path.cwd(), cassette, context_max_bytes=4000
        )
        state = ConversationState.model_validate(
            state.model_copy(
                update={
                    "exchanges_consumed": 1,
                    "entries": (
                        ConversationEntry(text="intent " * 800, status="interrupted"),
                        ConversationEntry(text="refine", steering_for=0),
                    ),
                }
            ).model_dump()
        )
        controller = ConversationController(state, cassette, lambda state: None)
        with self.assertRaises(ContextBudgetError):
            await controller.step(CapturingClient())
        self.assertEqual(controller.state, state)
        usage = AgentUsage(
            requests=1, tools=0, billed_input=1, billed_output=1, largest_request=1
        )
        state = state.model_copy(
            update={
                "entries": (
                    ConversationEntry(
                        text="old instructions " * 400,
                        status="completed",
                        answer="yes",
                        usage=usage,
                    ),
                    ConversationEntry(text="new prompt"),
                )
            }
        )
        controller = ConversationController(state, cassette, lambda state: None)
        with self.assertRaises(ContextBudgetError):
            await controller.step(CapturingClient())
        self.assertEqual(controller.state, state)

    async def test_config_is_frozen_before_running_callback(self) -> None:
        cassette = demo_cassette()
        controller = ConversationController(
            ConversationController.fresh(Path.cwd(), cassette),
            cassette,
            lambda state: None,
        )
        controller.submit(DEMO_PROMPTS[0])
        expected = conversation_config(context_for(controller.state, 0))
        client = CapturingClient()
        await controller.step(
            client, on_started=lambda: controller.steer("queued refinement")
        )
        self.assertEqual(client.requests[0].turns, expected.initial_turns)
        self.assertEqual(controller.state.entries[1].steering_for, 0)

    async def test_review_uses_its_existing_packet_limits_and_no_chat_admission(
        self,
    ) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(
            Path.cwd(), cassette, context_max_bytes=4000
        )
        controller = ConversationController(state, cassette, lambda state: None)
        brief, review_cassette = demo_inputs()
        controller.submit_review(
            ConversationReviewPacket(brief=brief, cassette=review_cassette)
        )
        with patch(
            "mos_eisley.conversation.admit_context",
            side_effect=AssertionError("chat context accessed"),
        ):
            await controller.step()
        self.assertEqual(controller.state.entries[0].text, REVIEW_PROMPT)
        self.assertEqual(controller.state.exchanges_consumed, 0)

    async def test_resize_busy_failure_and_noop_do_not_change_state(self) -> None:
        cassette = demo_cassette()
        controller = ConversationController(
            ConversationController.fresh(Path.cwd(), cassette, context_max_bytes=4000),
            cassette,
            lambda state: None,
        )
        state = controller.state
        controller.resize_context(4000)
        self.assertEqual(controller.state, state)
        with (
            patch.object(controller, "_busy", True),
            self.assertRaisesRegex(ValueError, "active work"),
        ):
            controller.resize_context(8000)
        for maximum in (3999, 1_000_001):
            with self.assertRaises(ValueError):
                controller.resize_context(maximum)
        with (
            patch.object(controller, "save", side_effect=OSError("disk full")),
            self.assertRaises(OSError),
        ):
            controller.resize_context(8000)
        self.assertEqual(controller.state, state)
        with self.assertRaisesRegex(ValueError, "persistence failed"):
            controller.submit("later")


class ContextPersistenceTests(TestCase):
    def test_legacy_hash_omits_default_and_budget_survives_refresh_and_recovery(
        self,
    ) -> None:
        for store_type in (ConversationStore, SQLiteConversationStore):
            with self.subTest(store=store_type), TemporaryDirectory() as directory:
                root = Path(directory)
                cassette = demo_cassette()
                state = ConversationController.fresh(root, cassette)
                self.assertNotIn("context_max_bytes", state.model_dump())
                self.assertEqual(state.context_byte_limit, DEFAULT_CONTEXT_BYTES)
                legacy = state.model_dump()
                self.assertEqual(
                    digest(canonical_bytes(state)),
                    digest(
                        json.dumps(
                            legacy, sort_keys=True, separators=(",", ":")
                        ).encode()
                    ),
                )
                with store_type(root, state.session_id, root) as store:
                    store.save(state)
                    controller = ConversationController(
                        store.load(), cassette, store.save
                    )
                    controller.resize_context(8000)
                    controller.submit(DEMO_PROMPTS[0])
                    asyncio.run(controller.step())
                    controller.refresh_memory(None, cassette, disabled=True)
                    running = controller.state.model_copy(
                        update={
                            "revision": controller.state.revision + 1,
                            "exchanges_consumed": 2,
                            "entries": controller.state.entries
                            + (ConversationEntry(text="pending", status="running"),),
                        }
                    )
                    store.save(running)
                with store_type(root, state.session_id, root, create=False) as store:
                    controller = ConversationController(
                        store.load(), cassette, store.save
                    )
                    self.assertEqual(controller.state.context_byte_limit, 8000)
                    self.assertEqual(controller.state.exchanges_consumed, 2)
                    self.assertEqual(controller.state.entries[-1].status, "interrupted")
                    self.assertEqual(store.load(), controller.state)
                if store_type is SQLiteConversationStore:
                    self.assertEqual(
                        inspect_sqlite_resume(
                            root, state.session_id, root
                        ).header.context_max_bytes,
                        8000,
                    )


class ContextCLITests(TestCase):
    def invoke(
        self, home: Path, *args: str, text: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *args],
            input=text,
            text=True,
            capture_output=True,
            env={**os.environ, "HOME": str(home)},
            timeout=20,
        )

    def test_launch_rejection_resize_and_inspect_for_both_backends(self) -> None:
        for backend in ("snapshot", "sqlite"):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                home = Path(directory)
                flags = ("--storage-backend", backend, "-C", str(home), "--plain")
                result = self.invoke(
                    home, "--context-max-bytes", "4000", *flags, text="x" * 5000 + "\n"
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Chat context budget: 4000 bytes", result.stdout)
                self.assertIn("no attempt was consumed", result.stdout)
                result = self.invoke(
                    home, "resume", "--last", "--context-max-bytes", "8000", *flags
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Chat context budget: 8000 bytes", result.stdout)
                result = self.invoke(home, "resume", "--last", *flags)
                self.assertIn("Chat context budget: 8000 bytes", result.stdout)
                result = self.invoke(
                    home,
                    "sessions",
                    "--storage-backend",
                    backend,
                    "-C",
                    str(home),
                    "--json",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                row = json.loads(result.stdout)["sessions"][0]
                self.assertEqual(row["pending"], 1)
                self.assertEqual(row["completed"], 0)
                if backend == "sqlite":
                    result = self.invoke(
                        home,
                        "resume",
                        "--last",
                        "--storage-backend",
                        backend,
                        "-C",
                        str(home),
                        "--inspect",
                        "--json",
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        json.loads(result.stdout)["header"]["context_max_bytes"], 8000
                    )

    def test_invalid_limit_and_inspection_mutation_rejected_before_storage(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            for maximum in ("3999", "1000001", "-1", "abc", "1.5"):
                result = self.invoke(home, "--context-max-bytes", maximum, "--plain")
                self.assertEqual(result.returncode, 2)
                self.assertFalse((home / ".mos-eisley-sessions").exists())
            result = self.invoke(
                home,
                "resume",
                "--last",
                "--storage-backend",
                "sqlite",
                "--inspect",
                "--context-max-bytes",
                "8000",
            )
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("conversation.resume_inspected", result.stdout)
            self.assertFalse((home / ".mos-eisley-sessions").exists())
