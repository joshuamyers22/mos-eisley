"""Post-selection skill health is empirical, signed, and non-executing."""

import io
import json
import math
from contextlib import redirect_stdout
from datetime import timedelta
from typing import Any, cast
from unittest import TestCase
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.skill_health import (
    SignedSkillHealthObservation,
    SignedSkillHealthPolicy,
    SkillHealthAuthorityPolicy,
    SkillHealthEligibility,
    SkillHealthMetrics,
    SkillHealthObservation,
    SkillHealthPolicy,
    SkillHealthThresholds,
    evaluate_skill_health_metrics,
    issue_skill_health_eligibility,
    sign_skill_health_observation,
    sign_skill_health_policy,
    trusted_skill_health_authority,
    verify_skill_health_eligibility,
)
from mos_eisley.run.store import private_write
from tests import test_skill_default as default_module


class SkillHealthTests(TestCase):
    def setUp(self) -> None:
        self.source = default_module.SkillDefaultTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.selection = self.source.select(self.source.authenticate())
        self.pointer = self.selection.pointer
        self.policy_signer = Ed25519PrivateKey.generate()
        self.observer_signer = Ed25519PrivateKey.generate()
        self.observed_from = self.pointer.selected_at + timedelta(seconds=1)
        self.observed_through = self.pointer.selected_at + timedelta(seconds=5)
        self.issue_at = self.pointer.selected_at + timedelta(seconds=10)
        staging = self.source.source.source.source
        control = staging.source
        fixture = control.source.promotion
        self.report = fixture.holdout_report
        latest = staging.anchor.snapshot(control.policy).latest
        assert latest is not None
        self.authorities = SkillHealthAuthorityPolicy(
            policy_id="skill-health-authorities-v1",
            default_authority_policy_sha256=self.source.policy.policy_sha256,
            default_store_policy_sha256=self.source.store.policy.policy_sha256,
            control_anchor_policy_sha256=staging.anchor.policy.policy_sha256,
            promotion_authority_policy_sha256=fixture.authority_policy.policy_sha256,
            valid_from=self.pointer.selected_at - timedelta(seconds=1),
            valid_until=self.source.valid_until,
            authorities=(
                trusted_skill_health_authority(
                    "health-observer",
                    self.observer_signer.public_key().public_bytes_raw(),
                ),
                trusted_skill_health_authority(
                    "health-policy",
                    self.policy_signer.public_key().public_bytes_raw(),
                ),
            ),
        )
        self.health_policy = SkillHealthPolicy(
            policy_id="selected-skill-health-v1",
            authority_policy_sha256=self.authorities.policy_sha256,
            default_store_policy_sha256=self.source.store.policy.policy_sha256,
            default_pointer_sha256=self.pointer.pointer_sha256,
            installed_manifest_sha256=self.pointer.installed_manifest_sha256,
            archive_sha256=self.pointer.archive_sha256,
            skill=self.pointer.skill,
            release_evidence_sha256=control.evidence.release_evidence_sha256,
            reference_holdout_report_sha256=(
                fixture.holdout_report.skill_comparison_report_sha256
            ),
            measurement_protocol_sha256="7" * 64,
            control_anchor_policy_sha256=staging.anchor.policy.policy_sha256,
            control_anchor_entry_sha256=latest.anchor_entry_sha256,
            signed_control_sha256=staging.control.signed_control.signed_control_sha256,
            valid_from=self.pointer.selected_at,
            valid_until=self.source.valid_until,
            max_observation_age_seconds=60,
            max_eligibility_lifetime_seconds=30,
            thresholds=SkillHealthThresholds(
                minimum_independence_groups=(
                    fixture.holdout_report.minimum_groups_per_metric
                ),
                max_detection_lower_bound_regression_ppm=10_000,
                max_clean_false_positive_upper_bound_increase_ppm=10_000,
                max_completion_lower_bound_regression_ppm=10_000,
                max_mean_cost_delta_increase_microusd=100,
                max_p95_latency_delta_increase_ms=100,
            ),
        )
        report = fixture.holdout_report
        cost = report.mean_cost_delta_microusd
        self.metrics = SkillHealthMetrics(
            detection_independence_groups=report.detection_delta.groups,
            clean_independence_groups=report.clean_false_positive_delta.groups,
            completion_independence_groups=report.completion_delta.groups,
            detection_lower_bound_ppm=math.ceil(
                report.detection_delta.lower * 1_000_000
            ),
            clean_false_positive_upper_bound_ppm=math.floor(
                report.clean_false_positive_delta.upper * 1_000_000
            ),
            completion_lower_bound_ppm=math.ceil(
                report.completion_delta.lower * 1_000_000
            ),
            mean_cost_delta_microusd=(math.floor(cost) if cost is not None else None),
            paired_cost_coverage_ppm=(
                round(report.paired_cost_coverage * 1_000_000)
                if cost is not None
                else 0
            ),
            p95_latency_delta_ms=report.p95_latency_delta_ms,
        )
        self.observation = SkillHealthObservation(
            health_policy_sha256=self.health_policy.health_policy_sha256,
            default_pointer_sha256=self.pointer.pointer_sha256,
            installed_manifest_sha256=self.pointer.installed_manifest_sha256,
            archive_sha256=self.pointer.archive_sha256,
            skill=self.pointer.skill,
            measurement_protocol_sha256=self.health_policy.measurement_protocol_sha256,
            evidence_bundle_sha256="8" * 64,
            observed_from=self.observed_from,
            observed_through=self.observed_through,
            valid_until=self.source.valid_until,
            metrics=self.metrics,
        )

    def _arguments(self) -> tuple[object, ...]:
        return (
            *self.source._arguments(),  # pyright: ignore[reportPrivateUsage]
            self.source.store,
            self.source.policy,
        )

    def signed_policy(self) -> SignedSkillHealthPolicy:
        return sign_skill_health_policy(
            self.health_policy,
            "health-policy",
            self.policy_signer.private_bytes_raw(),
        )

    def signed_observation(
        self, observation: SkillHealthObservation | None = None
    ) -> SignedSkillHealthObservation:
        return sign_skill_health_observation(
            observation or self.observation,
            "health-observer",
            self.observer_signer.private_bytes_raw(),
        )

    def issue(
        self,
        *,
        signed_policy: SignedSkillHealthPolicy | None = None,
        signed_observation: SignedSkillHealthObservation | None = None,
        authorities: SkillHealthAuthorityPolicy | None = None,
        offset: timedelta = timedelta(0),
    ) -> SkillHealthEligibility:
        call = cast(Any, issue_skill_health_eligibility)
        return call(
            *self._arguments(),
            signed_policy or self.signed_policy(),
            signed_observation or self.signed_observation(),
            authorities or self.authorities,
            self.issue_at + offset,
        )

    def test_issues_exact_expiring_health_and_drift_eligibility_without_runtime(
        self,
    ) -> None:
        signed_policy = self.signed_policy()
        signed_observation = self.signed_observation()
        eligibility = self.issue(
            signed_policy=signed_policy,
            signed_observation=signed_observation,
        )

        self.assertEqual(
            eligibility.default_pointer_sha256, self.pointer.pointer_sha256
        )
        self.assertEqual(eligibility.archive_sha256, self.pointer.archive_sha256)
        self.assertTrue(eligibility.health_passed)
        self.assertTrue(eligibility.drift_passed)
        self.assertTrue(eligibility.runtime_preflight_eligible)
        self.assertFalse(eligibility.runtime_dispatch_authorized)
        self.assertFalse(eligibility.activation_authorized)
        self.assertFalse(eligibility.configuration_mutation_authorized)
        self.assertFalse(eligibility.automatic_rollback_authorized)
        self.assertEqual(
            eligibility.valid_until,
            self.issue_at + timedelta(seconds=30),
        )
        verify_call = cast(Any, verify_skill_health_eligibility)
        verify_call(
            *self._arguments(),
            signed_policy,
            signed_observation,
            self.authorities,
            eligibility,
            self.issue_at + timedelta(seconds=1),
        )

    def test_preselection_stale_future_and_insufficient_evidence_fail_closed(
        self,
    ) -> None:
        before = self.observation.model_copy(
            update={"observed_from": self.pointer.selected_at - timedelta(seconds=1)}
        )
        with self.assertRaisesRegex(ValueError, "pre-selection"):
            self.issue(signed_observation=self.signed_observation(before))

        future = self.observation.model_copy(
            update={"observed_through": self.issue_at + timedelta(seconds=1)}
        )
        with self.assertRaisesRegex(ValueError, "future"):
            self.issue(signed_observation=self.signed_observation(future))

        insufficient = self.observation.model_copy(
            update={
                "metrics": self.metrics.model_copy(
                    update={"detection_independence_groups": 1}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "insufficient"):
            self.issue(signed_observation=self.signed_observation(insufficient))

        with self.assertRaisesRegex(ValueError, "stale"):
            self.issue(offset=timedelta(seconds=61))

    def test_health_and_drift_thresholds_are_recomputed(self) -> None:
        unhealthy = self.observation.model_copy(
            update={
                "metrics": self.metrics.model_copy(
                    update={"mean_cost_delta_microusd": 3}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "health evidence failed"):
            self.issue(signed_observation=self.signed_observation(unhealthy))

        strict_thresholds = self.health_policy.thresholds.model_copy(
            update={"max_p95_latency_delta_increase_ms": 0}
        )
        earlier_reference = self.report.model_copy(update={"p95_latency_delta_ms": 0})
        drift_only = evaluate_skill_health_metrics(
            self.metrics,
            earlier_reference,
            strict_thresholds,
        )
        self.assertTrue(drift_only.health_passed)
        self.assertFalse(drift_only.drift_passed)

    def test_signer_separation_tampering_and_policy_substitution_fail_closed(
        self,
    ) -> None:
        same_signer = sign_skill_health_observation(
            self.observation,
            "health-policy",
            self.policy_signer.private_bytes_raw(),
        )
        with self.assertRaisesRegex(ValueError, "distinct signers"):
            self.issue(signed_observation=same_signer)

        tampered = self.signed_observation().model_copy(
            update={
                "observation": self.observation.model_copy(
                    update={"evidence_bundle_sha256": "9" * 64}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "signature is invalid"):
            self.issue(signed_observation=tampered)

        overlapping = self.authorities.model_copy(
            update={
                "authorities": (
                    trusted_skill_health_authority(
                        "health-observer",
                        self.observer_signer.public_key().public_bytes_raw(),
                    ),
                    trusted_skill_health_authority(
                        "skill-default-selector",
                        self.source.signer.public_key().public_bytes_raw(),
                    ),
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "must be independent"):
            self.issue(authorities=overlapping)

    def test_pointer_control_and_expiry_are_rechecked(self) -> None:
        wrong_pointer = self.health_policy.model_copy(
            update={"default_pointer_sha256": "a" * 64}
        )
        signed_wrong = sign_skill_health_policy(
            wrong_pointer,
            "health-policy",
            self.policy_signer.private_bytes_raw(),
        )
        with self.assertRaisesRegex(ValueError, "policy provenance"):
            self.issue(signed_policy=signed_wrong)

        eligibility = self.issue()
        with self.assertRaisesRegex(ValueError, "not current"):
            eligibility.check_current(eligibility.valid_until)

    def test_cli_issues_non_executing_health_eligibility(self) -> None:
        signed_policy_path = self.source.root / "signed-health-policy.json"
        signed_observation_path = self.source.root / "signed-health-observation.json"
        authorities_path = self.source.root / "health-authorities.json"
        output = self.source.root / "health-eligibility.json"
        private_write(signed_policy_path, canonical_bytes(self.signed_policy()))
        private_write(
            signed_observation_path, canonical_bytes(self.signed_observation())
        )
        private_write(authorities_path, canonical_bytes(self.authorities))
        dummy = str(self.source.root / "unused.json")
        arguments = ["eval-issue-skill-health-eligibility"]
        for option in (
            "dataset",
            "plan",
            "sealed-comparison",
            "holdout-use-claim",
            "calibration-report",
            "holdout-report",
            "promotion-receipt",
            "promotion-authority-policy",
            "archive",
            "release-evidence",
            "control-authority-policy",
            "authenticated-control",
            "control-anchor",
            "installed-store",
            "installation-authority-policy",
            "default-store",
            "default-authority-policy",
        ):
            arguments.extend((f"--{option}", dummy))
        for prefix in ("calibration", "holdout"):
            for option in (
                "batch",
                "mapping",
                "raw-results",
                "grading-batch",
                "dual-grading-resolution",
                "dual-graded-observations",
                "grading-trust-policy",
                "resolution-trust-policy",
            ):
                arguments.extend((f"--{prefix}-{option}", dummy))
        arguments.extend(
            (
                "--signed-health-policy",
                str(signed_policy_path),
                "--signed-health-observation",
                str(signed_observation_path),
                "--health-authority-policy",
                str(authorities_path),
                "--output",
                str(output),
            )
        )
        with (
            patch(
                "mos_eisley.cli._skill_default_sources",
                return_value=(
                    self.source._arguments(),  # pyright: ignore[reportPrivateUsage]
                    (self.source.store, self.source.policy),
                ),
            ),
            patch("mos_eisley.cli.datetime") as clock,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            clock.now.return_value = self.issue_at
            self.assertEqual(main(arguments), 0)
        event = json.loads(stdout.getvalue())
        self.assertEqual(event["type"], "evaluation.skill_health.eligible")
        self.assertTrue(event["runtime_preflight_eligible"])
        self.assertFalse(event["runtime_dispatch_authorized"])
        self.assertFalse(event["automatic_rollback_authorized"])
        artifact = SkillHealthEligibility.model_validate_json(output.read_bytes())
        self.assertEqual(artifact.default_pointer_sha256, self.pointer.pointer_sha256)
