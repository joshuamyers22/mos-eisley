"""Advisory context pressure is exact, bounded, and never authoritative."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from test_conversation_context import CapturingClient

from mos_eisley.conversation import ConversationController, ConversationEntry
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_context_preview import pressure_status, preview_context
from mos_eisley.conversation_pressure import (
    ContextPressureBreakdown,
    ContextPressurePolicy,
    assess_context_pressure,
    build_pressure_snapshot,
    implicit_pressure_boundary,
    measure_pressure_activity,
)
from mos_eisley.core.agent import AgentUsage
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import ToolCallBlock, ToolResultBlock, Turn


def controller(
    policy: ContextPressurePolicy | None = None,
) -> ConversationController:
    cassette = demo_cassette()
    return ConversationController(
        ConversationController.fresh(
            Path.cwd(), cassette, context_pressure_policy=policy
        ),
        cassette,
        lambda _: None,
        context_pressure_policy=policy,
    )


class ContextPressureTests(TestCase):
    def test_repeated_reads_ignore_call_ids_and_substantial_results_are_counted(
        self,
    ) -> None:
        policy = ContextPressurePolicy(
            context_threshold_basis_points=9000,
            material_growth_basis_points=500,
            material_growth_bytes=1024,
            substantial_tool_result_bytes=256,
            substantial_tool_call_threshold=1,
            repeated_read_threshold=1,
            read_tool_ids=("read_file",),
        )
        turns = (
            Turn(
                role="assistant",
                blocks=(
                    ToolCallBlock(id="call-a", name="read_file", args={"path": "x"}),
                    ToolCallBlock(id="call-b", name="read_file", args={"path": "x"}),
                ),
            ),
            Turn(
                role="user",
                blocks=(
                    ToolResultBlock(
                        call_id="call-a", name="read_file", content="z" * 300
                    ),
                    ToolResultBlock(
                        call_id="call-b", name="read_file", content="z" * 300
                    ),
                ),
            ),
        )
        activity = measure_pressure_activity(turns, policy)
        self.assertEqual(activity.tool_calls, 2)
        self.assertEqual(activity.substantial_tool_calls, 2)
        self.assertEqual(len(set(activity.read_fingerprints)), 1)

        usage = AgentUsage(
            requests=1, tools=2, billed_input=10, billed_output=5, largest_request=10
        )
        entry = ConversationEntry(
            text="done",
            status="completed",
            answer="done",
            usage=usage,
            pressure_activity=activity,
        )
        boundary = implicit_pressure_boundary()
        previous = build_pressure_snapshot(
            policy=policy,
            source_revision=1,
            request_ordinal=1,
            context_bytes=800,
            context_max_bytes=10_000,
            request_bytes=1000,
            request_max_bytes=10_000,
            known_breakdown=ContextPressureBreakdown(base_system_bytes=500),
            entries=(),
            boundary=boundary,
            compaction_count=0,
        )
        current = build_pressure_snapshot(
            policy=policy,
            source_revision=2,
            request_ordinal=2,
            context_bytes=5000,
            context_max_bytes=10_000,
            request_bytes=6000,
            request_max_bytes=10_000,
            known_breakdown=ContextPressureBreakdown(base_system_bytes=500),
            entries=(entry,),
            boundary=boundary,
            compaction_count=0,
        )
        advisory = assess_context_pressure(current, previous)
        assert advisory is not None
        self.assertEqual(
            advisory.reasons,
            (
                "substantial_tool_threshold_crossed",
                "repeated_read_threshold_crossed",
                "material_request_growth",
            ),
        )
        self.assertFalse(advisory.automatic_stop)
        self.assertFalse(advisory.automatic_compaction)
        self.assertFalse(advisory.automatic_delegation)
        self.assertFalse(advisory.approval_required)
        self.assertFalse(advisory.grants_authority)

    def test_status_polling_is_read_only_and_reports_explicit_units(self) -> None:
        chat = controller()
        before = canonical_bytes(chat.state)
        first = pressure_status(chat.state, chat.context_pressure_policy)
        second = pressure_status(chat.state, chat.context_pressure_policy)
        self.assertEqual(first, second)
        self.assertEqual(canonical_bytes(chat.state), before)
        self.assertEqual(first.tool_calls_since_boundary, 0)
        self.assertIn("Provider token counts: unavailable", first.describe())
        self.assertIn("does not count as a tool call", first.describe())


class ContextPressureDispatchTests(IsolatedAsyncioTestCase):
    async def test_threshold_event_is_recorded_but_does_not_block_dispatch(
        self,
    ) -> None:
        policy = ContextPressurePolicy(context_threshold_basis_points=1000)
        chat = controller(policy)
        chat.submit("x" * 8000)
        preview = preview_context(chat.state, policy)
        pressure = preview.pressure
        advisory = preview.pressure_advisory
        assert pressure is not None
        assert advisory is not None
        self.assertIn("request_context_threshold_crossed", advisory.reasons)
        self.assertEqual(pressure.breakdown.total_bytes, preview.request.bytes)
        self.assertEqual(
            pressure.tokens.local_estimated_input_tokens,
            (preview.request.bytes + 3) // 4,
        )
        self.assertEqual(pressure.tokens.current_status, "unavailable")

        client = CapturingClient()
        self.assertTrue(await chat.step(client))
        self.assertEqual(len(client.requests), 1)
        completed = chat.state.entries[0]
        admission = completed.request_admission
        assert admission is not None
        self.assertEqual(admission.schema_version, 5)
        self.assertEqual(admission.pressure, pressure)
        self.assertEqual(admission.pressure_advisory, advisory)
        self.assertIsNone(completed.pressure_activity)

        before = canonical_bytes(chat.state)
        status = pressure_status(chat.state, policy)
        self.assertEqual(canonical_bytes(chat.state), before)
        tokens = status.tokens
        assert tokens is not None
        self.assertEqual(tokens.historical_known_requests, 0)
        self.assertEqual(tokens.historical_unknown_requests, 1)
        report = status.describe()
        self.assertIn("Request byte categories:", report)
        self.assertIn("Growth since session_start boundary:", report)
        self.assertIn("current provider count unavailable", report)
        self.assertIn("No automatic stop", report)

    async def test_terminal_emits_one_bounded_advisory_event(self) -> None:
        policy = ContextPressurePolicy(context_threshold_basis_points=1000)
        chat = controller(policy)
        chat.submit("x" * 8000)
        client = CapturingClient()
        original_step = chat.step

        async def captured_step(
            *, on_started: Callable[[], None] | None = None
        ) -> bool:
            return await original_step(client, on_started=on_started)

        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait("/continue")
        queue.put_nowait(None)
        events: list[dict[str, object]] = []
        with patch.object(chat, "step", side_effect=captured_step):
            await terminal(chat, queue, events.append)

        pressure_events = [
            event for event in events if event["type"] == "conversation.pressure"
        ]
        self.assertEqual(len(pressure_events), 1)
        event = pressure_events[0]
        self.assertFalse(event["automatic_stop"])
        self.assertFalse(event["automatic_compaction"])
        self.assertFalse(event["automatic_delegation"])
        self.assertFalse(event["approval_required"])
        self.assertFalse(event["grants_authority"])
