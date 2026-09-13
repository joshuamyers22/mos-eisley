"""Campaign sequencing uses synthetic providers and separately signed observations."""

import asyncio
import base64
from datetime import UTC, datetime
from unittest.mock import patch

from pydantic import JsonValue
from test_openai_spend import FakeTransport
from test_review_approval_flow import ScriptedUser
from test_review_campaign import CampaignCeremonyFixture

from mos_eisley.run.review_campaign import (
    CampaignAttemptSubmission,
    review_campaign_evidence,
)
from mos_eisley.run.review_campaign_dispatch import ReviewCampaignBinding
from mos_eisley.run.review_campaign_runner import (
    CampaignProbeCompletion,
    OwnedReviewCampaign,
)
from mos_eisley.run.review_conformance_authorization import ReviewConformanceScope
from mos_eisley.run.review_conformance_observation import (
    make_review_probe_observation,
    sign_review_probe_observation,
)
from mos_eisley.run.review_conformance_probe import BrokeredReviewConformanceProbe
from mos_eisley.run.review_runtime_evidence import collect_review_runtime_exchange


class CampaignRunnerTests(CampaignCeremonyFixture):
    async def asyncSetUp(self) -> None:
        self.prepare_attempts()
        self.users = [ScriptedUser(("approve", "approve")) for _ in range(3)]
        self.observed: list[int] = []
        for index, fixture in enumerate(self.fixtures):
            fixture.base.fake.response["id"] = f"runner-critic-{index}"
            fixture.judge.response["id"] = f"runner-judge-{index}"
            probe = BrokeredReviewConformanceProbe(
                fixture.review,
                fixture.base.reviewer,
                self.policy.review_policy,
                self.users[index],
                critic_containers=(fixture.base.container,),
                judge_container=fixture.base.container,
                authority_policy=lambda fixture=fixture: fixture.policy,
                load_authorization=self.loader(index),
                load_api_key=fixture.key_loader,
                total_seconds=self.policy.total_seconds,
                campaign=ReviewCampaignBinding(
                    campaign_directory=str(self.sealed_directory),
                    expected_seal_sha256=self.seal_sha,
                    attempt_index=index,
                ),
            )
            self.probes[index] = probe
            fixture.controller = probe.controller
            fixture.preview = probe.controller.preview

        def transport(*args: object) -> FakeTransport:
            active = [
                fixture
                for fixture in self.fixtures
                if fixture.controller.phase in {"critics_running", "judge_running"}
            ]
            self.assertEqual(len(active), 1)
            return active[0].sdk(*args)

        self.enterContext(
            patch(
                "mos_eisley.run.review_conformance_probe.EphemeralOpenAITransport",
                side_effect=transport,
            )
        )

    def loader(self, index: int):
        async def load(scope: ReviewConformanceScope):
            fixture = self.fixtures[index]
            fixture.timestamp = datetime.now(UTC)
            return fixture.certificate(scope)

        return load

    async def observe(
        self, completion: CampaignProbeCompletion
    ) -> CampaignAttemptSubmission:
        index = completion.attempt_index
        self.observed.append(index)
        self.assertEqual(self.observed, list(range(index + 1)))
        for future in self.fixtures[index + 1 :]:
            future.key_loader.assert_not_called()
            self.assertEqual(future.base.ledger.snapshot().entries, 0)
        fixture = self.fixtures[index]
        exchanges = tuple(
            collect_review_runtime_exchange(
                directory, lifecycle, request, signed.authorization
            )
            for directory, lifecycle, request, signed in zip(
                (fixture.critic_directory(), fixture.directory / "judge"),
                fixture.lifecycles,
                (*fixture.preview.requests, completion.judge.model_request),
                completion.authorizations,
                strict=True,
            )
        )
        observation = make_review_probe_observation(
            self.observation_policies[index],
            fixture.policy,
            fixture.preview,
            completion.start,
            completion.judge,
            completion.authorizations,
            fixture.base.reviewer,
            fixture.base.ledger,
            expected_result_sha256=completion.expected_result_sha256,
            exchanges=exchanges,
            observed_at=datetime.now(UTC),
        )
        return CampaignAttemptSubmission(
            start=completion.start,
            judge=completion.judge,
            authorizations=completion.authorizations,
            signed_observation=sign_review_probe_observation(
                observation, "observer", fixture.observer_key
            ),
            expected_result_sha256=completion.expected_result_sha256,
            lifecycle_directories=tuple(str(path) for path in fixture.lifecycles),
        )

    def runner(self, *, observer_timeout_seconds: float = 120) -> OwnedReviewCampaign:
        return OwnedReviewCampaign(
            self.sealed_directory,
            self.seal_sha,
            tuple(self.probes),
            self.observe,
            observer_timeout_seconds=observer_timeout_seconds,
        )

    def assert_future_unused(self, first: int) -> None:
        for fixture in self.fixtures[first:]:
            fixture.key_loader.assert_not_called()
            self.assertFalse(fixture.directory.exists())
            self.assertEqual(fixture.base.ledger.snapshot().entries, 0)

    async def test_three_slots_require_verified_observation_before_the_next(self):
        runner = self.runner()
        self.assert_future_unused(0)
        self.assertEqual(runner.phase, "prepared")
        result = await runner.run()
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.qualifying_attempts, 3)
        self.assertEqual(runner.phase, "accepted")
        self.assertEqual(self.observed, [0, 1, 2])
        self.assertEqual([f.key_loader.call_count for f in self.fixtures], [4, 4, 4])
        rechecked = review_campaign_evidence(
            self.sealed_directory,
            self.seal_sha,
            runner.submission,
            now=datetime.now(UTC),
        )
        self.assertEqual(rechecked.status, "accepted")
        self.assertFalse(rechecked.provider_dispatch_authorized)
        with self.assertRaisesRegex(ValueError, "consumed"):
            await runner.run()

    def test_reordered_or_duplicate_probes_cannot_start(self):
        for probes in (
            (self.probes[1], self.probes[0], self.probes[2]),
            (self.probes[0],) * 3,
        ):
            with self.assertRaises(ValueError):
                OwnedReviewCampaign(
                    self.sealed_directory, self.seal_sha, probes, self.observe
                )
        self.assert_future_unused(0)

    def test_standalone_probe_cannot_replace_a_bound_slot(self):
        self.probes[0] = self.fixtures[0].probe()
        with self.assertRaisesRegex(ValueError, "exact ordered slots"):
            self.runner()
        self.assert_future_unused(0)

    async def test_missing_observation_stops_before_next_probe(self):
        with patch.object(self, "observe", return_value=None):
            runner = self.runner()
            result = await runner.run()
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(result.qualifying_attempts, 0)
        self.assertEqual(runner.phase, "incomplete")
        self.assertIsNotNone(runner.last_completion)
        self.assertEqual(runner.submission.attempts, (None, None, None))
        self.assert_future_unused(1)

    async def test_local_decline_stops_campaign_without_observer_or_credentials(self):
        with patch.object(self.users[0], "approve", return_value=None):
            runner = self.runner()
            result = await runner.run()
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(self.observed, [])
        self.assertIsNone(runner.last_completion)
        self.assert_future_unused(0)

    async def test_invalid_observation_blocks_future_probes(self):
        original = self.observe

        async def observe(completion: CampaignProbeCompletion):
            supplied = await original(completion)
            signed = supplied.signed_observation.model_copy(
                update={"signature_base64": base64.b64encode(bytes(64)).decode()}
            )
            return supplied.model_copy(update={"signed_observation": signed})

        with patch.object(self, "observe", side_effect=observe):
            runner = self.runner()
            with self.assertRaises(ValueError):
                await runner.run()
        self.assertEqual(runner.phase, "failed")
        self.assert_future_unused(1)
        self.assertEqual(runner.submission.attempts, (None, None, None))

    async def test_wrong_handoff_result_pin_blocks_future_probes(self):
        original = self.observe

        async def observe(completion: CampaignProbeCompletion):
            supplied = await original(completion)
            return supplied.model_copy(update={"expected_result_sha256": "f" * 64})

        with (
            patch.object(self, "observe", side_effect=observe),
            self.assertRaisesRegex(ValueError, "owned probe completion"),
        ):
            await self.runner().run()
        self.assert_future_unused(1)

    async def test_prior_evidence_is_rechecked_when_second_observer_returns(self):
        original = self.observe

        async def observe(completion: CampaignProbeCompletion):
            supplied = await original(completion)
            if completion.attempt_index == 1:
                path = self.fixtures[0].critic_directory() / "runtime-count-start.json"
                path.write_bytes(b"{}")
            return supplied

        with patch.object(self, "observe", side_effect=observe):
            runner = self.runner()
            with self.assertRaises(ValueError):
                await runner.run()
        self.assertIsNotNone(runner.submission.attempts[0])
        self.assertIsNone(runner.submission.attempts[1])
        self.assert_future_unused(2)

    async def test_observer_timeout_cancels_handoff_and_stops_campaign(self):
        closed = asyncio.Event()

        async def observe(_completion: CampaignProbeCompletion):
            try:
                await asyncio.Future()
            finally:
                closed.set()

        with patch.object(self, "observe", side_effect=observe):
            runner = self.runner(observer_timeout_seconds=0.01)
            result = await runner.run()
        self.assertTrue(closed.is_set())
        self.assertEqual(result.status, "incomplete")
        self.assert_future_unused(1)

    async def test_cancel_during_observation_retains_completion_without_next_probe(
        self,
    ):
        entered, closed = asyncio.Event(), asyncio.Event()

        async def observe(_completion: CampaignProbeCompletion):
            entered.set()
            try:
                await asyncio.Future()
            finally:
                closed.set()

        with patch.object(self, "observe", side_effect=observe):
            runner = self.runner()
            task = asyncio.create_task(runner.run())
            await asyncio.wait_for(entered.wait(), 10)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(closed.is_set())
        self.assertEqual(runner.phase, "cancelled")
        self.assertIsNotNone(runner.last_completion)
        self.assert_future_unused(1)
        with self.assertRaises(ValueError):
            await runner.run()

    async def test_cancel_during_probe_awaits_worker_cleanup(self):
        entered = asyncio.Event()

        async def count(_payload: dict[str, JsonValue]) -> int:
            entered.set()
            await asyncio.Future()
            return 10

        with patch.object(
            self.fixtures[0].base.fake, "count_input_tokens", side_effect=count
        ):
            runner = self.runner()
            task = asyncio.create_task(runner.run())
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(runner.phase, "cancelled")
        self.assertTrue((self.fixtures[0].lifecycles[0] / "result.json").is_file())
        self.assert_future_unused(1)

    async def test_observer_cannot_swallow_cancellation_and_start_another_probe(self):
        entered = asyncio.Event()
        original = self.observe

        async def observe(completion: CampaignProbeCompletion):
            entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                return await original(completion)

        with patch.object(self, "observe", side_effect=observe):
            runner = self.runner()
            task = asyncio.create_task(runner.run())
            await asyncio.wait_for(entered.wait(), 10)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(runner.phase, "cancelled")
        self.assert_future_unused(1)

    async def test_observer_cannot_swallow_timeout_and_start_another_probe(self):
        original = self.observe

        async def observe(completion: CampaignProbeCompletion):
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                return await original(completion)

        with patch.object(self, "observe", side_effect=observe):
            runner = self.runner(observer_timeout_seconds=0.01)
            result = await runner.run()
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(result.qualifying_attempts, 0)
        self.assert_future_unused(1)

    async def test_competing_run_cannot_cancel_owned_observer_pause(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def observe(_completion: CampaignProbeCompletion):
            entered.set()
            await release.wait()
            return None

        with patch.object(self, "observe", side_effect=observe):
            runner = self.runner()
            task = asyncio.create_task(runner.run())
            await asyncio.wait_for(entered.wait(), 10)
            with self.assertRaisesRegex(ValueError, "consumed"):
                await runner.run()
            self.assertEqual(runner.phase, "awaiting_observer")
            release.set()
            self.assertEqual((await task).status, "incomplete")
        self.assert_future_unused(1)

    async def test_provider_failure_never_invokes_observer_or_future_probe(self):
        with patch.object(
            self.fixtures[0].base.fake, "create_response", side_effect=OSError
        ):
            runner = self.runner()
            with self.assertRaises(ValueError):
                await runner.run()
        self.assertEqual(self.observed, [])
        self.assertEqual(runner.phase, "failed")
        self.assert_future_unused(1)
