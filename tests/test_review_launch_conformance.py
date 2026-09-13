"""Fresh launch profile comparisons never grant authority from fixture conformance."""

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from test_review_campaign import CampaignCeremonyFixture

from mos_eisley.cli import main
from mos_eisley.core.budget import BudgetPolicy
from mos_eisley.core.models import ReviewPolicy, canonical_bytes, digest
from mos_eisley.run.review_campaign import CampaignEvidenceSubmission
from mos_eisley.run.review_conformance_admission import ReviewConformanceRuntime
from mos_eisley.run.review_launch import (
    ReviewLaunchPreview,
    prepare_review_launch_preview,
)
from mos_eisley.run.review_launch_conformance import check_review_launch_conformance
from mos_eisley.run.spend_ledger import SpendLedger
from mos_eisley.run.store import private_write


class ReviewLaunchConformanceTests(CampaignCeremonyFixture):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.configuration = self.bundle.attempts[0].configuration
        self.launch_ledger = SpendLedger.create(self.root / "launch.sqlite", 2000)
        self.launch_directory = self.root / "proposed-launch"
        self.configuration_path = self.root / "launch-config.json"
        self.prepared_path = self.root / "launch-prepared.json"
        self.evidence_path = self.root / "launch-evidence.json"
        self.configuration_raw = canonical_bytes(self.configuration)
        self.evidence_raw = canonical_bytes(self.submission())
        for path, raw in (
            (self.configuration_path, self.configuration_raw),
            (self.prepared_path, canonical_bytes(self.fixtures[0].guided.prepared)),
            (self.evidence_path, self.evidence_raw),
        ):
            private_write(path, raw)

    def launch(self):
        guided = self.fixtures[0].guided
        return prepare_review_launch_preview(
            self.configuration,
            prepared=guided.prepared,
            expected_prepared_sha256=guided.prepared.sha256,
            workspace=guided.fixture.workspace,
            guidance_store=guided.store,
            guidance_policy_path=guided.fixture.policy_path,
            expected_guidance_policy_sha256=guided.policy_sha,
            ledger=self.launch_ledger,
            review_directory=self.launch_directory,
        )

    def check(
        self,
        *,
        submission: CampaignEvidenceSubmission | None = None,
        runtime: ReviewConformanceRuntime | None = None,
        now: datetime | None = None,
        launch: ReviewLaunchPreview | None = None,
    ):
        return check_review_launch_conformance(
            self.configuration,
            self.launch() if launch is None else launch,
            self.sealed_directory,
            self.seal_sha,
            self.submission() if submission is None else submission,
            runtime=self.policy.runtime if runtime is None else runtime,
            now=datetime.now(UTC) if now is None else now,
        )

    def arguments(self):
        guided = self.fixtures[0].guided
        return [
            "review-launch-conformance-check",
            "--config",
            str(self.configuration_path),
            "--expected-config-sha256",
            digest(self.configuration_raw),
            "--workspace",
            str(guided.fixture.workspace),
            "--guidance-storage",
            str(guided.fixture.storage),
            "--prepared",
            str(self.prepared_path),
            "--expected-prepared-sha256",
            guided.prepared.sha256,
            "--guidance-policy",
            str(guided.fixture.policy_path),
            "--expected-guidance-policy-sha256",
            guided.policy_sha,
            "--spend-ledger",
            str(self.launch_ledger.path),
            "--review-dir",
            str(self.launch_directory),
            "--campaign-dir",
            str(self.sealed_directory),
            "--expected-seal-sha256",
            self.seal_sha,
            "--evidence",
            str(self.evidence_path),
            "--expected-evidence-sha256",
            digest(self.evidence_raw),
            "--image-id",
            self.policy.runtime.image_id,
            "--json",
        ]

    def test_cli_rechecks_complete_evidence_without_credentials_or_reservations(self):
        ledgers = [self.launch_ledger, *(f.base.ledger for f in self.fixtures)]
        before = [ledger.path.read_bytes() for ledger in ledgers]
        out = io.StringIO()
        with (
            patch("mos_eisley.providers.openai_live.AsyncOpenAI") as sdk,
            patch("keyring.get_password") as key,
            redirect_stdout(out),
        ):
            self.assertEqual(main(self.arguments()), 0)
        sdk.assert_not_called()
        key.assert_not_called()
        result = json.loads(out.getvalue())
        self.assertEqual(result["conformance"]["status"], "accepted")
        self.assertEqual(result["conformance"]["qualifying_attempts"], 3)
        self.assertEqual(
            result["canonical_submission_sha256"], digest(self.evidence_raw)
        )
        self.assertTrue(result["launch_review_required"])
        for field in (
            "live_launch_available",
            "credential_access_authorized",
            "provider_dispatch_authorized",
            "reservation_created",
        ):
            self.assertFalse(result[field])
        self.assertNotIn("unsigned_observation", result)
        self.assertEqual(before, [ledger.path.read_bytes() for ledger in ledgers])
        self.assertFalse(self.launch_directory.exists())

    def test_partial_evidence_returns_incomplete_not_launch_admission(self):
        supplied = self.submission()
        self.evidence_raw = canonical_bytes(
            supplied.model_copy(update={"attempts": (supplied.attempts[0], None, None)})
        )
        self.evidence_path.write_bytes(self.evidence_raw)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(self.arguments()), 1)
        result = json.loads(out.getvalue())
        self.assertEqual(result["conformance"]["status"], "incomplete")
        self.assertEqual(result["conformance"]["qualifying_attempts"], 1)
        self.assertFalse(result["live_launch_available"])

    def test_changed_role_budget_does_not_inherit_campaign_conformance(self):
        selected = self.configuration.critics[0]
        self.configuration = self.configuration.model_copy(
            update={
                "budget": BudgetPolicy(max_output_tokens=99),
                "critics": (
                    selected.model_copy(
                        update={
                            "spending": selected.spending.model_copy(
                                update={"max_output_tokens": 99}
                            )
                        }
                    ),
                ),
                "judge_spending": self.configuration.judge_spending.model_copy(
                    update={"max_output_tokens": 99}
                ),
            }
        )
        with self.assertRaisesRegex(ValueError, "roles differ"):
            self.check()

    def test_changed_duration_does_not_inherit_campaign_conformance(self):
        self.configuration = self.configuration.model_copy(
            update={"total_seconds": 119}
        )
        with self.assertRaisesRegex(ValueError, "conformance profile"):
            self.check()

    def test_stronger_quorum_is_not_silently_relaxed(self):
        self.configuration = self.configuration.model_copy(
            update={"policy": ReviewPolicy()}
        )
        with self.assertRaises(ValueError):
            self.check()
        self.assertEqual(self.launch_ledger.snapshot().entries, 0)

    def test_changed_runtime_sdk_or_image_is_rejected(self):
        launch = self.launch()
        for update in ({"sdk_version": "999.0.0"}, {"image_id": "sha256:" + "f" * 64}):
            with (
                self.subTest(update=update),
                self.assertRaisesRegex(ValueError, "profile"),
            ):
                self.check(
                    runtime=self.policy.runtime.model_copy(update=update), launch=launch
                )

    def test_changed_configuration_hash_is_rejected(self):
        launch = self.launch().model_copy(update={"configuration_sha256": "f" * 64})
        with self.assertRaisesRegex(ValueError, "profile"):
            self.check(launch=launch)

    def test_current_guidance_change_blocks_cli_before_conformance_review(self):
        self.fixtures[0].guided.fixture.add_requirement()
        with (
            patch(
                "mos_eisley.review_launch_conformance_cli.check_review_launch_conformance"
            ) as check,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(main(self.arguments()), 2)
        check.assert_not_called()
        self.assertEqual(self.launch_ledger.snapshot().entries, 0)

    def test_changed_raw_inputs_fail_before_launch_preparation(self):
        for path, raw in (
            (self.configuration_path, self.configuration_raw),
            (self.evidence_path, self.evidence_raw),
        ):
            path.write_bytes(raw + b" ")
            with (
                patch("mos_eisley.review_launch_cli.prepare_from_arguments") as prepare,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(self.arguments()), 2)
            prepare.assert_not_called()
            path.write_bytes(raw)

    def test_previously_accepted_evidence_is_reverified_after_artifact_change(self):
        self.assertEqual(self.check().conformance.status, "accepted")
        path = self.fixtures[0].critic_directory() / "runtime-generation-end.json"
        changed = json.loads(path.read_bytes())
        changed["duration_ms"] += 1
        path.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            self.check()

    def test_expired_campaign_cannot_support_current_launch_review(self):
        with self.assertRaises(ValueError):
            self.check(now=self.policy.valid_until + timedelta(seconds=1))

    def test_cached_acceptance_report_cannot_replace_source_submission(self):
        self.evidence_raw = canonical_bytes(self.check().conformance)
        self.evidence_path.write_bytes(self.evidence_raw)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(self.arguments()), 2)
