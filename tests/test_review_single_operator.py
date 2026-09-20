"""Single-operator custody uses synthetic secrets and providers only."""

from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_review_approval_flow import ScriptedUser
from test_review_conformance_probe import ReviewProbeFixture

from mos_eisley.core.models import ReviewPolicy
from mos_eisley.run.review_conformance_admission import ReviewConformanceRuntime
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceScope,
    verify_review_conformance_authorization,
)
from mos_eisley.run.review_conformance_observation import (
    ReviewObservedExchange,
    ReviewProbeObservation,
)
from mos_eisley.run.review_conformance_probe import BrokeredReviewConformanceProbe
from mos_eisley.run.review_launch_authorization import (
    ReviewLaunchScope,
    verify_review_launch_decision,
)
from mos_eisley.run.review_single_operator import (
    MacOSKeychainOpenAICredential,
    ReviewOperatorFailure,
    SingleOperatorReviewHost,
)


class MemoryCredentialBackend:
    def __init__(self, value: str | None = "synthetic-review-key") -> None:
        self.value = value
        self.calls: list[tuple[str, str]] = []
        self.failure: Exception | None = None

    def get_password(self, service: str, username: str) -> str | None:
        self.calls.append((service, username))
        if self.failure is not None:
            raise self.failure
        return self.value


class SingleOperatorHostBoundaryTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 20, 2, tzinfo=UTC)
        self.backend = MemoryCredentialBackend()
        self.credential = MacOSKeychainOpenAICredential(
            "joshua-myers", backend=self.backend
        )
        self.host = SingleOperatorReviewHost(
            self.credential,
            clock=lambda: self.now,
            key_factory=lambda: Ed25519PrivateKey.from_private_bytes(b"k" * 32),
        )
        self.addCleanup(self.host.close)
        self.phase_policy = self.host.authority_policy(
            policy_id="joshua-live-review",
            valid_from=self.now - timedelta(seconds=1),
            valid_until=self.now + timedelta(minutes=5),
            max_authorization_seconds=60,
            max_reserved_microusd=5_000_000,
        )
        self.launch_policy = self.host.launch_policy(
            policy_id="joshua-live-review-launch",
            valid_from=self.now - timedelta(seconds=1),
            valid_until=self.now + timedelta(minutes=5),
            max_decision_seconds=60,
            max_reserved_microusd=5_000_000,
        )

    def phase_scope(self) -> ReviewConformanceScope:
        return ReviewConformanceScope(
            phase="critics",
            controller_sha256="a" * 64,
            critic_preview_sha256="b" * 64,
            phase_preview_sha256="b" * 64,
            start_sha256=None,
            guidance_sha256="c" * 64,
            ledger_id="d" * 64,
            ledger_policy_sha256="e" * 64,
            max_reserved_microusd=100,
            additional_reservation_microusd=100,
            sdk_version="3.11.0",
            image_id="sha256:" + "f" * 64,
            expires_at=self.now + timedelta(minutes=2),
        )

    def launch_scope(self) -> ReviewLaunchScope:
        return ReviewLaunchScope(
            schema_version=2,
            operator_mode="single_operator",
            launch_authority_policy_sha256=self.launch_policy.sha256,
            phase_authority_policy_sha256=self.phase_policy.sha256,
            configuration_sha256="1" * 64,
            critic_preview_sha256="2" * 64,
            seal_sha256="3" * 64,
            evidence_file_sha256="4" * 64,
            runtime=ReviewConformanceRuntime(
                sdk_version="3.11.0", image_id="sha256:" + "5" * 64
            ),
            ledger_path="/private/launch.sqlite",
            artifact_directory="/private/launch",
            max_reserved_microusd=100,
            expires_at=self.now + timedelta(minutes=2),
        )

    def observation(self) -> ReviewProbeObservation:
        exchange = ReviewObservedExchange(
            model_request_sha256="6" * 64,
            count_started_at=self.now,
            count_finished_at=self.now,
            generation_started_at=self.now,
            generation_finished_at=self.now,
            transport_evidence_sha256="7" * 64,
            cleanup_evidence_sha256="8" * 64,
        )
        return ReviewProbeObservation(
            schema_version=2,
            operator_mode="single_operator",
            observation_policy_sha256="9" * 64,
            authority_policy_sha256=self.phase_policy.sha256,
            critic_preview_sha256="a" * 64,
            controller_start_sha256="b" * 64,
            judge_preview_sha256="c" * 64,
            critic_authorization_sha256="d" * 64,
            judge_authorization_sha256="e" * 64,
            result_sha256="f" * 64,
            exchanges=(exchange, exchange),
            observed_at=self.now,
            charged_microusd=10,
        )

    def test_construction_exposes_one_public_identity_without_keychain_access(self):
        signer = self.host.signer
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.phase_policy.authorities, (signer,))
        self.assertEqual(self.phase_policy.observers, (signer,))
        self.assertEqual(self.launch_policy.reviewers, (signer,))
        self.assertNotIn("synthetic-review-key", repr(self.host))
        self.assertNotIn("joshua-myers", repr(self.credential))

    def test_keychain_load_is_late_uncached_and_owner_bound(self):
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.host.load_api_key(), "synthetic-review-key")
        self.assertEqual(self.host.load_api_key(), "synthetic-review-key")
        self.assertEqual(len(self.backend.calls), 2)
        with (
            patch(
                "mos_eisley.run.review_single_operator.os.geteuid",
                return_value=999_999,
            ),
            self.assertRaisesRegex(ReviewOperatorFailure, "owner changed"),
        ):
            self.host.load_api_key()
        self.assertEqual(len(self.backend.calls), 2)

    def test_keychain_failures_are_fixed_and_redacted(self):
        for value in (None, "short", "synthetic-review-key\n", "sëcret-value"):
            self.backend.value = value
            with self.assertRaises(ReviewOperatorFailure) as raised:
                self.host.load_api_key()
            self.assertNotIn(str(value), str(raised.exception))
        self.backend.failure = RuntimeError("synthetic-review-key")
        with self.assertRaises(ReviewOperatorFailure) as raised:
            self.host.load_api_key()
        self.assertNotIn("synthetic-review-key", str(raised.exception))

    def test_close_revokes_signing_and_credential_callbacks(self):
        self.host.close()
        self.assertTrue(self.host.closed)
        for operation in (lambda: self.host.signer, self.host.load_api_key):
            with self.assertRaisesRegex(ReviewOperatorFailure, "closed"):
                operation()
        self.assertEqual(self.backend.calls, [])

    async def test_explicit_phase_and_launch_signatures_verify(self):
        scope = self.phase_scope()
        signed_phase = await self.host.authorize_phase(
            scope, self.phase_policy, lifetime_seconds=60
        )
        verified_phase = verify_review_conformance_authorization(
            signed_phase, self.phase_policy, scope, self.now
        )
        self.assertEqual(verified_phase.operator_mode, "single_operator")

        launch_scope = self.launch_scope()
        signed_launch = self.host.authorize_launch(
            launch_scope,
            self.launch_policy,
            lifetime_seconds=60,
            commitment_custody_reviewed=True,
            credentialed_campaign_reviewed=True,
            self_review_risk_accepted=True,
        )
        verified_launch = verify_review_launch_decision(
            signed_launch, self.launch_policy, launch_scope, self.now
        )
        self.assertTrue(verified_launch.single_operator_self_review_risk_accepted)
        self.assertEqual(
            signed_phase.public_key_sha256, signed_launch.public_key_sha256
        )
        self.assertEqual(self.backend.calls, [])

    def test_observation_and_launch_require_explicit_self_review(self):
        with self.assertRaisesRegex(ReviewOperatorFailure, "self-assessment"):
            self.host.sign_observation(
                self.observation(), self.phase_policy, claims_reviewed=False
            )
        signed = self.host.sign_observation(
            self.observation(), self.phase_policy, claims_reviewed=True
        )
        self.assertEqual(signed.signer_id, "joshua-myers")
        with self.assertRaisesRegex(ReviewOperatorFailure, "every.*assertion"):
            self.host.authorize_launch(
                self.launch_scope(),
                self.launch_policy,
                lifetime_seconds=60,
                commitment_custody_reviewed=True,
                credentialed_campaign_reviewed=True,
                self_review_risk_accepted=False,
            )

    async def test_host_rejects_another_single_operator_key(self):
        other = SingleOperatorReviewHost(
            self.credential,
            key_factory=lambda: Ed25519PrivateKey.from_private_bytes(b"z" * 32),
        )
        self.addCleanup(other.close)
        other_phase = other.authority_policy(
            policy_id="other",
            valid_from=self.now - timedelta(seconds=1),
            valid_until=self.now + timedelta(minutes=5),
            max_authorization_seconds=60,
            max_reserved_microusd=5_000_000,
        )
        other_launch = other.launch_policy(
            policy_id="other-launch",
            valid_from=self.now - timedelta(seconds=1),
            valid_until=self.now + timedelta(minutes=5),
            max_decision_seconds=60,
            max_reserved_microusd=5_000_000,
        )
        with self.assertRaisesRegex(ReviewOperatorFailure, "owning operator"):
            await self.host.authorize_phase(
                self.phase_scope(), other_phase, lifetime_seconds=60
            )
        with self.assertRaisesRegex(ReviewOperatorFailure, "owning operator"):
            self.host.sign_observation(
                self.observation(), other_phase, claims_reviewed=True
            )
        with self.assertRaisesRegex(ReviewOperatorFailure, "owning operator"):
            self.host.authorize_launch(
                self.launch_scope(),
                other_launch,
                lifetime_seconds=60,
                commitment_custody_reviewed=True,
                credentialed_campaign_reviewed=True,
                self_review_risk_accepted=True,
            )


class SingleOperatorHostProbeTests(ReviewProbeFixture, IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.backend = MemoryCredentialBackend()
        credential = MacOSKeychainOpenAICredential("joshua-myers", backend=self.backend)
        self.host = SingleOperatorReviewHost(credential)
        self.addCleanup(self.host.close)
        self.policy = self.host.authority_policy(
            policy_id="joshua-probe",
            valid_from=self.timestamp - timedelta(minutes=1),
            valid_until=self.timestamp + timedelta(minutes=5),
            max_authorization_seconds=60,
            max_reserved_microusd=1000,
        )

    async def load_authorization(self, scope: ReviewConformanceScope):
        return await self.host.authorize_phase(scope, self.policy, lifetime_seconds=20)

    def host_probe(self, user: ScriptedUser) -> BrokeredReviewConformanceProbe:
        probe = BrokeredReviewConformanceProbe(
            self.review,
            self.base.reviewer,
            ReviewPolicy(min_critics=1, min_providers=1),
            user,
            critic_containers=(self.base.container,),
            judge_container=self.base.container,
            authority_policy=lambda: self.policy,
            load_authorization=self.load_authorization,
            load_api_key=self.host.load_api_key,
        )
        self.controller = probe.controller
        self.preview = self.controller.preview
        self.runtime = ReviewConformanceRuntime(
            sdk_version=version("openai"), image_id=self.base.container.image_id
        )
        return probe

    async def test_existing_probe_loads_keychain_only_after_both_approvals(self):
        probe = self.host_probe(ScriptedUser(("approve", "approve")))
        self.assertEqual(self.backend.calls, [])
        result = await probe.run()
        self.assertIsNotNone(result)
        self.assertEqual(len(self.backend.calls), 4)
        self.assertEqual(len(probe.approval_ui.authorizations), 2)
        for path in self.directory.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"synthetic-review-key", path.read_bytes())

    async def test_decline_never_reads_keychain(self):
        result = await self.host_probe(ScriptedUser(("decline",))).run()
        self.assertIsNone(result)
        self.assertEqual(self.backend.calls, [])
