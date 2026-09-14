"""G1 context-pressure accounting, advice, and inspection fixtures."""

import asyncio
import os
from pathlib import Path
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from pydantic import ValidationError
from test_conversation_tui import until
from test_task_state_acquisition import TaskStateFixture

from mos_eisley.conversation import (
    ConversationController,
    ConversationEntry,
    ConversationState,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_context_pressure import (
    ContextPressureMonitor,
    ContextPressurePolicy,
    context_pressure_report,
    measure_current_context,
)
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.agent import AgentUsage
from mos_eisley.core.budget import Budget
from mos_eisley.core.models import canonical_bytes
from mos_eisley.core.protocol import (
    ModelRequest,
    TextBlock,
    ToolDefinition,
    ToolSchema,
    Turn,
)


def measured_request(*, capacity: int = 100_000):
    guidance = '\n[{"guidance":"selected"}]'
    memory = '\n{"memory":"selected"}'
    checkpoint = '\n{"checkpoint":"selected"}'
    definition = ToolDefinition(
        name="bounded-read",
        description="Read one bounded source.",
        input_schema=ToolSchema(type="object"),
    )
    request = ModelRequest(
        provider="fixture",
        model="tool-reviewer-v1",
        effort="high",
        system="base system" + guidance + memory + checkpoint,
        tools=(definition,),
        turns=(Turn(role="user", blocks=(TextBlock(text="question"),)),),
        max_output=1000,
        max_output_tokens=250,
    )
    budget = Budget(
        cap=capacity + 1500,
        output_reserve=1000,
        usable_input=capacity,
        headroom=500,
        max_output_tokens=250,
    )
    return measure_current_context(
        request,
        budget,
        context_bytes=400,
        context_capacity_bytes=1000,
        project_guidance=guidance,
        selected_memory=memory,
        checkpoint=checkpoint,
    )


class ContextPressureContractTests(TestCase):
    def state(self) -> ConversationState:
        cassette = demo_cassette()
        return ConversationController.fresh(Path.cwd(), cassette)

    def test_exact_categories_capacity_and_distinct_local_token_estimate(self) -> None:
        current = measured_request()

        self.assertEqual(current.categories.total_bytes, current.request_bytes)
        self.assertGreater(current.categories.system_instruction_bytes, 0)
        self.assertGreater(current.categories.tool_schema_bytes, 0)
        self.assertGreater(current.categories.project_guidance_bytes, 0)
        self.assertGreater(current.categories.selected_memory_bytes, 0)
        self.assertGreater(current.categories.checkpoint_bytes, 0)
        self.assertGreater(current.categories.conversation_bytes, 0)
        self.assertGreater(current.categories.other_bytes, 0)
        self.assertEqual(
            current.local_input_token_estimate, (current.request_bytes + 3) // 4
        )
        self.assertIsNone(current.provider_input_tokens)
        self.assertEqual(
            current.request_available_bytes,
            current.request_capacity_bytes - current.request_bytes,
        )

    def test_versioned_config_stays_within_evaluation_ranges(self) -> None:
        policy = ContextPressurePolicy(
            context_advisory_basis_points=3000,
            substantial_tool_call_threshold=20,
        )
        self.assertEqual(policy.denominator_rule, "usable_model_input_bytes_v1")
        self.assertEqual(
            policy.substantial_call_rule,
            "completed_noninspection_tool_calls_v1",
        )
        for update in (
            {"context_advisory_basis_points": 2999},
            {"context_advisory_basis_points": 4001},
            {"substantial_tool_call_threshold": 19},
            {"substantial_tool_call_threshold": 31},
        ):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                ContextPressurePolicy.model_validate(update)

    def test_thresholds_are_advisory_and_hard_limits_remain_distinct(self) -> None:
        baseline = measured_request()
        pressured = measured_request(capacity=baseline.request_bytes * 2)
        report = context_pressure_report(self.state(), current=pressured)

        self.assertEqual(report.status, "advisory")
        self.assertEqual(report.advisories[0].code, "context_usage_threshold")
        self.assertEqual(report.advisories[0].assessment, "assess")
        self.assertFalse(report.automatic_action)
        self.assertFalse(report.automatic_delegation)
        self.assertFalse(report.grants_authority)
        self.assertFalse(report.critic_compaction_allowed)

        overflow = measured_request(capacity=baseline.request_bytes - 1)
        stopped = context_pressure_report(self.state(), current=overflow)
        self.assertEqual(stopped.status, "hard_limit")
        self.assertEqual(stopped.advisories[0].code, "hard_input_limit")
        self.assertEqual(stopped.advisories[0].assessment, "honor_hard_admission_limit")
        self.assertFalse(stopped.advisories[0].automatic_action)

    def test_monitor_emits_crossing_and_clear_once_without_transcript_state(
        self,
    ) -> None:
        baseline = measured_request()
        normal = context_pressure_report(self.state(), current=baseline)
        high = context_pressure_report(
            self.state(),
            current=measured_request(capacity=baseline.request_bytes * 2),
        )
        monitor = ContextPressureMonitor()

        self.assertIsNone(monitor.observe(normal))
        changed = monitor.observe(high)
        assert changed is not None
        self.assertEqual(changed.kind, "pressure_changed")
        self.assertIsNone(monitor.observe(high))
        cleared = monitor.observe(normal)
        assert cleared is not None
        self.assertEqual(cleared.kind, "pressure_cleared")
        self.assertEqual(cleared.advisories, ())


class ContextPressureTaskStateTests(TaskStateFixture, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.prepare_task_state(self)

    def test_checkpoint_baseline_preserves_categories_unknowns_and_signals(
        self,
    ) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(self.workspace, cassette)
        task_state = self.acquirer().acquire(
            owner_uid=os.getuid(),
            workspace=state.workspace,
            session_id=state.session_id,
        )

        report = context_pressure_report(state, task_state=task_state)

        self.assertEqual(report.boundary, "checkpoint")
        self.assertEqual(report.baseline, self.bundle.checkpoint.context_metrics)
        self.assertEqual(report.provider_input.value, 300)
        self.assertEqual(report.provider_input.known_items, 1)
        self.assertEqual(report.provider_input.unknown_items, 2)
        self.assertEqual(report.substantial_tool_calls, 2)
        self.assertEqual(report.repeated_reads, 0)
        self.assertEqual(report.compactions, 0)
        self.assertIn("unavailable for 2 request(s)", report.describe())


class ContextPressureTerminalTests(IsolatedAsyncioTestCase):
    async def test_status_without_a_queue_is_read_only_and_reports_unknown_tokens(
        self,
    ) -> None:
        cassette = demo_cassette()
        chat = ConversationController(
            ConversationController.fresh(Path.cwd(), cassette),
            cassette,
            lambda _: None,
        )
        before = chat.state
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        queue.put_nowait("/status")
        queue.put_nowait(None)
        events: list[dict[str, object]] = []

        await terminal(chat, queue, events.append)

        event = next(item for item in events if item["type"] == "conversation.status")
        self.assertIsNone(event["current"])
        provider_input = cast(dict[str, object], event["provider_input"])
        self.assertEqual(provider_input["unknown_items"], 0)
        self.assertIn("No queued author request", str(event["text"]))
        self.assertIs(chat.state, before)

    async def test_status_and_context_share_one_bounded_pressure_advisory(self) -> None:
        cassette = demo_cassette().model_copy(
            update={"exchanges": demo_cassette().exchanges * 4}
        )
        initial = ConversationController.fresh(
            Path.cwd(), cassette, context_max_bytes=1_000_000
        )
        usage = AgentUsage(
            requests=1,
            tools=0,
            billed_input=1,
            billed_output=1,
            largest_request=1,
        )
        entries = tuple(
            ConversationEntry(
                text="PRIVATE " + "x" * 7200,
                answer="PRIVATE " + "y" * 7200,
                status="completed",
                usage=usage,
            )
            for _ in range(4)
        ) + (ConversationEntry(text="PRIVATE queued"),)
        state = ConversationState.model_validate(
            initial.model_copy(
                update={"entries": entries, "exchanges_consumed": 4}
            ).model_dump()
        )
        chat = ConversationController(state, cassette, lambda _: None)
        before = canonical_bytes(chat.state)
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        for command in ("/status", "/context", None):
            queue.put_nowait(command)
        events: list[dict[str, object]] = []

        await terminal(chat, queue, events.append)

        status = next(item for item in events if item["type"] == "conversation.status")
        context = next(
            item for item in events if item["type"] == "conversation.context"
        )
        advisories = [
            item for item in events if item["type"] == "conversation.context_pressure"
        ]
        pressure = cast(dict[str, object], context["pressure"])
        self.assertEqual(status["current"], pressure["current"])
        self.assertEqual(len(advisories), 1)
        self.assertEqual(advisories[0]["kind"], "pressure_changed")
        self.assertNotIn("PRIVATE", str(advisories))
        self.assertEqual(canonical_bytes(chat.state), before)

    async def test_byte_usage_is_not_mislabeled_as_provider_tokens(self) -> None:
        cassette = demo_cassette()
        chat = ConversationController(
            ConversationController.fresh(Path.cwd(), cassette),
            cassette,
            lambda _: None,
        )
        chat.submit(DEMO_PROMPTS[0])
        await chat.step()

        report = context_pressure_report(chat.state)

        self.assertEqual(report.provider_input.value, 0)
        self.assertEqual(report.provider_input.known_items, 0)
        self.assertEqual(report.provider_input.unknown_items, 1)
        self.assertGreater(report.admitted_growth_input_bytes, 0)

    async def test_tui_status_toggles_without_dispatch_or_saving(self) -> None:
        cassette = demo_cassette()
        chat = ConversationController(
            ConversationController.fresh(Path.cwd(), cassette),
            cassette,
            lambda _: None,
        )
        chat.submit("queued question")
        before = chat.state
        with create_pipe_input() as input:
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                ui.control("/status")
                await until(lambda: "Context pressure" in ui.transcript.text)
                self.assertIn("Upcoming categories", ui.transcript.text)
                self.assertIs(chat.state, before)
                ui.control("/status")
                await until(lambda: ui.context_preview is None)
                self.assertIs(chat.state, before)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)
