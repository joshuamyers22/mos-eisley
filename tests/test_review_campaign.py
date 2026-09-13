"""Operator ceremony is offline, hash-confirmed and read-only after sealing."""

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from test_review_conformance_acceptance import ReviewAcceptanceFixture

from mos_eisley.cli import main
from mos_eisley.core.budget import BudgetPolicy
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.registry import openai_registry
from mos_eisley.run.review_campaign import (
    CampaignAttempt,
    CampaignAttemptSubmission,
    CampaignEvidenceSubmission,
    ReviewCampaignBundle,
    decode_campaign_bundle,
    decode_campaign_submission,
    read_campaign_seal,
    review_campaign_evidence,
    seal_review_campaign,
)
from mos_eisley.run.review_conformance_observation import ReviewObservationPolicy
from mos_eisley.run.review_launch import LaunchCritic, ReviewLaunchConfiguration
from mos_eisley.run.store import private_write


class CampaignCeremonyTests(ReviewAcceptanceFixture):
    def before_attempts(
        self, observation_policies: list[ReviewObservationPolicy]
    ) -> None:
        self.bundle = ReviewCampaignBundle(
            policy=self.policy,
            attempts=tuple(
                CampaignAttempt(
                    configuration=ReviewLaunchConfiguration(
                        registry=openai_registry(),
                        critics=(
                            LaunchCritic(
                                critic=fixture.base.critic, spending=fixture.base.policy
                            ),
                        ),
                        judge_model=fixture.base.policy.model,
                        judge_spending=fixture.base.policy,
                        effort=fixture.preview.requests[0].effort,
                        budget=BudgetPolicy(max_output_tokens=100),
                        policy=self.policy.review_policy,
                        total_seconds=self.policy.total_seconds,
                        max_total_microusd=650,
                    ),
                    preview=fixture.preview,
                    authority_policy=fixture.policy,
                    observation_policy=observation_policy,
                    ledger_path=str(fixture.base.ledger.path),
                )
                for fixture, observation_policy in zip(
                    self.fixtures, observation_policies, strict=True
                )
            ),
        )
        self.root = self.fixtures[0].base.root
        self.bundle_file = self.root / "operator-bundle.json"
        private_write(self.bundle_file, canonical_bytes(self.bundle))
        self.sealed_directory = self.root / "sealed-campaign"
        preview = io.StringIO()
        with redirect_stdout(preview):
            self.assertEqual(
                main(["review-campaign-preview", "--bundle", str(self.bundle_file)]), 0
            )
        self.preview_output = json.loads(preview.getvalue())
        sealed = io.StringIO()
        with redirect_stdout(sealed):
            self.assertEqual(
                main(
                    [
                        "review-campaign-seal",
                        "--bundle",
                        str(self.bundle_file),
                        "--expected-bundle-sha256",
                        digest(canonical_bytes(self.bundle)),
                        "--destination",
                        str(self.sealed_directory),
                    ]
                ),
                0,
            )
        self.seal_sha = json.loads(sealed.getvalue())["seal_sha256"]
        self.assertTrue(
            all(
                fixture.base.ledger.snapshot().entries == 0 for fixture in self.fixtures
            )
        )
        self.assertTrue(
            all(not fixture.directory.exists() for fixture in self.fixtures)
        )
        for fixture in self.fixtures:
            fixture.key_loader.assert_not_called()

    def submission(self) -> CampaignEvidenceSubmission:
        return CampaignEvidenceSubmission(
            seal_sha256=self.seal_sha,
            attempts=tuple(
                CampaignAttemptSubmission(
                    start=item.start,
                    judge=item.judge,
                    authorizations=item.authorizations,
                    signed_observation=item.signed_observation,
                    expected_result_sha256=item.expected_result_sha256,
                    lifecycle_directories=tuple(
                        str(path) for path in item.lifecycle_directories
                    ),
                )
                for item in self.evidence
            ),
        )

    def test_cli_seals_before_attempts_and_freshly_reviews_completed_evidence(self):
        self.assertEqual(self.preview_output["attempts"], 3)
        self.assertEqual(self.preview_output["total_planned_microusd"], 1950)
        self.assertNotIn("bundle", self.preview_output)
        evidence = self.root / "evidence.json"
        raw = canonical_bytes(self.submission())
        private_write(evidence, raw)
        out = io.StringIO()
        before = [fixture.base.ledger.path.read_bytes() for fixture in self.fixtures]
        with (
            patch("mos_eisley.providers.openai_live.AsyncOpenAI") as sdk,
            redirect_stdout(out),
        ):
            code = main(
                [
                    "review-campaign-review",
                    "--campaign-dir",
                    str(self.sealed_directory),
                    "--expected-seal-sha256",
                    self.seal_sha,
                    "--evidence",
                    str(evidence),
                    "--expected-evidence-sha256",
                    digest(raw),
                ]
            )
        self.assertEqual(code, 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "accepted")
        self.assertFalse(result["live_review_activation_authorized"])
        sdk.assert_not_called()
        self.assertEqual(
            before, [fixture.base.ledger.path.read_bytes() for fixture in self.fixtures]
        )
        self.assertEqual(self.sealed_directory.stat().st_mode & 0o777, 0o700)
        for path in self.sealed_directory.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_incomplete_submission_preserves_slots_and_returns_nonacceptance(self):
        submission = CampaignEvidenceSubmission(
            seal_sha256=self.seal_sha, attempts=(None, None, None)
        )
        result = review_campaign_evidence(
            self.sealed_directory, self.seal_sha, submission, now=self.now
        )
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(result.qualifying_attempts, 0)
        evidence = self.root / "incomplete.json"
        raw = canonical_bytes(submission)
        private_write(evidence, raw)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(
                main(
                    [
                        "review-campaign-review",
                        "--campaign-dir",
                        str(self.sealed_directory),
                        "--expected-seal-sha256",
                        self.seal_sha,
                        "--evidence",
                        str(evidence),
                        "--expected-evidence-sha256",
                        digest(raw),
                    ]
                ),
                1,
            )

    def test_attempt_started_before_sealing_is_rejected(self):
        submission = self.submission()
        first = submission.attempts[0]
        assert first is not None
        _, seal = read_campaign_seal(self.sealed_directory, self.seal_sha)
        first = first.model_copy(
            update={
                "start": first.start.model_copy(
                    update={"started_at": seal.sealed_at - timedelta(seconds=1)}
                )
            }
        )
        changed = submission.model_copy(
            update={"attempts": (first, *submission.attempts[1:])}
        )
        with self.assertRaisesRegex(ValueError, "predates sealing"):
            review_campaign_evidence(
                self.sealed_directory, self.seal_sha, changed, now=self.now
            )

    def test_fresh_review_rejects_changed_runtime_evidence(self):
        path = self.fixtures[0].critic_directory() / "runtime-generation-end.json"
        raw = json.loads(path.read_bytes())
        raw["duration_ms"] += 1
        path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):
            review_campaign_evidence(
                self.sealed_directory, self.seal_sha, self.submission(), now=self.now
            )

    def test_naive_start_timestamp_is_rejected_as_invalid_input(self):
        submission = self.submission().model_dump(mode="json")
        submission["attempts"][0]["start"]["started_at"] = "2026-09-12T00:00:00"
        with self.assertRaisesRegex(ValueError, "ordered UTC window"):
            decode_campaign_submission(json.dumps(submission).encode())

    def test_wrong_bundle_confirmation_writes_nothing(self):
        destination = self.root / "wrong-confirmation"
        with self.assertRaisesRegex(ValueError, "changed before sealing"):
            seal_review_campaign(
                self.bundle, destination, expected_bundle_sha256="f" * 64, now=self.now
            )
        self.assertFalse(destination.exists())

    def test_post_outcome_sealing_is_rejected(self):
        destination = self.root / "late-seal"
        with self.assertRaisesRegex(ValueError, "unused run directories"):
            seal_review_campaign(
                self.bundle,
                destination,
                expected_bundle_sha256=digest(canonical_bytes(self.bundle)),
                now=self.now,
            )
        self.assertFalse(destination.exists())

    def test_wrong_independent_seal_pin_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "independent pin"):
            read_campaign_seal(self.sealed_directory, "f" * 64)

    def test_tampered_retained_bundle_is_rejected(self):
        path = self.sealed_directory / "bundle.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "retained seal"):
            read_campaign_seal(self.sealed_directory, self.seal_sha)

    def test_cross_campaign_submission_is_rejected(self):
        submission = self.submission().model_copy(update={"seal_sha256": "f" * 64})
        with self.assertRaisesRegex(ValueError, "another retained seal"):
            review_campaign_evidence(
                self.sealed_directory, self.seal_sha, submission, now=self.now
            )

    def test_changed_submission_hash_fails_before_ledger_access(self):
        evidence = self.root / "evidence.json"
        private_write(evidence, canonical_bytes(self.submission()))
        with (
            patch("mos_eisley.run.review_campaign.SpendLedger") as ledger,
            redirect_stderr(io.StringIO()),
        ):
            code = main(
                [
                    "review-campaign-review",
                    "--campaign-dir",
                    str(self.sealed_directory),
                    "--expected-seal-sha256",
                    self.seal_sha,
                    "--evidence",
                    str(evidence),
                    "--expected-evidence-sha256",
                    "f" * 64,
                ]
            )
        self.assertEqual(code, 2)
        ledger.assert_not_called()

    def test_duplicate_keys_and_oversized_bundles_are_rejected(self):
        for raw in (b'{"schema_version":1,"schema_version":1}', b" " * 8_000_001):
            with self.assertRaises(ValueError):
                decode_campaign_bundle(raw)

    def test_configuration_substitution_cannot_change_committed_projection(self):
        first = self.bundle.attempts[0]
        changed = first.model_copy(
            update={
                "configuration": first.configuration.model_copy(
                    update={"effort": "low"}
                )
            }
        )
        broken = self.bundle.model_copy(
            update={"attempts": (changed, *self.bundle.attempts[1:])}
        )
        with self.assertRaises(ValueError):
            decode_campaign_bundle(canonical_bytes(broken))

    def test_existing_seal_is_preserved(self):
        before = (self.sealed_directory / "seal.json").read_bytes()
        with self.assertRaises(ValueError):
            seal_review_campaign(
                self.bundle,
                self.sealed_directory,
                expected_bundle_sha256=digest(canonical_bytes(self.bundle)),
                now=datetime.now(UTC),
            )
        self.assertEqual(before, (self.sealed_directory / "seal.json").read_bytes())
