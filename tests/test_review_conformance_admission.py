"""Independent signatures bind exact review phases without certifying conformance."""

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_openai_spend import FakeTransport
from test_review_approval_flow import ScriptedUser
from test_review_broker_admission import output
from test_review_guidance_admission import GuidedBrokerFixture

from mos_eisley.core.models import (
    Critique,
    JudgeDecision,
    ReviewPolicy,
    canonical_bytes,
)
from mos_eisley.run.review_approval import ApprovalPreview, BrokeredReviewApprovalFlow
from mos_eisley.run.review_conformance_admission import (
    ReviewConformanceRuntime,
    SignedReviewApprovalUI,
)
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceAuthorityPolicy,
    ReviewConformanceScope,
    SignedReviewConformanceAuthorization,
    make_review_conformance_authorization,
    review_conformance_scope,
    review_conformance_signer,
    sign_review_conformance_authorization,
    verify_review_conformance_authorization,
)
from mos_eisley.run.review_controller import (
    BrokeredReviewController,
)


class ReviewConformanceTests(GuidedBrokerFixture, IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.review = self.envelope()
        self.controller = BrokeredReviewController(
            self.review,
            self.base.reviewer,
            ReviewPolicy(min_critics=1, min_providers=1),
            total_seconds=30,
        )
        self.preview = self.controller.preview
        self.directory = Path(self.review.envelope.artifact_directory)
        self.base.fake.directory = (
            self.directory / self.call.authorization.ledger_entry_id
        )
        self.base.fake.response = output(canonical_bytes(Critique()).decode())
        self.judge = FakeTransport(self.directory / "judge")
        self.judge.response = output(
            canonical_bytes(JudgeDecision(upheld=(), rationale="Fixture")).decode()
        )
        self.timestamp = datetime.now(UTC)
        self.key = Ed25519PrivateKey.from_private_bytes(b"a" * 32)
        self.observer_key = Ed25519PrivateKey.from_private_bytes(b"b" * 32)
        self.policy = ReviewConformanceAuthorityPolicy(
            policy_id="fixture",
            authorities=(
                review_conformance_signer("authority", self.key.public_key()),
            ),
            observers=(
                review_conformance_signer("observer", self.observer_key.public_key()),
            ),
            valid_from=self.timestamp - timedelta(minutes=1),
            valid_until=self.timestamp + timedelta(minutes=5),
            max_authorization_seconds=60,
            max_reserved_microusd=1000,
        )
        self.runtime = ReviewConformanceRuntime(
            sdk_version="2.54.0", image_id="sha256:" + "a" * 64
        )
        self.scope = review_conformance_scope(self.preview, **self.runtime.model_dump())

    def certificate(self, scope: ReviewConformanceScope | None = None):
        selected = self.scope if scope is None else scope
        authorization = make_review_conformance_authorization(
            selected,
            self.policy,
            self.timestamp,
            min(self.timestamp + timedelta(seconds=20), selected.expires_at),
        )
        return sign_review_conformance_authorization(
            authorization, "authority", self.key
        )

    async def load_certificate(self, scope: ReviewConformanceScope):
        return self.certificate(scope)

    def admission_ui(self, user: ScriptedUser):
        return SignedReviewApprovalUI(
            self.preview,
            user,
            authority_policy=lambda: self.policy,
            runtime=lambda: self.runtime,
            controller_start=lambda: self.controller.start,
            load_authorization=self.load_certificate,
            now=lambda: self.timestamp,
        )

    async def run_flow(self, ui: SignedReviewApprovalUI):
        return await BrokeredReviewApprovalFlow(self.controller, ui).run(
            critic_transports=(self.base.fake,),
            critic_containers=(self.base.container,),
            judge_transport=self.judge,
            judge_container=self.base.container,
        )

    def test_signature_verification_is_read_only_and_not_conformance_evidence(self):
        signed = self.certificate()
        before = self.base.ledger.path.read_bytes()
        verified = verify_review_conformance_authorization(
            signed, self.policy, self.scope, self.timestamp
        )
        self.assertEqual(verified, signed.authorization)
        self.assertTrue(verified.explicit_local_consent_also_required)
        self.assertFalse(verified.conformance_proven)
        self.assertFalse(verified.live_review_activation_authorized)
        self.assertEqual(before, self.base.ledger.path.read_bytes())
        self.assertFalse(self.directory.exists())

    def test_authorizer_and_observer_identity_and_key_must_be_disjoint(self):
        for observer in (
            self.policy.authorities[0],
            self.policy.authorities[0].model_copy(update={"signer_id": "observer"}),
        ):
            broken = self.policy.model_copy(update={"observers": (observer,)})
            with (
                self.subTest(observer=observer.signer_id),
                self.assertRaises(ValueError),
            ):
                ReviewConformanceAuthorityPolicy.model_validate_json(
                    canonical_bytes(broken)
                )

    def test_observer_signature_cannot_authorize_a_probe(self):
        signed = sign_review_conformance_authorization(
            self.certificate().authorization, "observer", self.observer_key
        )
        with self.assertRaisesRegex(ValueError, "not enrolled"):
            verify_review_conformance_authorization(
                signed, self.policy, self.scope, self.timestamp
            )

    def test_each_runtime_content_and_spending_binding_is_exact(self):
        signed = self.certificate()
        substitutions = (
            {"sdk_version": "2.54.1"},
            {"image_id": "sha256:" + "f" * 64},
            {"controller_sha256": "f" * 64},
            {"guidance_sha256": "f" * 64},
            {"ledger_id": "f" * 64},
            {"ledger_policy_sha256": "f" * 64},
            {"critic_preview_sha256": "f" * 64, "phase_preview_sha256": "f" * 64},
            {"max_reserved_microusd": 651, "additional_reservation_microusd": 651},
        )
        for changes in substitutions:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                verify_review_conformance_authorization(
                    signed,
                    self.policy,
                    self.scope.model_copy(update=changes),
                    self.timestamp,
                )

    def test_policy_revision_invalidates_an_old_signature(self):
        with self.assertRaises(ValueError):
            verify_review_conformance_authorization(
                self.certificate(),
                self.policy.model_copy(update={"policy_id": "revised"}),
                self.scope,
                self.timestamp,
            )

    def test_expiration_is_exclusive_and_future_and_naive_times_reject(self):
        signed = self.certificate()
        for now in (
            signed.authorization.valid_until,
            self.timestamp - timedelta(seconds=1),
            self.timestamp.replace(tzinfo=None),
        ):
            with self.subTest(now=now), self.assertRaises(ValueError):
                verify_review_conformance_authorization(
                    signed, self.policy, self.scope, now
                )

    def test_lifetime_spending_and_envelope_expiry_bound_unsigned_authorization(self):
        for policy, expiry in (
            (self.policy, self.timestamp + timedelta(seconds=61)),
            (
                self.policy.model_copy(update={"max_reserved_microusd": 649}),
                self.timestamp + timedelta(seconds=10),
            ),
            (self.policy, self.scope.expires_at + timedelta(seconds=1)),
        ):
            with self.subTest(expiry=expiry), self.assertRaises(ValueError):
                make_review_conformance_authorization(
                    self.scope, policy, self.timestamp, expiry
                )

    def test_bad_signature_and_other_signing_domain_reject(self):
        signed = self.certificate()
        for signature in (
            b"\x00" * 64,
            self.key.sign(b"other-domain\x00" + canonical_bytes(signed.authorization)),
        ):
            changed = signed.model_copy(
                update={"signature_base64": base64.b64encode(signature).decode()}
            )
            with self.subTest(signature=signature[:2]), self.assertRaises(ValueError):
                verify_review_conformance_authorization(
                    changed, self.policy, self.scope, self.timestamp
                )

    def test_evaluation_authorization_mode_cannot_be_substituted(self):
        record = json.loads(canonical_bytes(self.certificate()))
        record["authorization"]["mode"] = "evaluation_conformance_authorization"
        with self.assertRaises(ValueError):
            SignedReviewConformanceAuthorization.model_validate_json(json.dumps(record))

    async def test_two_independent_signatures_and_local_approvals_complete_fixture(
        self,
    ):
        user = ScriptedUser(("approve", "approve"))
        ui = self.admission_ui(user)
        result = await self.run_flow(ui)
        assert result is not None
        self.assertEqual(result.result.verdict.decision, "accept")
        self.assertEqual(len(ui.authorizations), 2)
        first, second = (s.authorization.scope for s in ui.authorizations)
        self.assertEqual((first.phase, second.phase), ("critics", "judge"))
        self.assertEqual(first.additional_reservation_microusd, 650)
        self.assertEqual(second.additional_reservation_microusd, 0)
        self.assertEqual(second.max_reserved_microusd, 325)
        self.assertIsNotNone(second.start_sha256)
        self.assertNotEqual(first.phase_preview_sha256, second.phase_preview_sha256)
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 40)

    async def test_critic_signature_cannot_be_reused_for_judge(self):
        signed = self.certificate()
        user = ScriptedUser(("approve",))
        with (
            patch.object(self, "load_certificate", return_value=signed),
            self.assertRaisesRegex(ValueError, "scope changed"),
        ):
            await self.run_flow(self.admission_ui(user))
        self.assertEqual(len(user.previews), 1)
        self.assertEqual(self.judge.calls, [])
        self.assertEqual(self.base.ledger.snapshot().charged_microusd, 345)

    async def test_local_decline_does_not_become_approval_from_a_valid_signature(self):
        user = ScriptedUser(("decline",))
        ui = self.admission_ui(user)
        self.assertIsNone(await self.run_flow(ui))
        self.assertEqual(ui.authorizations, ())
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    async def test_missing_signature_does_not_prompt_or_reserve(self):
        user = ScriptedUser(())
        with patch.object(self, "load_certificate", return_value=None):
            self.assertIsNone(await self.run_flow(self.admission_ui(user)))
        self.assertEqual(user.previews, [])
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    async def test_expiry_during_local_prompt_invalidates_approval(self):
        user = ScriptedUser(())

        async def delayed(preview: ApprovalPreview) -> str:
            self.timestamp += timedelta(seconds=30)
            return preview.sha256

        with (
            patch.object(user, "approve", side_effect=delayed),
            self.assertRaises(ValueError),
        ):
            await self.run_flow(self.admission_ui(user))
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    async def test_policy_change_during_prompt_invalidates_approval(self):
        user = ScriptedUser(())

        async def changed(preview: ApprovalPreview) -> str:
            self.policy = self.policy.model_copy(update={"policy_id": "revoked"})
            return preview.sha256

        with (
            patch.object(user, "approve", side_effect=changed),
            self.assertRaises(ValueError),
        ):
            await self.run_flow(self.admission_ui(user))
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    async def test_runtime_change_during_prompt_invalidates_approval(self):
        user = ScriptedUser(())

        async def changed(preview: ApprovalPreview) -> str:
            self.runtime = self.runtime.model_copy(update={"sdk_version": "different"})
            return preview.sha256

        with (
            patch.object(user, "approve", side_effect=changed),
            self.assertRaises(ValueError),
        ):
            await self.run_flow(self.admission_ui(user))
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    async def test_current_guidance_still_blocks_an_independently_signed_attempt(self):
        user = ScriptedUser(())

        async def changed(preview: ApprovalPreview) -> str:
            self.invalidate()
            return preview.sha256

        with (
            patch.object(user, "approve", side_effect=changed),
            self.assertRaises(ValueError),
        ):
            await self.run_flow(self.admission_ui(user))
        self.assertEqual(self.base.ledger.snapshot().entries, 0)

    def test_judge_scope_cannot_claim_a_new_reservation(self):
        broken = self.scope.model_copy(
            update={"phase": "judge", "start_sha256": "f" * 64}
        )
        with self.assertRaises(ValueError):
            ReviewConformanceScope.model_validate_json(canonical_bytes(broken))
