"""Fixed-tranche review acceptance uses synthetic probes and independent test keys."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from test_review_runtime_evidence import RuntimeEvidenceFixture

from mos_eisley.core.models import JudgeRequest, canonical_bytes, digest
from mos_eisley.run.review_conformance_acceptance import (
    ReviewAcceptancePolicy,
    ReviewAttemptCommitment,
    ReviewAttemptEvidence,
    evaluate_review_conformance,
    review_role_profile,
)
from mos_eisley.run.review_conformance_observation import (
    ReviewObservationPolicy,
    make_review_probe_observation,
    sign_review_probe_observation,
)
from mos_eisley.run.review_runtime_evidence import collect_review_runtime_exchange
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerSettlement


class ReviewAcceptanceFixture(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.fixtures: list[RuntimeEvidenceFixture] = []
        for _ in range(3):
            fixture = RuntimeEvidenceFixture()
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
            self.fixtures.append(fixture)
        if self._testMethodName == "test_shared_ledger_counts_each_attempt_once":
            for fixture in self.fixtures[1:]:
                fixture.base.ledger = self.fixtures[0].base.ledger
                fixture.call = fixture.prepare()
                fixture.review = fixture.envelope()
                fixture.base.fake.directory = fixture.critic_directory()
        probes = [fixture.probe() for fixture in self.fixtures]
        observation_policies = [
            ReviewObservationPolicy(
                policy_id=f"fixture-{index}",
                authority_policy_sha256=fixture.policy.sha256,
                critic_preview_sha256=digest(canonical_bytes(fixture.preview)),
                valid_from=fixture.policy.valid_from,
                valid_until=fixture.policy.valid_until,
                max_observation_age_seconds=600,
            )
            for index, fixture in enumerate(self.fixtures)
        ]
        first = self.fixtures[0]
        self.policy = ReviewAcceptancePolicy(
            policy_id="fixture-tranche",
            committed_at=datetime.now(UTC),
            valid_until=datetime.now(UTC) + timedelta(minutes=5),
            max_observation_age_seconds=600,
            runtime=first.runtime,
            review_policy=first.controller.authorization.policy,
            total_seconds=first.controller.authorization.total_seconds,
            critics=tuple(
                review_role_profile(request, call.critic_sha256)
                for request, call in zip(
                    first.preview.requests, first.preview.envelope.critics, strict=True
                )
            ),
            judge=review_role_profile(
                first.base.reviewer.judge_request(
                    JudgeRequest(brief=first.guided.prepared.brief, findings=())
                )
            ),
            attempts=tuple(
                ReviewAttemptCommitment(
                    critic_preview_sha256=digest(canonical_bytes(fixture.preview)),
                    observation_policy_sha256=digest(
                        canonical_bytes(observation_policy)
                    ),
                    authority_policy_sha256=fixture.policy.sha256,
                )
                for fixture, observation_policy in zip(
                    self.fixtures, observation_policies, strict=True
                )
            ),
        )
        self.before_attempts(observation_policies)
        self.evidence: list[ReviewAttemptEvidence] = []
        for index, (fixture, probe, observation_policy) in enumerate(
            zip(self.fixtures, probes, observation_policies, strict=True)
        ):
            fixture.base.fake.response["id"] = f"fixture-critic-{index}"
            if self._testMethodName == "test_duplicate_provider_response_is_rejected":
                fixture.base.fake.response["id"] = "repeated-response"
            fixture.judge.response["id"] = f"fixture-judge-{index}"
            with patch(
                "mos_eisley.run.review_conformance_probe.EphemeralOpenAITransport",
                fixture.sdk,
            ):
                result = await probe.run()
            assert (
                result is not None
                and probe.judge_preview is not None
                and probe.controller.start is not None
            )
            critic_signed, judge_signed = probe.approval_ui.authorizations
            signatures = (critic_signed, judge_signed)
            directories = (fixture.critic_directory(), fixture.directory / "judge")
            exchanges = tuple(
                collect_review_runtime_exchange(
                    directory, lifecycle, request, signature.authorization
                )
                for directory, lifecycle, request, signature in zip(
                    directories,
                    fixture.lifecycles,
                    (*fixture.preview.requests, probe.judge_preview.model_request),
                    signatures,
                    strict=True,
                )
            )
            result_sha = digest(canonical_bytes(result))
            observation = make_review_probe_observation(
                observation_policy,
                fixture.policy,
                fixture.preview,
                probe.controller.start,
                probe.judge_preview,
                signatures,
                fixture.base.reviewer,
                fixture.base.ledger,
                expected_result_sha256=result_sha,
                exchanges=exchanges,
                observed_at=datetime.now(UTC),
            )
            signed = sign_review_probe_observation(
                observation, "observer", fixture.observer_key
            )
            self.evidence.append(
                ReviewAttemptEvidence(
                    observation_policy=observation_policy,
                    authority_policy=fixture.policy,
                    critics=fixture.preview,
                    start=probe.controller.start,
                    judge=probe.judge_preview,
                    authorizations=signatures,
                    signed_observation=signed,
                    expected_result_sha256=result_sha,
                    lifecycle_directories=tuple(fixture.lifecycles),
                    reviewer=fixture.base.reviewer,
                    ledger=fixture.base.ledger,
                )
            )
        self.now = datetime.now(UTC)

    def before_attempts(
        self, observation_policies: list[ReviewObservationPolicy]
    ) -> None:
        pass

    def evaluate(self):
        return evaluate_review_conformance(
            self.policy, tuple(self.evidence), now=self.now
        )


class ReviewAcceptanceTests(ReviewAcceptanceFixture):
    def test_three_precommitted_verified_probes_accept_only_exact_profile(self):
        before = [fixture.base.ledger.path.read_bytes() for fixture in self.fixtures]
        result = self.evaluate()
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.qualifying_attempts, 3)
        self.assertFalse(result.live_review_activation_authorized)
        self.assertFalse(result.provider_dispatch_authorized)
        self.assertFalse(result.retry_authorized)
        self.assertFalse(result.provider_authorship_proven)
        self.assertFalse(result.billing_reconciled)
        self.assertEqual(
            before, [fixture.base.ledger.path.read_bytes() for fixture in self.fixtures]
        )
        self.assertEqual(self.evaluate(), result)

    def test_missing_slot_stays_incomplete(self):
        result = evaluate_review_conformance(
            self.policy, (self.evidence[0], None, self.evidence[2]), now=self.now
        )
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(result.qualifying_attempts, 2)

    def test_shared_ledger_counts_each_attempt_once(self):
        self.assertEqual(self.evaluate().status, "accepted")
        snapshot = self.fixtures[0].base.ledger.snapshot()
        self.assertEqual(snapshot.entries, 9)
        self.assertEqual(snapshot.charged_microusd, 120)

    def test_omitted_slot_cannot_shorten_the_tranche(self):
        with self.assertRaisesRegex(ValueError, "all three"):
            evaluate_review_conformance(
                self.policy, tuple(self.evidence[:2]), now=self.now
            )

    def test_repeated_record_cannot_replace_committed_attempt(self):
        self.evidence[1] = self.evidence[0]
        with self.assertRaisesRegex(ValueError, "commitment"):
            self.evaluate()

    def test_post_outcome_commitment_is_rejected(self):
        self.policy = self.policy.model_copy(update={"committed_at": self.now})
        with self.assertRaisesRegex(ValueError, "chronology"):
            self.evaluate()

    def test_runtime_and_quorum_substitution_cannot_expand_acceptance(self):
        original = self.policy
        for change in (
            {
                "runtime": self.policy.runtime.model_copy(
                    update={"image_id": "sha256:" + "f" * 64}
                )
            },
            {
                "review_policy": self.policy.review_policy.model_copy(
                    update={"min_critics": 2}
                )
            },
            {"judge": self.policy.judge.model_copy(update={"effort": "low"})},
        ):
            self.policy = original.model_copy(update=change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.evaluate()

    def test_runtime_tampering_blocks_even_valid_observer_signature(self):
        path = self.fixtures[0].critic_directory() / "runtime-count-end.json"
        path.write_bytes(b"{}")
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_wrong_cleanup_selection_is_rejected(self):
        self.evidence[0] = replace(
            self.evidence[0],
            lifecycle_directories=self.evidence[1].lifecycle_directories,
        )
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_unexplained_ledger_entry_blocks_acceptance_even_if_settled_zero(self):
        ledger = self.fixtures[0].base.ledger
        entry = LedgerEntry(
            entry_id="f" * 64, reservation_sha256="e" * 64, reserved_microusd=1
        )
        ledger.reserve(entry)
        ledger.settle(
            LedgerSettlement(
                entry_id=entry.entry_id,
                reservation_sha256=entry.reservation_sha256,
                status="settled",
                charged_microusd=0,
            )
        )
        with self.assertRaisesRegex(ValueError, "unexplained exposure"):
            self.evaluate()

    def test_uncertain_ledger_exposure_blocks_acceptance(self):
        ledger = self.fixtures[0].base.ledger
        ledger.reserve(
            LedgerEntry(
                entry_id="f" * 64, reservation_sha256="e" * 64, reserved_microusd=1
            )
        )
        with self.assertRaisesRegex(ValueError, "unexplained exposure"):
            self.evaluate()

    def test_expired_policy_and_naive_clock_are_rejected(self):
        for now in (self.policy.valid_until, self.now.replace(tzinfo=None)):
            with self.assertRaises(ValueError):
                evaluate_review_conformance(self.policy, tuple(self.evidence), now=now)

    def test_duplicate_commitments_are_invalid(self):
        broken = self.policy.model_copy(
            update={"attempts": (self.policy.attempts[0],) * 3}
        )
        with self.assertRaisesRegex(ValueError, "distinct committed"):
            ReviewAcceptancePolicy.model_validate_json(canonical_bytes(broken))

    def test_duplicate_provider_response_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "distinct responses"):
            self.evaluate()
