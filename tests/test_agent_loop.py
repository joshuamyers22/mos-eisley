"""Tool-loop completion, failure semantics, and journal boundaries."""

import asyncio
from unittest import IsolatedAsyncioTestCase

from mos_eisley.core.agent import AgentConfig, AgentFailure, run_agent
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    ReasoningBlock,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
    Turn,
    Usage,
)
from mos_eisley.core.registry import fixture_registry, openai_registry
from mos_eisley.demo_agent import agent_demo_inputs
from mos_eisley.providers.agent_recorded import (
    AgentCassette,
    AgentExchange,
    RecordedAgentClient,
)
from mos_eisley.run.journal import MemoryJournal
from mos_eisley.tools.fixture import FixtureDispatcher
from mos_eisley.tools.none import NoToolsDispatcher


class AgentLoopTests(IsolatedAsyncioTestCase):
    async def test_two_turn_tool_exchange_and_journal(self) -> None:
        config, fixtures, cassette = agent_demo_inputs()
        journal = MemoryJournal()
        client = RecordedAgentClient(cassette)
        result = await run_agent(
            config,
            registry := fixture_registry(),
            client,
            FixtureDispatcher(fixtures),
            journal,
        )
        self.assertEqual(result.resolved_model.spec, registry.models[0])
        self.assertEqual(result.final_text, "The required quantity boundary is >= 10.")
        self.assertEqual((result.usage.requests, result.usage.tools), (2, 1))
        self.assertTrue(client.exhausted)
        self.assertEqual(
            tuple(event.type for event in journal.events),
            (
                "model.request.started",
                "model.response.completed",
                "tool.completed",
                "model.request.started",
                "model.response.completed",
            ),
        )
        self.assertEqual(
            tuple(event.sequence for event in journal.events), tuple(range(5))
        )
        self.assertEqual(
            journal.events[0].payload_sha256, cassette.exchanges[0].request_sha256
        )
        response = cassette.exchanges[0].response
        assert response is not None
        self.assertEqual(
            journal.events[1].payload_sha256, digest(canonical_bytes(response))
        )

    async def test_provider_failure_is_journaled_and_fails(self) -> None:
        config, fixtures, cassette = agent_demo_inputs()
        cassette = cassette.model_copy(
            update={
                "exchanges": (
                    cassette.exchanges[0].model_copy(update={"response": None}),
                )
            }
        )
        journal = MemoryJournal()
        with self.assertRaisesRegex(AgentFailure, "provider request"):
            await run_agent(
                config,
                fixture_registry(),
                RecordedAgentClient(cassette),
                FixtureDispatcher(fixtures),
                journal,
            )
        self.assertEqual(
            tuple(event.type for event in journal.events),
            ("model.request.started", "model.request.failed"),
        )

    async def test_reused_call_id_and_iteration_limit_fail(self) -> None:
        config, fixtures, cassette = agent_demo_inputs()
        second = cassette.exchanges[1]
        repeated = ModelResponse(
            turn=Turn(
                role="assistant",
                blocks=(
                    ToolCallBlock(
                        id="fixture-call-1",
                        name="fixture_lookup",
                        args={"key": "discount_boundary"},
                    ),
                ),
            ),
            stop_reason="tool_use",
            usage=Usage(input=1, output=1),
        )
        reused = cassette.model_copy(
            update={
                "exchanges": (
                    cassette.exchanges[0],
                    second.model_copy(update={"response": repeated}),
                )
            }
        )
        with self.assertRaisesRegex(AgentFailure, "reused"):
            await run_agent(
                config,
                fixture_registry(),
                RecordedAgentClient(reused),
                FixtureDispatcher(fixtures),
            )
        with self.assertRaisesRegex(AgentFailure, "iteration"):
            await run_agent(
                config.model_copy(update={"max_iterations": 1}),
                fixture_registry(),
                RecordedAgentClient(cassette),
                FixtureDispatcher(fixtures),
            )

    async def test_noncompletion_and_reasoning_only_completion_fail(self) -> None:
        config, fixtures, cassette = agent_demo_inputs()
        responses = (
            ModelResponse(
                turn=Turn(role="assistant", blocks=(TextBlock(text="truncated"),)),
                stop_reason="max_output",
                usage=Usage(input=1, output=1),
            ),
            ModelResponse(
                turn=Turn(
                    role="assistant",
                    blocks=(
                        ReasoningBlock(provider="fixture", visible=None, opaque={}),
                    ),
                ),
                stop_reason="end_turn",
                usage=Usage(input=1, output=1),
            ),
        )
        for response in responses:
            broken = AgentCassette(
                exchanges=(
                    AgentExchange(
                        request_sha256=cassette.exchanges[0].request_sha256,
                        response=response,
                    ),
                )
            )
            with self.assertRaises(AgentFailure):
                await run_agent(
                    config,
                    fixture_registry(),
                    RecordedAgentClient(broken),
                    FixtureDispatcher(fixtures),
                )

    async def test_mismatched_tool_result_fails(self) -> None:
        config, fixtures, cassette = agent_demo_inputs()
        journal = MemoryJournal()

        class BadDispatcher(FixtureDispatcher):
            async def dispatch(self, call: ToolCallBlock) -> ToolResultBlock:
                return ToolResultBlock(
                    call_id="different", name=call.name, content="wrong"
                )

        with self.assertRaisesRegex(AgentFailure, "does not match"):
            await run_agent(
                config,
                fixture_registry(),
                RecordedAgentClient(cassette),
                BadDispatcher(fixtures),
                journal,
            )
        self.assertEqual(journal.events[-1].type, "tool.failed")
        self.assertEqual(journal.events[-1].detail, "result_mismatch")

    async def test_provider_and_tool_timeouts_are_journaled(self) -> None:
        config, fixtures, cassette = agent_demo_inputs()

        class SlowClient:
            async def complete(self, request: ModelRequest) -> ModelResponse:
                await asyncio.sleep(1)
                raise AssertionError("unreachable")

        provider_journal = MemoryJournal()
        with self.assertRaisesRegex(AgentFailure, "provider request timed out"):
            await run_agent(
                config.model_copy(update={"request_timeout_seconds": 0.001}),
                fixture_registry(),
                SlowClient(),
                FixtureDispatcher(fixtures),
                provider_journal,
            )
        self.assertEqual(provider_journal.events[-1].type, "model.request.failed")
        self.assertEqual(provider_journal.events[-1].detail, "timeout")

        class SlowDispatcher(FixtureDispatcher):
            async def dispatch(self, call: ToolCallBlock) -> ToolResultBlock:
                await asyncio.sleep(1)
                raise AssertionError("unreachable")

        tool_journal = MemoryJournal()
        with self.assertRaisesRegex(AgentFailure, "tool call timed out"):
            await run_agent(
                config.model_copy(update={"tool_timeout_seconds": 0.001}),
                fixture_registry(),
                RecordedAgentClient(cassette),
                SlowDispatcher(fixtures),
                tool_journal,
            )
        self.assertEqual(tool_journal.events[-1].type, "tool.failed")
        self.assertEqual(tool_journal.events[-1].detail, "timeout")

    async def test_tool_limit_and_dispatcher_exception_fail_closed(self) -> None:
        config, fixtures, cassette = agent_demo_inputs()
        with self.assertRaisesRegex(AgentFailure, "tool-call limit"):
            await run_agent(
                config.model_copy(update={"max_tool_calls": 0}),
                fixture_registry(),
                RecordedAgentClient(cassette),
                FixtureDispatcher(fixtures),
            )

        class BrokenDispatcher(FixtureDispatcher):
            async def dispatch(self, call: ToolCallBlock) -> ToolResultBlock:
                raise RuntimeError("sensitive adapter detail")

        journal = MemoryJournal()
        with self.assertRaisesRegex(AgentFailure, "dispatcher failed unexpectedly"):
            await run_agent(
                config,
                fixture_registry(),
                RecordedAgentClient(cassette),
                BrokenDispatcher(fixtures),
                journal,
            )
        self.assertEqual(journal.events[-1].type, "tool.failed")
        self.assertEqual(journal.events[-1].detail, "dispatcher_exception")

    async def test_cancellation_propagates(self) -> None:
        config, fixtures, _ = agent_demo_inputs()
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        class BlockingClient:
            async def complete(self, request: ModelRequest) -> ModelResponse:
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
                raise AssertionError("unreachable")

        task = asyncio.create_task(
            run_agent(
                config,
                fixture_registry(),
                BlockingClient(),
                FixtureDispatcher(fixtures),
            )
        )
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cancelled.is_set())

    async def test_provider_token_usage_cannot_exceed_resolved_budget(self) -> None:
        config = AgentConfig(
            provider="openai",
            model="gpt-6-astra",
            initial_turns=(
                Turn(role="user", blocks=(TextBlock(text="Bound this request."),)),
            ),
        )

        class OverBudgetClient:
            async def complete(self, request: ModelRequest) -> ModelResponse:
                return ModelResponse(
                    turn=Turn(
                        role="assistant", blocks=(TextBlock(text="Too expensive."),)
                    ),
                    stop_reason="end_turn",
                    usage=Usage(unit="tokens", input=10, output=4097),
                )

        with self.assertRaisesRegex(AgentFailure, "output tokens"):
            await run_agent(
                config,
                openai_registry(),
                OverBudgetClient(),
                NoToolsDispatcher(),
            )
