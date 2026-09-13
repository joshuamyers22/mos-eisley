"""Explicit human approval pauses preserve one-use dispatch and spending."""

import asyncio
import io
from typing import Literal
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from pydantic import JsonValue
from test_review_controller import ControllerFixture

from mos_eisley.core.models import canonical_bytes
from mos_eisley.review_approval_terminal import TerminalReviewApproval
from mos_eisley.run.review_approval import (
    ApprovalPreview,
    BrokeredReviewApprovalFlow,
)
from mos_eisley.run.review_controller import (
    BrokeredReviewController,
    ControllerCriticPreview,
)
from mos_eisley.run.review_verdict import RetainedReviewResult


class ScriptedUser:
    def __init__(self, answers: tuple[Literal["approve", "decline", "wrong"], ...]):
        self.answers = iter(answers)
        self.previews: list[ApprovalPreview] = []
        self.results: list[RetainedReviewResult] = []

    async def approve(self, preview: ApprovalPreview) -> str | None:
        self.previews.append(preview)
        answer = next(self.answers)
        if answer == "decline":
            return None
        return preview.sha256 if answer == "approve" else "f" * 64

    async def show_result(self, result: RetainedReviewResult) -> None:
        self.results.append(result)


class ApprovalFlowTests(ControllerFixture, IsolatedAsyncioTestCase):
    def run_flow(self, flow: BrokeredReviewApprovalFlow):
        return flow.run(
            critic_transports=self.transports,
            critic_containers=self.containers,
            judge_transport=self.judge,
            judge_container=self.base.container,
        )

    def test_preview_contains_exact_requests_and_spending_without_reservation(self):
        preview = self.controller.preview
        self.assertEqual(preview.sha256, self.controller.approval_sha256)
        self.assertEqual(preview.envelope.total_reserved_microusd, 975)
        self.assertEqual(preview.requests, tuple(c.model_request for c in self.calls))
        self.assertEqual(self.base.ledger.snapshot().entries, 0)
        self.assertFalse(self.directory.exists())
        broken = preview.model_copy(update={"requests": preview.requests[:1]})
        with self.assertRaises(ValueError):
            ControllerCriticPreview.model_validate_json(canonical_bytes(broken))

    async def test_two_separate_approvals_return_and_display_verified_result(self):
        user = ScriptedUser(("approve", "approve"))
        flow = BrokeredReviewApprovalFlow(self.controller, user)
        result = await self.run_flow(flow)
        self.assertEqual(user.results, [result])
        self.assertEqual(len(user.previews), 2)
        from mos_eisley.run.review_controller_inspection import (
            inspect_review_controller,
        )

        assert self.controller.start is not None and flow.judge_preview is not None
        state = inspect_review_controller(
            self.directory,
            self.controller.start,
            self.base.ledger,
            expected_judge_preview_sha256=flow.judge_preview.sha256,
        )
        self.assertEqual(state.recorded_phase, "finished")
        self.assertNotEqual(user.previews[0].sha256, user.previews[1].sha256)
        self.assertEqual(self.controller.phase, "finished")
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 60)
        with self.assertRaises(ValueError):
            await self.run_flow(flow)
        self.assertEqual(len(self.judge.calls), 1)

    async def test_declining_critics_makes_no_reservation_or_provider_call(self):
        user = ScriptedUser(("decline",))
        self.assertIsNone(
            await self.run_flow(BrokeredReviewApprovalFlow(self.controller, user))
        )
        self.assertEqual(self.controller.phase, "cancelled")
        self.assertEqual(self.base.ledger.snapshot().entries, 0)
        self.assertFalse(self.directory.exists())
        self.assertTrue(all(not t.calls for t in self.transports))

    async def test_declining_judge_preserves_allowance_and_does_not_dispatch(self):
        user = ScriptedUser(("approve", "decline"))
        self.assertIsNone(
            await self.run_flow(BrokeredReviewApprovalFlow(self.controller, user))
        )
        self.assertEqual(self.terminal().phase, "cancelled")
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 365)
        self.assertEqual(self.judge.calls, [])
        self.assertEqual(user.results, [])

    async def test_wrong_critic_approval_cannot_dispatch(self):
        user = ScriptedUser(("wrong",))
        with self.assertRaisesRegex(ValueError, "exact critic approval"):
            await self.run_flow(BrokeredReviewApprovalFlow(self.controller, user))
        self.assertEqual(self.base.ledger.snapshot().entries, 0)
        self.assertEqual(self.controller.phase, "cancelled")

    async def test_wrong_judge_approval_preserves_spending_and_does_not_dispatch(self):
        user = ScriptedUser(("approve", "wrong"))
        with self.assertRaisesRegex(ValueError, "exact judge approval"):
            await self.run_flow(BrokeredReviewApprovalFlow(self.controller, user))
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 365)
        self.assertEqual(self.terminal().phase, "cancelled")
        self.assertEqual(self.judge.calls, [])

    async def test_cancellation_during_initial_prompt_preserves_zero_spend(self):
        user = ScriptedUser(())
        waiting = asyncio.Event()

        async def wait(preview: ApprovalPreview) -> str | None:
            waiting.set()
            await asyncio.Event().wait()
            return None

        with patch.object(user, "approve", side_effect=wait):
            task = asyncio.create_task(
                self.run_flow(BrokeredReviewApprovalFlow(self.controller, user))
            )
            await waiting.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(self.controller.phase, "cancelled")
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    async def test_judge_prompt_deadline_cancels_without_judge_spend(self):
        self.controller = BrokeredReviewController(
            self.envelope, self.base.reviewer, self.policy, total_seconds=1.0
        )
        user = ScriptedUser(())

        async def wait(preview: ApprovalPreview) -> str | None:
            if isinstance(preview, ControllerCriticPreview):
                return preview.sha256
            await asyncio.sleep(5)
            return preview.sha256

        with (
            patch.object(user, "approve", side_effect=wait),
            self.assertRaises(TimeoutError),
        ):
            await self.run_flow(BrokeredReviewApprovalFlow(self.controller, user))
        self.assertEqual(self.controller.phase, "cancelled")
        self.assertEqual(self.judge.calls, [])
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 365)

    async def test_result_display_failure_cannot_replay_completed_judge(self):
        user = ScriptedUser(("approve", "approve"))
        flow = BrokeredReviewApprovalFlow(self.controller, user)
        with (
            patch.object(user, "show_result", side_effect=OSError("fixture output")),
            self.assertRaises(OSError),
        ):
            await self.run_flow(flow)
        self.assertEqual(self.controller.phase, "finished")
        self.assertEqual(len(self.judge.calls), 1)
        with self.assertRaises(ValueError):
            await self.run_flow(flow)

    async def test_competing_flow_cannot_cancel_an_existing_judge_pause(self):
        user = ScriptedUser(())

        async def competing(preview: ApprovalPreview) -> str:
            await self.critics()
            return preview.sha256

        with (
            patch.object(user, "approve", side_effect=competing),
            self.assertRaisesRegex(ValueError, "changed while awaiting"),
        ):
            await self.run_flow(BrokeredReviewApprovalFlow(self.controller, user))
        self.assertEqual(self.controller.phase, "awaiting_judge")
        self.assertFalse((self.directory / "controller-terminal.json").exists())

    async def test_terminal_show_requires_explicit_exact_approval(self):
        preview = self.controller.preview
        output = io.StringIO()
        answers = iter(("show", "approve " + preview.sha256))

        async def read_line(prompt: str) -> str:
            return next(answers)

        ui = TerminalReviewApproval(read_line, output)
        self.assertEqual(await ui.approve(preview), preview.sha256)
        rendered = output.getvalue()
        self.assertIn("$0.000975", rendered)
        self.assertIn("Required quorum: 2 critics; minimum providers: 1", rendered)
        self.assertIn(preview.sha256, rendered)
        self.assertIn("Return one", rendered)
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    async def test_terminal_blank_yes_wrong_hash_and_eof_are_declines(self):
        for answer in ("", "yes", "approve " + "f" * 64, None):

            async def read_line(prompt: str, value: str | None = answer) -> str:
                if value is None:
                    raise EOFError
                return value

            with self.subTest(answer=answer):
                self.assertIsNone(
                    await TerminalReviewApproval(read_line, io.StringIO()).approve(
                        self.controller.preview
                    )
                )

    async def test_terminal_escapes_control_sequences_in_untrusted_content(self):
        preview = self.controller.preview
        dangerous = preview.requests[0].model_copy(
            update={"model": "fixture\x1b[2J\u202e"}
        )
        preview = preview.model_copy(
            update={"requests": (dangerous, preview.requests[1])}
        )
        answers = iter(("show", "cancel"))
        output = io.StringIO()

        async def read_line(prompt: str) -> str:
            return next(answers)

        self.assertIsNone(
            await TerminalReviewApproval(read_line, output).approve(preview)
        )
        self.assertNotIn("\x1b", output.getvalue())
        self.assertNotIn("\u202e", output.getvalue())
        self.assertIn("\\u001b", output.getvalue())

    async def test_repeated_flow_cancellation_awaits_both_critic_cleanups(self):
        user = ScriptedUser(("approve",))
        started = asyncio.Event()
        cleaning = asyncio.Event()
        release = asyncio.Event()
        counts = [0, 0]

        async def blocked(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
            counts[0] += 1
            if counts[0] == 2:
                started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()
                counts[1] += 1
            return {}

        with (
            patch.object(self.transports[0], "create_response", side_effect=blocked),
            patch.object(self.transports[1], "create_response", side_effect=blocked),
        ):
            flow = BrokeredReviewApprovalFlow(self.controller, user)
            task = asyncio.create_task(self.run_flow(flow))
            try:
                await asyncio.wait_for(started.wait(), 5)
                task.cancel()
                await asyncio.wait_for(cleaning.wait(), 5)
                task.cancel()
                await asyncio.sleep(0)
                self.assertFalse(task.done())
            finally:
                release.set()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertEqual(counts, [2, 2])
        self.assertEqual(self.terminal().phase, "cancelled")
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 975)
        self.assertEqual(user.results, [])

    async def test_changed_evidence_during_judge_prompt_blocks_dispatch(self):
        user = ScriptedUser(())

        async def tamper(preview: ApprovalPreview) -> str:
            if not isinstance(preview, ControllerCriticPreview):
                (self.directory / "controller-judge-preview.json").write_bytes(b"{}")
            return preview.sha256

        with (
            patch.object(user, "approve", side_effect=tamper),
            self.assertRaises(ValueError),
        ):
            await self.run_flow(BrokeredReviewApprovalFlow(self.controller, user))
        self.assertEqual(self.controller.phase, "failed")
        self.assertEqual(self.judge.calls, [])
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 365)

    async def test_terminal_flow_displays_infrastructure_error_without_acceptance(self):
        import test_review_broker_admission as broker_fixture

        self.judge.response = broker_fixture.output("{}")
        output = io.StringIO()

        async def read_line(prompt: str) -> str:
            # Scripted fixture user approves each separately displayed request.
            approved = output.getvalue().rsplit("Approval: ", 1)[1].splitlines()[0]
            return "approve " + approved

        ui = TerminalReviewApproval(read_line, output)
        result = await self.run_flow(BrokeredReviewApprovalFlow(self.controller, ui))
        assert result is not None
        self.assertEqual(result.result.verdict.decision, "infrastructure_error")
        self.assertIn("Review judge request", output.getvalue())
        self.assertIn("Review result: infrastructure_error", output.getvalue())
        self.assertNotIn("Review result: accept", output.getvalue())

    async def test_ui_failure_before_approval_never_reserves_spending(self):
        user = ScriptedUser(())
        with (
            patch.object(user, "approve", side_effect=OSError("terminal")),
            self.assertRaises(OSError),
        ):
            await self.run_flow(BrokeredReviewApprovalFlow(self.controller, user))
        self.assertEqual(self.controller.phase, "cancelled")
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    async def test_real_async_terminal_input_accepts_exact_hash(self):
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import DummyHistory
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput

        with create_pipe_input() as terminal_input:
            session = PromptSession[str](
                input=terminal_input, output=DummyOutput(), history=DummyHistory()
            )

            async def read_line(prompt: str) -> str:
                return await session.prompt_async(prompt)

            preview = self.controller.preview
            ui = TerminalReviewApproval(read_line, io.StringIO())
            task = asyncio.create_task(ui.approve(preview))
            terminal_input.send_text("approve " + preview.sha256 + "\n")
            self.assertEqual(await asyncio.wait_for(task, 5), preview.sha256)
        self.assertEqual(self.base.ledger.snapshot().entries, 0)
