"""Synthetic observer signatures authenticate provenance without live claims."""

import base64
import json
from datetime import UTC, datetime, timedelta
from unittest import IsolatedAsyncioTestCase

from test_review_broker_admission import output
from test_review_conformance_probe import ReviewProbeFixture

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.review_conformance_observation import (
    ReviewObservationPolicy,
    ReviewObservedExchange,
    SignedReviewProbeObservation,
    authenticate_review_probe,
    make_review_probe_observation,
    sign_review_probe_observation,
)


class ReviewObservationTests(ReviewProbeFixture, IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        invalid_judge = (
            self._testMethodName == "test_invalid_judge_cannot_certify_success"
        )
        if invalid_judge:
            self.judge.response = output("not-json")
        self.run_probe = self.probe()
        self.observation_policy = ReviewObservationPolicy(
            policy_id="fixture-observation",
            authority_policy_sha256=self.policy.sha256,
            critic_preview_sha256=digest(canonical_bytes(self.preview)),
            valid_from=self.timestamp,
            valid_until=self.timestamp + timedelta(minutes=5),
            max_observation_age_seconds=600,
        )
        result = await self.run_probe.run()
        assert result is not None
        self.result_sha = digest(canonical_bytes(result))
        start = self.run_probe.controller.start
        judge = self.run_probe.judge_preview
        assert start is not None and judge is not None
        self.start = start
        self.judge_preview = judge
        self.observed_at = datetime.now(UTC)
        signed_critic, signed_judge = self.run_probe.approval_ui.authorizations
        self.authorizations = (signed_critic, signed_judge)
        # These timestamps and evidence pins are explicitly synthetic observer
        # inputs. Unit tests never manufacture a production observation record.
        self.exchanges: tuple[ReviewObservedExchange, ...] = tuple(
            ReviewObservedExchange(
                model_request_sha256=digest(canonical_bytes(request)),
                count_started_at=start.started_at + timedelta(milliseconds=index * 4),
                count_finished_at=start.started_at
                + timedelta(milliseconds=index * 4 + 1),
                generation_started_at=start.started_at
                + timedelta(milliseconds=index * 4 + 2),
                generation_finished_at=start.started_at
                + timedelta(milliseconds=index * 4 + 3),
                transport_evidence_sha256=digest(f"fixture-transport-{index}".encode()),
                cleanup_evidence_sha256=digest(f"fixture-cleanup-{index}".encode()),
            )
            for index, request in enumerate(
                (*self.preview.requests, judge.model_request)
            )
        )
        if invalid_judge:
            return
        self.observation = self.make_observation()
        self.signed = sign_review_probe_observation(
            self.observation, "observer", self.observer_key
        )

    def make_observation(self):
        return make_review_probe_observation(
            self.observation_policy,
            self.policy,
            self.preview,
            self.start,
            self.judge_preview,
            self.authorizations,
            self.base.reviewer,
            self.base.ledger,
            expected_result_sha256=self.result_sha,
            exchanges=self.exchanges,
            observed_at=self.observed_at,
        )

    def authenticate(self, now: datetime | None = None):
        return authenticate_review_probe(
            self.signed,
            self.observation_policy,
            self.policy,
            self.preview,
            self.start,
            self.judge_preview,
            self.authorizations,
            self.base.reviewer,
            self.base.ledger,
            expected_result_sha256=self.result_sha,
            now=self.observed_at if now is None else now,
        )

    def test_authentication_is_read_only_and_grants_no_new_authority(self):
        before = {p: p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}
        ledger = self.base.ledger.path.read_bytes()
        verified = self.authenticate()
        self.assertTrue(verified.observer_authenticated)
        self.assertTrue(verified.local_artifacts_verified)
        self.assertFalse(verified.provider_authorship_proven)
        self.assertFalse(verified.billing_reconciled)
        self.assertFalse(verified.repeated_conformance_proven)
        self.assertFalse(verified.live_review_activation_authorized)
        self.assertFalse(verified.retry_authorized)
        self.assertEqual(
            before,
            {p: p.read_bytes() for p in self.directory.rglob("*") if p.is_file()},
        )
        self.assertEqual(ledger, self.base.ledger.path.read_bytes())
        self.assertEqual(self.authenticate(), verified)
        self.assertEqual(self.key_loader.call_count, 4)

    def test_invalid_judge_cannot_certify_success(self):
        with self.assertRaisesRegex(ValueError, "successful critics and judge"):
            self.make_observation()

    def test_authorizer_cannot_act_as_observer(self):
        self.signed = sign_review_probe_observation(
            self.observation, "authority", self.key
        )
        with self.assertRaisesRegex(ValueError, "independently enrolled"):
            self.authenticate()

    def test_changed_observer_key_is_rejected(self):
        self.signed = sign_review_probe_observation(
            self.observation, "observer", self.key
        )
        with self.assertRaisesRegex(ValueError, "independently enrolled"):
            self.authenticate()

    def test_modified_observation_fails_signature(self):
        self.signed = self.signed.model_copy(
            update={
                "observation": self.observation.model_copy(
                    update={"charged_microusd": 0}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "signature"):
            self.authenticate()

    def test_wrong_signature_domain_is_rejected(self):
        wrong = self.observer_key.sign(
            b"evaluation" + canonical_bytes(self.observation)
        )
        self.signed = self.signed.model_copy(
            update={"signature_base64": base64.b64encode(wrong).decode("ascii")}
        )
        with self.assertRaisesRegex(ValueError, "signature"):
            self.authenticate()

    def test_valid_signature_cannot_override_reconstructed_spending(self):
        self.signed = sign_review_probe_observation(
            self.observation.model_copy(update={"charged_microusd": 0}),
            "observer",
            self.observer_key,
        )
        with self.assertRaisesRegex(ValueError, "reconstructed evidence"):
            self.authenticate()

    def test_observation_policy_substitution_is_rejected(self):
        self.observation_policy = self.observation_policy.model_copy(
            update={"policy_id": "replacement"}
        )
        with self.assertRaisesRegex(ValueError, "reconstructed evidence"):
            self.authenticate()

    def test_authority_policy_substitution_is_rejected(self):
        self.policy = self.policy.model_copy(update={"policy_id": "replacement"})
        with self.assertRaisesRegex(ValueError, "selected policy"):
            self.authenticate()

    def test_historical_authorization_expiry_does_not_grant_new_dispatch(self):
        result = self.authenticate(self.observed_at + timedelta(seconds=120))
        self.assertFalse(result.retry_authorized)
        self.assertFalse(result.live_review_activation_authorized)

    def test_future_stale_and_naive_verification_clocks_are_rejected(self):
        for now in (
            self.observed_at - timedelta(microseconds=1),
            self.observed_at + timedelta(seconds=601),
            self.observed_at.replace(tzinfo=None),
        ):
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.authenticate(now)

    def test_exchange_outside_its_signed_window_is_rejected(self):
        late = self.authorizations[0].authorization.valid_until
        self.exchanges = (
            self.exchanges[0].model_copy(
                update={
                    "count_started_at": late,
                    "count_finished_at": late,
                    "generation_started_at": late,
                    "generation_finished_at": late,
                }
            ),
            self.exchanges[1],
        )
        self.observed_at = late + timedelta(seconds=1)
        with self.assertRaises(ValueError):
            self.make_observation()

    def test_missing_or_reordered_exchanges_are_rejected(self):
        original = self.exchanges
        for exchanges in (original[:1], tuple(reversed(original))):
            self.exchanges = exchanges
            with self.assertRaises(ValueError):
                self.make_observation()

    def test_reused_supporting_evidence_is_rejected(self):
        self.exchanges = (
            self.exchanges[0],
            self.exchanges[1].model_copy(
                update={
                    "cleanup_evidence_sha256": self.exchanges[
                        0
                    ].cleanup_evidence_sha256,
                }
            ),
        )
        with self.assertRaisesRegex(ValueError, "distinct per-call evidence"):
            self.make_observation()

    def test_result_pin_and_local_tampering_are_rejected(self):
        result_path = self.directory / "review-result.json"
        result_path.write_bytes(result_path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.authenticate()

    def test_response_tampering_is_rejected_even_with_original_result(self):
        response = next(self.directory.rglob("broker-response.json"))
        response.write_bytes(response.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.authenticate()

    def test_missing_terminal_record_cannot_be_observed_as_completed(self):
        (self.directory / "controller-terminal.json").rename(
            self.directory / "hidden-terminal"
        )
        with self.assertRaisesRegex(ValueError, "completed, settled"):
            self.authenticate()

    def test_evaluation_observation_mode_cannot_be_substituted(self):
        raw = json.loads(canonical_bytes(self.signed))
        raw["observation"]["mode"] = "brokered_evaluation_conformance_observation"
        with self.assertRaises(ValueError):
            SignedReviewProbeObservation.model_validate_json(json.dumps(raw))
