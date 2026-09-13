"""Sealed campaign bindings restrict synthetic owned probes at every dispatch edge."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from pydantic import JsonValue
from test_review_approval_flow import ScriptedUser
from test_review_campaign import CampaignCeremonyFixture

from mos_eisley.core.models import JudgeRequest, canonical_bytes, digest
from mos_eisley.run.review_approval import ApprovalPreview
from mos_eisley.run.review_campaign import (
    review_campaign_evidence,
    seal_review_campaign,
)
from mos_eisley.run.review_campaign_dispatch import ReviewCampaignBinding
from mos_eisley.run.review_conformance_authorization import ReviewConformanceScope
from mos_eisley.run.review_conformance_probe import BrokeredReviewConformanceProbe
from mos_eisley.run.review_controller import ControllerJudgePreview


class CampaignDispatchTests(CampaignCeremonyFixture):
    async def asyncSetUp(self) -> None:
        self.prepare_attempts()
        self.fixture = self.fixtures[0]
        self.user = ScriptedUser(("approve", "approve"))
        self.binding = ReviewCampaignBinding(
            campaign_directory=str(self.sealed_directory),
            expected_seal_sha256=self.seal_sha,
            attempt_index=0,
        )
        self.enterContext(
            patch(
                "mos_eisley.run.review_conformance_probe.EphemeralOpenAITransport",
                self.fixture.sdk,
            )
        )

    def bound_probe(self) -> BrokeredReviewConformanceProbe:
        fixture = self.fixture
        probe = BrokeredReviewConformanceProbe(
            fixture.review,
            fixture.base.reviewer,
            self.policy.review_policy,
            self.user,
            critic_containers=(fixture.base.container,),
            judge_container=fixture.base.container,
            authority_policy=lambda: fixture.policy,
            load_authorization=fixture.load_certificate,
            load_api_key=fixture.key_loader,
            total_seconds=self.policy.total_seconds,
            campaign=self.binding,
        )
        fixture.controller = probe.controller
        fixture.preview = probe.controller.preview
        return probe

    def corrupt_bundle(self) -> None:
        path = self.sealed_directory / "bundle.json"
        path.write_bytes(path.read_bytes() + b" ")

    def assert_unspent(self) -> None:
        self.fixture.key_loader.assert_not_called()
        self.fixture.sdk.assert_not_called()
        self.assertEqual(self.fixture.base.ledger.snapshot().entries, 0)
        self.assertFalse(self.fixture.directory.exists())

    async def test_exact_bound_probe_requires_both_approvals_and_is_one_use(self):
        probe = self.bound_probe()
        self.assert_unspent()
        result = await probe.run()
        assert result is not None
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(len(self.user.previews), 2)
        self.assertEqual(self.fixture.key_loader.call_count, 4)
        self.assertEqual(len(self.fixture.lifecycles), 2)
        with self.assertRaises(ValueError):
            await probe.run()
        self.assertEqual(self.fixture.key_loader.call_count, 4)

    async def test_three_bound_probes_freshly_pass_campaign_evidence_review(self):
        for index, fixture in enumerate(self.fixtures):
            self.fixture = fixture
            self.user = ScriptedUser(("approve", "approve"))
            self.binding = self.binding.model_copy(update={"attempt_index": index})
            self.probes[index] = self.bound_probe()
        await self.execute_attempts()
        result = review_campaign_evidence(
            self.sealed_directory, self.seal_sha, self.submission(), now=self.now
        )
        self.assertEqual(result.status, "accepted")
        self.assertFalse(result.provider_dispatch_authorized)

    async def test_seal_does_not_replace_independent_signature(self):
        with patch.object(self.fixture, "load_certificate", return_value=None):
            result = await self.bound_probe().run()
        self.assertIsNone(result)
        self.assertEqual(self.user.previews, [])
        self.assert_unspent()

    def test_judge_projection_change_is_rejected_before_any_critic(self):
        original = self.fixture.base.reviewer.judge_request

        def changed(request: JudgeRequest):
            return original(request).model_copy(update={"system": "changed judge"})

        with (
            patch.object(
                self.fixture.base.reviewer, "judge_request", side_effect=changed
            ),
            self.assertRaisesRegex(ValueError, "judge configuration changed"),
        ):
            self.bound_probe()
        self.assert_unspent()

    def test_wrong_independent_seal_prevents_construction(self):
        self.binding = self.binding.model_copy(
            update={"expected_seal_sha256": "f" * 64}
        )
        with self.assertRaisesRegex(ValueError, "independent pin"):
            self.bound_probe()
        self.assert_unspent()

    def test_wrong_attempt_slot_prevents_construction(self):
        self.binding = self.binding.model_copy(update={"attempt_index": 1})
        with self.assertRaisesRegex(ValueError, "preview, runtime or authority"):
            self.bound_probe()
        self.assert_unspent()

    async def test_changed_seal_before_prompt_prevents_authorization_loading(self):
        with patch.object(self.fixture, "load_certificate") as load:
            probe = self.bound_probe()
            self.corrupt_bundle()
            with self.assertRaisesRegex(ValueError, "retained seal"):
                await probe.run()
        load.assert_not_called()
        self.assertEqual(self.user.previews, [])
        self.assert_unspent()

    async def test_changed_seal_after_signature_load_prevents_local_prompt(self):
        original = self.fixture.load_certificate

        async def load(scope: ReviewConformanceScope):
            signed = await original(scope)
            self.corrupt_bundle()
            return signed

        with patch.object(self.fixture, "load_certificate", side_effect=load):
            probe = self.bound_probe()
            with self.assertRaisesRegex(ValueError, "retained seal"):
                await probe.run()
        self.assertEqual(self.user.previews, [])
        self.assert_unspent()

    async def test_changed_seal_during_local_approval_prevents_reservation(self):
        async def approve(preview: ApprovalPreview) -> str:
            self.corrupt_bundle()
            return preview.sha256

        with (
            patch.object(self.user, "approve", side_effect=approve),
            self.assertRaisesRegex(ValueError, "retained seal"),
        ):
            await self.bound_probe().run()
        self.assert_unspent()

    async def test_changed_seal_in_key_loader_prevents_sdk_and_holds_spending(self):
        def key() -> str:
            self.corrupt_bundle()
            return "synthetic-test-key"

        self.fixture.key_loader.side_effect = key
        with self.assertRaises(ValueError):
            await self.bound_probe().run()
        self.fixture.sdk.assert_not_called()
        self.assertEqual(self.fixture.key_loader.call_count, 1)
        self.assertEqual(self.fixture.base.ledger.snapshot().charged_microusd, 650)
        self.assertTrue((self.fixture.lifecycles[0] / "result.json").is_file())

    async def test_changed_seal_after_count_prevents_generation(self):
        async def count(_payload: dict[str, JsonValue]) -> int:
            self.corrupt_bundle()
            return 10

        with (
            patch.object(
                self.fixture.base.fake, "count_input_tokens", side_effect=count
            ),
            self.assertRaises(ValueError),
        ):
            await self.bound_probe().run()
        self.assertEqual(self.fixture.key_loader.call_count, 1)
        self.assertEqual(self.fixture.base.fake.calls, [])
        self.assertEqual(self.fixture.judge.calls, [])

    async def test_changed_seal_after_generation_prevents_judge(self):
        original = self.fixture.base.fake.create_response

        async def generate(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
            result = await original(payload)
            self.corrupt_bundle()
            return result

        with (
            patch.object(
                self.fixture.base.fake, "create_response", side_effect=generate
            ),
            self.assertRaises(ValueError),
        ):
            await self.bound_probe().run()
        self.assertEqual(self.fixture.key_loader.call_count, 2)
        self.assertEqual(self.fixture.judge.calls, [])
        self.assertEqual(self.fixture.base.ledger.snapshot().charged_microusd, 650)

    async def test_changed_seal_during_judge_approval_blocks_judge_credentials(self):
        async def approve(preview: ApprovalPreview) -> str:
            if isinstance(preview, ControllerJudgePreview):
                self.corrupt_bundle()
            return preview.sha256

        with (
            patch.object(self.user, "approve", side_effect=approve),
            self.assertRaisesRegex(ValueError, "retained seal"),
        ):
            await self.bound_probe().run()
        self.assertEqual(self.fixture.key_loader.call_count, 2)
        self.assertEqual(self.fixture.judge.calls, [])
        self.assertEqual(self.fixture.base.ledger.snapshot().charged_microusd, 345)

    async def test_current_authority_cannot_rotate_away_from_sealed_policy(self):
        probe = self.bound_probe()
        self.fixture.policy = self.fixture.policy.model_copy(
            update={"policy_id": "changed"}
        )
        with self.assertRaisesRegex(ValueError, "preview, runtime or authority"):
            await probe.run()
        self.assert_unspent()

    async def test_current_image_cannot_rotate_away_from_sealed_runtime(self):
        probe = self.bound_probe()
        self.fixture.base.container.image_id = "sha256:" + "f" * 64
        with self.assertRaisesRegex(ValueError, "preview, runtime or authority"):
            await probe.run()
        self.assert_unspent()

    def test_copied_ledger_identity_cannot_substitute_for_selected_path(self):
        path = self.root / "copied-ledger.sqlite"
        path.write_bytes(self.fixture.base.ledger.path.read_bytes())
        self.fixture.base.ledger.path = path
        with self.assertRaisesRegex(ValueError, "sealed path or policy"):
            self.bound_probe()
        self.assert_unspent()

    async def test_campaign_expiry_caps_sdk_deadlines(self):
        bundle = self.bundle.model_copy(
            update={
                "policy": self.bundle.policy.model_copy(
                    update={"valid_until": datetime.now(UTC) + timedelta(seconds=5)}
                )
            }
        )
        directory = self.root / "short-campaign"
        seal = seal_review_campaign(
            bundle,
            directory,
            expected_bundle_sha256=digest(canonical_bytes(bundle)),
            now=datetime.now(UTC),
        )
        self.binding = self.binding.model_copy(
            update={
                "campaign_directory": str(directory),
                "expected_seal_sha256": digest(canonical_bytes(seal)),
            }
        )
        result = await self.bound_probe().run()
        self.assertIsNotNone(result)
        self.assertEqual(self.fixture.sdk.call_count, 4)
        for call in self.fixture.sdk.call_args_list:
            self.assertGreater(call.args[1], 0)
            self.assertLessEqual(call.args[1], 5)

    async def test_cancellation_awaits_cleanup_and_cannot_retry_bound_attempt(self):
        started = asyncio.Event()

        async def count(_payload: dict[str, JsonValue]) -> int:
            started.set()
            await asyncio.Future()
            return 10

        probe = self.bound_probe()
        with patch.object(
            self.fixture.base.fake, "count_input_tokens", side_effect=count
        ):
            task = asyncio.create_task(probe.run())
            await asyncio.wait_for(started.wait(), 5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue((self.fixture.lifecycles[0] / "result.json").is_file())
        with self.assertRaises(ValueError):
            await probe.run()
        self.assertEqual(self.fixture.key_loader.call_count, 1)
