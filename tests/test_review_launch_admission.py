"""Launch decisions and revocation races use synthetic independent keys only."""

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import JsonValue
from test_review_approval_flow import ScriptedUser
from test_review_campaign import CampaignCeremonyFixture

from mos_eisley.core.models import JudgeRequest, canonical_bytes, digest
from mos_eisley.run.review_approval import ApprovalPreview
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceScope,
    review_conformance_signer,
)
from mos_eisley.run.review_conformance_probe import BrokeredReviewConformanceProbe
from mos_eisley.run.review_controller import ControllerJudgePreview
from mos_eisley.run.review_launch_admission import (
    ReviewLaunchAdmissionInputs,
    ReviewLaunchBinding,
)
from mos_eisley.run.review_launch_authorization import (
    ReviewLaunchAuthorityPolicy,
    ReviewLaunchDecision,
    SignedReviewLaunchDecision,
    sign_review_launch_decision,
)
from mos_eisley.run.store import private_write


class LaunchAdmissionFixture(CampaignCeremonyFixture):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.fixture = self.create_fixture()
        self.user = ScriptedUser(("approve", "approve"))
        self.configuration = self.bundle.attempts[0].configuration
        self.configuration = self.configuration.model_copy(
            update={
                "critics": (
                    self.configuration.critics[0].model_copy(
                        update={"spending": self.fixture.base.policy}
                    ),
                ),
                "judge_spending": self.fixture.base.policy,
            }
        )
        self.evidence_path = self.root / "launch-campaign-evidence.json"
        self.evidence_raw = canonical_bytes(self.submission())
        private_write(self.evidence_path, self.evidence_raw)
        self.binding = ReviewLaunchBinding(
            campaign_directory=str(self.sealed_directory),
            expected_seal_sha256=self.seal_sha,
            evidence_path=str(self.evidence_path),
            expected_evidence_sha256=digest(self.evidence_raw),
        )
        self.launch_key = Ed25519PrivateKey.from_private_bytes(b"c" * 32)
        now = datetime.now(UTC)
        self.launch_policy = ReviewLaunchAuthorityPolicy(
            policy_id="fixture-launch",
            reviewers=(
                review_conformance_signer(
                    "launch-reviewer", self.launch_key.public_key()
                ),
            ),
            valid_from=now - timedelta(seconds=1),
            valid_until=now + timedelta(minutes=3),
            max_decision_seconds=60,
            max_reserved_microusd=1000,
        )
        self.signed: SignedReviewLaunchDecision | None = None
        self.enterContext(
            patch(
                "mos_eisley.run.review_conformance_probe.EphemeralOpenAITransport",
                self.fixture.sdk,
            )
        )

    async def load_phase(self, scope: ReviewConformanceScope):
        self.fixture.timestamp = datetime.now(UTC)
        return await self.fixture.load_certificate(scope)

    def probe(self) -> BrokeredReviewConformanceProbe:
        fixture = self.fixture
        probe = BrokeredReviewConformanceProbe(
            fixture.review,
            fixture.base.reviewer,
            self.policy.review_policy,
            self.user,
            critic_containers=(fixture.base.container,),
            judge_container=fixture.base.container,
            authority_policy=lambda: fixture.policy,
            load_authorization=self.load_phase,
            load_api_key=fixture.key_loader,
            total_seconds=self.policy.total_seconds,
            launch=ReviewLaunchAdmissionInputs(
                self.binding,
                self.configuration,
                lambda: self.launch_policy,
                lambda: self.signed,
            ),
        )
        fixture.controller, fixture.preview = probe.controller, probe.controller.preview
        return probe

    def authorize(
        self, probe: BrokeredReviewConformanceProbe, seconds: int = 60
    ) -> None:
        scope = probe.launch_scope
        assert scope is not None
        now = datetime.now(UTC)
        decision = ReviewLaunchDecision(
            scope=scope,
            issued_at=now,
            valid_until=min(scope.expires_at, now + timedelta(seconds=seconds)),
            commitment_custody_reviewed=True,
            credentialed_campaign_reviewed=True,
            independent_observer_assessment_reviewed=True,
        )
        self.signed = sign_review_launch_decision(
            decision, "launch-reviewer", self.launch_key
        )

    def revoke(self) -> None:
        self.signed = None

    def assert_unspent(self) -> None:
        self.fixture.key_loader.assert_not_called()
        self.fixture.sdk.assert_not_called()
        self.assertEqual(self.fixture.base.ledger.snapshot().entries, 0)
        self.assertFalse(self.fixture.directory.exists())


class LaunchAdmissionTests(LaunchAdmissionFixture):
    async def test_exact_launch_requires_all_approvals_and_retains_private_decision(
        self,
    ):
        probe = self.probe()
        self.assert_unspent()
        self.assertIsNone(probe.launch_decision)
        self.authorize(probe)
        before = [f.base.ledger.path.read_bytes() for f in self.fixtures]
        result = await probe.run()
        assert result is not None and self.signed is not None
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(len(self.user.previews), 2)
        self.assertEqual(len(probe.approval_ui.authorizations), 2)
        self.assertEqual(self.fixture.key_loader.call_count, 4)
        self.assertEqual(self.fixture.base.ledger.snapshot().charged_microusd, 40)
        self.assertEqual(
            before, [f.base.ledger.path.read_bytes() for f in self.fixtures]
        )
        record = self.fixture.directory / "launch-admission.json"
        self.assertEqual(record.read_bytes(), canonical_bytes(self.signed))
        self.assertEqual(record.stat().st_mode & 0o777, 0o600)
        self.assertEqual(probe.launch_decision, self.signed)
        with self.assertRaises(ValueError):
            await probe.run()
        self.assertEqual(self.fixture.key_loader.call_count, 4)

    async def test_missing_decision_blocks_before_phase_or_local_approval(self):
        with patch.object(self, "load_phase") as load:
            probe = self.probe()
            with self.assertRaisesRegex(ValueError, "independent signed decision"):
                await probe.run()
        load.assert_not_called()
        self.assertEqual(self.user.previews, [])
        self.assert_unspent()

    async def test_launch_decision_does_not_replace_phase_signature(self):
        with patch.object(self.fixture, "load_certificate", return_value=None):
            probe = self.probe()
            self.authorize(probe)
            self.assertIsNone(await probe.run())
        self.assert_unspent()

    async def test_launch_decision_does_not_replace_local_consent(self):
        self.user = ScriptedUser(("decline",))
        probe = self.probe()
        self.authorize(probe)
        self.assertIsNone(await probe.run())
        self.assert_unspent()

    def test_incomplete_campaign_cannot_prepare_launch(self):
        partial = self.submission().model_copy(update={"attempts": (None, None, None)})
        raw = canonical_bytes(partial)
        self.evidence_path.write_bytes(raw)
        self.binding = self.binding.model_copy(
            update={"expected_evidence_sha256": digest(raw)}
        )
        with self.assertRaisesRegex(ValueError, "all three"):
            self.probe()
        self.assert_unspent()

    def test_launch_reviewer_cannot_reuse_campaign_authority_or_observer_key(self):
        original = self.launch_policy
        for signer in (
            *self.fixture.policy.authorities,
            *self.fixture.policy.observers,
        ):
            self.launch_policy = original.model_copy(update={"reviewers": (signer,)})
            with (
                self.subTest(signer=signer.signer_id),
                self.assertRaisesRegex(ValueError, "separate"),
            ):
                self.probe()
        self.assert_unspent()

    async def test_revoked_policy_after_preparation_blocks_before_prompt(self):
        probe = self.probe()
        self.authorize(probe)
        self.launch_policy = self.launch_policy.model_copy(
            update={"policy_id": "revoked"}
        )
        with self.assertRaises(ValueError):
            await probe.run()
        self.assertEqual(self.user.previews, [])
        self.assert_unspent()

    async def test_revocation_in_credential_loader_blocks_sdk_and_preserves_hold(self):
        probe = self.probe()
        self.authorize(probe)

        def key() -> str:
            self.revoke()
            return "synthetic-key"

        self.fixture.key_loader.side_effect = key
        with self.assertRaises(ValueError):
            await probe.run()
        self.assertEqual(self.fixture.key_loader.call_count, 1)
        self.fixture.sdk.assert_not_called()
        self.assertEqual(self.fixture.base.ledger.snapshot().charged_microusd, 650)

    async def test_revocation_during_count_blocks_generation(self):
        probe = self.probe()
        self.authorize(probe)
        original = self.fixture.base.fake.count_input_tokens

        async def count(payload: dict[str, JsonValue]) -> int:
            result = await original(payload)
            self.revoke()
            return result

        with (
            patch.object(
                self.fixture.base.fake, "count_input_tokens", side_effect=count
            ),
            self.assertRaises(ValueError),
        ):
            await probe.run()
        self.assertEqual(self.fixture.key_loader.call_count, 1)
        self.assertEqual(self.fixture.sdk.call_count, 1)
        self.assertEqual(self.fixture.base.ledger.snapshot().charged_microusd, 650)

    async def test_changed_guidance_before_run_blocks_without_spending(self):
        probe = self.probe()
        self.authorize(probe)
        self.fixture.guided.fixture.add_requirement()
        with self.assertRaises(ValueError):
            await probe.run()
        self.assert_unspent()

    async def test_changed_campaign_evidence_after_decision_blocks(self):
        probe = self.probe()
        self.authorize(probe)
        self.evidence_path.write_bytes(self.evidence_raw + b" ")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            await probe.run()
        self.assert_unspent()

    async def test_signature_for_another_preview_is_rejected(self):
        probe = self.probe()
        self.authorize(probe)
        assert self.signed is not None
        decision = self.signed.decision.model_copy(
            update={
                "scope": self.signed.decision.scope.model_copy(
                    update={"critic_preview_sha256": "f" * 64}
                )
            }
        )
        self.signed = sign_review_launch_decision(
            decision, "launch-reviewer", self.launch_key
        )
        with self.assertRaisesRegex(ValueError, "scope"):
            await probe.run()
        self.assert_unspent()

    async def test_wrong_signature_domain_is_rejected(self):
        probe = self.probe()
        self.authorize(probe)
        assert self.signed is not None
        self.signed = self.signed.model_copy(
            update={
                "signature_base64": base64.b64encode(
                    self.launch_key.sign(
                        b"different-domain" + canonical_bytes(self.signed.decision)
                    )
                ).decode()
            }
        )
        with self.assertRaisesRegex(ValueError, "signature"):
            await probe.run()
        self.assert_unspent()

    async def test_decision_deadline_caps_every_sdk_operation(self):
        probe = self.probe()
        self.authorize(probe, seconds=18)
        self.assertIsNotNone(await probe.run())
        self.assertEqual(self.fixture.sdk.call_count, 4)
        for call in self.fixture.sdk.call_args_list:
            self.assertGreater(call.args[1], 0)
            self.assertLessEqual(call.args[1], 18)

    async def test_revocation_during_judge_prompt_blocks_judge_credentials(self):
        probe = self.probe()
        self.authorize(probe)

        async def approve(preview: ApprovalPreview) -> str:
            if isinstance(preview, ControllerJudgePreview):
                self.revoke()
            return preview.sha256

        with (
            patch.object(self.user, "approve", side_effect=approve),
            self.assertRaises(ValueError),
        ):
            await probe.run()
        self.assertEqual(self.fixture.key_loader.call_count, 2)
        self.assertEqual(self.fixture.judge.calls, [])
        self.assertEqual(self.fixture.base.ledger.snapshot().charged_microusd, 345)

    async def test_changed_worker_image_blocks_before_credentials(self):
        probe = self.probe()
        self.authorize(probe)
        self.fixture.base.container.image_id = "sha256:" + "f" * 64
        with self.assertRaises(ValueError):
            await probe.run()
        self.assert_unspent()

    def test_owning_judge_change_blocks_before_first_critic(self):
        original = self.fixture.base.reviewer.judge_request

        def changed(request: JudgeRequest):
            return original(request).model_copy(update={"system": "different judge"})

        with (
            patch.object(
                self.fixture.base.reviewer, "judge_request", side_effect=changed
            ),
            self.assertRaisesRegex(ValueError, "owning launch judge"),
        ):
            self.probe()
        self.assert_unspent()

    def test_campaign_ledger_cannot_fund_the_new_launch(self):
        self.fixture.base.ledger = self.fixtures[0].base.ledger
        self.fixture.call = self.fixture.prepare()
        self.fixture.review = self.fixture.envelope()
        with self.assertRaisesRegex(ValueError, "separate ledger"):
            self.probe()
        self.fixture.key_loader.assert_not_called()
        self.assertEqual(self.fixture.base.ledger.snapshot().charged_microusd, 40)

    async def test_expired_signed_decision_is_rejected(self):
        probe = self.probe()
        self.authorize(probe)
        assert self.signed is not None
        now = datetime.now(UTC)
        decision = self.signed.decision.model_copy(
            update={
                "issued_at": now - timedelta(seconds=2),
                "valid_until": now - timedelta(seconds=1),
            }
        )
        self.signed = sign_review_launch_decision(
            decision, "launch-reviewer", self.launch_key
        )
        with self.assertRaises(ValueError):
            await probe.run()
        self.assert_unspent()

    async def test_replacing_valid_decision_during_count_cannot_extend_admission(self):
        probe = self.probe()
        self.authorize(probe)
        original = self.signed

        async def count(_payload: dict[str, JsonValue]) -> int:
            self.authorize(probe)
            return 10

        with (
            patch.object(
                self.fixture.base.fake, "count_input_tokens", side_effect=count
            ),
            self.assertRaisesRegex(ValueError, "verified critic quorum"),
        ):
            await probe.run()
        self.assertEqual(self.fixture.key_loader.call_count, 1)
        self.assertEqual(self.fixture.sdk.call_count, 1)
        self.assertEqual(probe.launch_decision, original)
        self.assertNotEqual(self.signed, original)
        self.assertEqual(self.fixture.base.ledger.snapshot().charged_microusd, 650)
        self.assertEqual(self.fixture.judge.calls, [])

    async def test_changed_retained_decision_stops_generation(self):
        probe = self.probe()
        self.authorize(probe)
        original = self.fixture.base.fake.count_input_tokens

        async def count(payload: dict[str, JsonValue]) -> int:
            result = await original(payload)
            (self.fixture.directory / "launch-admission.json").write_bytes(b"changed")
            return result

        with (
            patch.object(
                self.fixture.base.fake, "count_input_tokens", side_effect=count
            ),
            self.assertRaises(ValueError),
        ):
            await probe.run()
        self.assertEqual(self.fixture.key_loader.call_count, 1)
        self.assertEqual(
            (self.fixture.directory / "launch-admission.json").read_bytes(), b"changed"
        )

    async def test_cancellation_awaits_worker_cleanup_and_cannot_retry(self):
        started = asyncio.Event()

        async def count(_payload: dict[str, JsonValue]) -> int:
            started.set()
            await asyncio.Future()
            return 10

        probe = self.probe()
        self.authorize(probe)
        with patch.object(
            self.fixture.base.fake, "count_input_tokens", side_effect=count
        ):
            task = asyncio.create_task(probe.run())
            await asyncio.wait_for(started.wait(), 15)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(self.fixture.base.ledger.snapshot().charged_microusd, 650)
        self.assertTrue(self.fixture.lifecycles)
        self.assertTrue(
            all((path / "result.json").is_file() for path in self.fixture.lifecycles)
        )
        with self.assertRaises(ValueError):
            await probe.run()
