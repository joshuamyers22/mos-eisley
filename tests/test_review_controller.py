"""Whole-review admission, critic concurrency, judge pause and owned cleanup."""

import asyncio
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import test_review_broker_admission as broker_fixture
import test_review_guidance_admission as guidance_fixture
from pydantic import JsonValue
from test_openai_spend import FakeTransport

from mos_eisley.core.models import (
    Critique,
    JudgeDecision,
    ReviewPolicy,
    canonical_bytes,
    digest,
)
from mos_eisley.core.ports import ProviderError
from mos_eisley.run.isolation import OfflineContainer
from mos_eisley.run.review_broker import PreparedReviewCall, PreparedReviewEnvelope
from mos_eisley.run.review_controller import (
    BrokeredReviewController,
    ControllerTerminal,
)
from mos_eisley.run.review_verdict import verify_retained_review_result


class ControllerTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.base = broker_fixture.ReviewAdmissionFixture()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        second = OfflineContainer(Path("/usr/bin/docker"), "sha256:" + "a" * 64)
        patcher = patch.object(second, "exchange_async", side_effect=self.base.exchange)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.containers = (self.base.container, second)
        self.calls = tuple(
            PreparedReviewCall(
                self.base.reviewer,
                self.base.request,
                self.base.policy,
                self.base.ledger,
                critic=self.base.critic.model_copy(update={"id": name}),
            )
            for name in ("one", "two")
        )
        self.directory = self.base.root / "review"
        self.envelope = PreparedReviewEnvelope(
            self.calls,
            self.base.policy,
            self.base.ledger,
            max_total_microusd=975,
            directory=self.directory,
        )
        self.policy = ReviewPolicy(min_critics=2, min_providers=1)
        self.controller = self.make_controller()
        self.transports = tuple(
            FakeTransport(self.directory / call.authorization.ledger_entry_id)
            for call in self.calls
        )
        for transport in self.transports:
            transport.response = broker_fixture.output(
                canonical_bytes(Critique()).decode()
            )
        self.judge = FakeTransport(self.directory / "judge")
        self.judge.response = broker_fixture.output(
            canonical_bytes(JudgeDecision(upheld=(), rationale="Fixture")).decode()
        )

    def make_controller(self, policy: ReviewPolicy | None = None):
        return BrokeredReviewController(
            self.envelope,
            self.base.reviewer,
            self.policy if policy is None else policy,
            total_seconds=30,
        )

    async def critics(self):
        return await self.controller.run_critics(
            approved_controller_sha256=self.controller.approval_sha256,
            transports=self.transports,
            containers=self.containers,
        )

    async def finish(self, approval: str):
        return await self.controller.run_judge(
            approved_preview_sha256=approval,
            transport=self.judge,
            container=self.base.container,
        )

    def terminal(self) -> ControllerTerminal:
        return ControllerTerminal.model_validate_json(
            (self.directory / "controller-terminal.json").read_bytes()
        )

    async def test_exact_approvals_pause_judge_and_reconstruct_final_result(self):
        with self.assertRaises(ValueError):
            await self.controller.run_critics(
                approved_controller_sha256=self.envelope.approval_sha256,
                transports=self.transports,
                containers=self.containers,
            )
        self.assertEqual(self.controller.phase, "prepared")
        self.assertEqual(self.base.ledger.snapshot().entries, 0)
        preview = await self.critics()
        self.assertEqual(self.controller.phase, "awaiting_judge")
        self.assertEqual(self.judge.calls, [])
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 365)
        with self.assertRaises(ValueError):
            await self.finish(self.controller.approval_sha256)
        self.assertEqual(self.controller.phase, "awaiting_judge")
        result = await self.finish(preview.sha256)
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(self.controller.phase, "finished")
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 60)
        self.assertEqual(self.terminal().result_sha256, digest(canonical_bytes(result)))
        self.assertEqual(
            verify_retained_review_result(
                self.envelope.envelope,
                self.base.reviewer,
                self.base.ledger,
                preview.authorization,
                digest(canonical_bytes(result)),
            ),
            result,
        )
        for operation in (self.critics(), self.finish(preview.sha256)):
            with self.assertRaises(ValueError):
                await operation
        self.assertEqual(len(self.judge.calls), 1)

    async def test_transport_count_rejection_preserves_prepared_state(self):
        with self.assertRaises(ValueError):
            await self.controller.run_critics(
                approved_controller_sha256=self.controller.approval_sha256,
                transports=(),
                containers=self.containers,
            )
        self.assertEqual(self.controller.phase, "prepared")
        self.assertFalse(self.directory.exists())

    def test_quorum_and_call_deadlines_are_checked_before_any_spend(self):
        for policy in (
            ReviewPolicy(),
            ReviewPolicy(min_critics=3, min_providers=1),
            self.policy.model_copy(update={"timeout_seconds": 61.0}),
        ):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                self.make_controller(policy)
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_request_budget_rejection_happens_before_any_spend(self):
        request = self.base.request.model_copy(
            update={
                "brief": self.base.request.brief.model_copy(update={"spec": "x" * 2000})
            }
        )
        call = PreparedReviewCall(
            self.base.reviewer,
            request,
            self.base.policy,
            self.base.ledger,
            critic=self.base.critic,
        )
        envelope = PreparedReviewEnvelope(
            (call,),
            self.base.policy,
            self.base.ledger,
            max_total_microusd=650,
            directory=self.base.root / "oversized",
        )
        with self.assertRaisesRegex(ValueError, "byte budget"):
            BrokeredReviewController(
                envelope,
                self.base.reviewer,
                ReviewPolicy(min_critics=1, min_providers=1, max_request_bytes=1024),
            )
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    async def test_failed_critic_is_tolerated_only_with_verified_quorum(self):
        self.controller = self.make_controller(
            ReviewPolicy(min_critics=1, min_providers=1)
        )
        self.transports[0].error = ProviderError("SECRET fixture diagnostic")
        preview = await self.critics()
        self.assertEqual(
            [c.result.status for c in preview.evidence.critics], ["error", "completed"]
        )
        result = await self.finish(preview.sha256)
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 365)
        self.assertNotIn(
            b"SECRET", (self.directory / "controller-terminal.json").read_bytes()
        )

    async def test_missing_quorum_blocks_judge_and_fails_controller(self):
        self.transports[0].response = broker_fixture.output("{}")
        with self.assertRaises(ValueError):
            await self.critics()
        self.assertEqual(self.controller.phase, "failed")
        self.assertEqual(self.terminal().phase, "failed")
        self.assertFalse((self.directory / "judge-transfer.json").exists())
        self.assertEqual(self.judge.calls, [])

    async def test_second_controller_cannot_poison_first_controller_artifacts(self):
        other = self.make_controller()
        preview = await self.critics()
        with self.assertRaises(ValueError):
            await other.run_critics(
                approved_controller_sha256=other.approval_sha256,
                transports=self.transports,
                containers=self.containers,
            )
        self.assertEqual(other.phase, "failed")
        self.assertFalse((self.directory / "controller-terminal.json").exists())
        self.assertEqual(
            (await self.finish(preview.sha256)).result.verdict.decision, "accept"
        )

    async def test_approval_pause_does_not_reset_whole_review_deadline(self):
        preview = await self.critics()
        loop = asyncio.get_running_loop()
        later = loop.time() + 60
        with (
            patch.object(loop, "time", return_value=later),
            self.assertRaises(TimeoutError),
        ):
            await self.finish(preview.sha256)
        self.assertEqual(self.controller.phase, "failed")
        self.assertEqual(self.judge.calls, [])
        self.assertFalse((self.directory / "judge-transfer.json").exists())

    async def test_idle_cancel_keeps_judge_allowance_and_denies_continuation(self):
        preview = await self.critics()
        before = self.base.ledger.snapshot()
        self.controller.cancel()
        self.assertEqual(self.terminal().phase, "cancelled")
        with self.assertRaises(ValueError):
            await self.finish(preview.sha256)
        self.assertEqual(self.base.ledger.snapshot(), before)

    def test_cancel_before_start_has_no_persistent_effects(self):
        self.controller.cancel()
        self.assertEqual(self.controller.phase, "cancelled")
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    async def tampered_record(self, name: str) -> None:
        preview = await self.critics()
        (self.directory / name).write_bytes(b"{}")
        with self.assertRaises(ValueError):
            await self.finish(preview.sha256)
        self.assertEqual(self.judge.calls, [])

    async def test_tampered_preview_cannot_dispatch_judge(self):
        await self.tampered_record("controller-judge-preview.json")

    async def test_tampered_start_cannot_dispatch_judge(self):
        await self.tampered_record("controller-start.json")

    async def test_invalid_judge_is_finished_infrastructure_result(self):
        preview = await self.critics()
        self.judge.response = broker_fixture.output("{}")
        result = await self.finish(preview.sha256)
        self.assertEqual(result.result.verdict.decision, "infrastructure_error")
        self.assertEqual(self.controller.phase, "finished")
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 60)

    async def test_failed_judge_retains_infrastructure_result_and_uncertain_spend(self):
        preview = await self.critics()
        self.judge.error = ProviderError("SECRET fixture diagnostic")
        result = await self.finish(preview.sha256)
        self.assertEqual(result.result.verdict.decision, "infrastructure_error")
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 365)

    async def test_critic_fanout_and_repeated_cancellation_await_all_children(self):
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
            task = asyncio.create_task(self.critics())
            try:
                await asyncio.wait_for(started.wait(), 5)
                with self.assertRaises(ValueError):
                    self.controller.cancel()
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
        self.assertEqual(self.controller.phase, "cancelled")
        self.assertEqual(self.terminal().phase, "cancelled")
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 975)

    async def test_terminal_storage_failure_does_not_repeat_paid_work(self):
        preview = await self.critics()
        with (
            patch(
                "mos_eisley.run.review_controller.private_write",
                side_effect=OSError("disk"),
            ),
            self.assertRaises(OSError),
        ):
            await self.finish(preview.sha256)
        self.assertEqual(self.controller.phase, "failed")
        self.assertTrue((self.directory / "review-result.json").exists())
        with self.assertRaises(ValueError):
            await self.finish(preview.sha256)
        self.assertEqual(len(self.judge.calls), 1)

    async def test_guidance_is_rechecked_at_delayed_judge_approval(self):
        guided = guidance_fixture.GuidedBrokerFixture()
        guided.setUp()
        self.addCleanup(guided.doCleanups)
        envelope = guided.envelope()
        controller = BrokeredReviewController(
            envelope, guided.base.reviewer, ReviewPolicy(min_critics=1, min_providers=1)
        )
        guided.base.fake.directory = (
            Path(envelope.envelope.artifact_directory)
            / guided.call.authorization.ledger_entry_id
        )
        preview = await controller.run_critics(
            approved_controller_sha256=controller.approval_sha256,
            transports=(guided.base.fake,),
            containers=(guided.base.container,),
        )
        guided.invalidate()
        with self.assertRaises(ValueError):
            await controller.run_judge(
                approved_preview_sha256=preview.sha256,
                transport=guided.base.fake,
                container=guided.base.container,
            )
        self.assertEqual(controller.phase, "failed")
        self.assertEqual(len(guided.base.fake.calls), 1)

    async def test_shared_container_is_rejected_before_reservation(self):
        with self.assertRaisesRegex(ValueError, "distinct container"):
            await self.controller.run_critics(
                approved_controller_sha256=self.controller.approval_sha256,
                transports=self.transports,
                containers=(self.base.container, self.base.container),
            )
        self.assertEqual(self.controller.phase, "prepared")
        self.assertEqual(self.base.ledger.snapshot().entries, 0)
