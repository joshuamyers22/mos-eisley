"""Frozen-policy holdout evaluation is one-attempt, complete, and inert."""

import io
import json
import stat
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import Contract, canonical_bytes
from mos_eisley.evaluation.routing_calibration import score_routing_calibration
from mos_eisley.evaluation.routing_holdout import (
    FrozenPolicyHoldoutReport,
    HoldoutUseClaim,
    evaluate_frozen_routing_policy,
    make_holdout_use_claim,
    verify_frozen_policy_holdout_report,
)
from mos_eisley.evaluation.routing_policy import freeze_candidate_routing_policy
from mos_eisley.evaluation.routing_protocol import seal_routing_study
from mos_eisley.run.holdout_use import claim_holdout_use
from mos_eisley.run.store import private_write
from tests.test_routing_calibration import RoutingCalibrationTests, RoutingLineage
from tests.test_routing_protocol import study_inputs


class FrozenPolicyHoldoutTests(TestCase):
    def setUp(self) -> None:
        self.dataset, self.plan, self.manifest, protocol = study_inputs(
            True, max_p95_latency_ms=100
        )
        self.sealed = seal_routing_study(
            self.dataset, self.plan, self.manifest, protocol
        )
        self.source = RoutingCalibrationTests()
        self.source.dataset = self.dataset
        self.source.plan = self.plan
        self.source.manifest = self.manifest
        self.source.sealed = self.sealed
        self.calibration = self.source.make_lineage("calibration")
        self.calibration_report = score_routing_calibration(
            self.dataset,
            self.plan,
            *self.calibration,
            self.manifest,
            self.sealed,
        )
        self.policy = freeze_candidate_routing_policy(
            self.dataset,
            self.plan,
            *self.calibration,
            self.manifest,
            self.sealed,
            self.calibration_report,
        )
        self.holdout = self.source.make_lineage("holdout")

    def claim(self, holdout: RoutingLineage) -> HoldoutUseClaim:
        return make_holdout_use_claim(self.policy, *holdout)

    def evaluate(
        self, holdout: RoutingLineage | None = None
    ) -> FrozenPolicyHoldoutReport:
        selected = holdout if holdout is not None else self.holdout
        return evaluate_frozen_routing_policy(
            self.dataset,
            self.plan,
            *self.calibration,
            *selected,
            self.manifest,
            self.sealed,
            self.calibration_report,
            self.policy,
            self.claim(selected),
        )

    def test_scores_frozen_choices_without_granting_activation(self) -> None:
        report = self.evaluate()
        self.assertEqual(report.holdout_status, "evaluated_once_candidate_only")
        self.assertEqual(report.summary.profiles, 2)
        self.assertEqual(report.summary.calibrated_route_profiles, 2)
        self.assertEqual(report.summary.selected_adequate_profiles, 2)
        self.assertEqual(report.summary.under_routed_profiles, 0)
        self.assertEqual(report.summary.calibrated_policy_coverage, 1)
        self.assertEqual(report.summary.selected_adequacy_rate, 1)
        self.assertEqual(report.summary.under_routing_rate, 0)
        self.assertEqual(report.summary.mean_cost_regret_microusd, 0)
        self.assertEqual(report.summary.mean_latency_regret_ms, 0)
        self.assertFalse(report.promotion_ready)
        self.assertFalse(report.activation_authorized)
        self.assertEqual(
            FrozenPolicyHoldoutReport.model_validate_json(canonical_bytes(report)),
            report,
        )
        verify_frozen_policy_holdout_report(
            self.dataset,
            self.plan,
            *self.calibration,
            *self.holdout,
            self.manifest,
            self.sealed,
            self.calibration_report,
            self.policy,
            self.claim(self.holdout),
            report,
        )

    def test_reports_cost_regret_against_cheapest_adequate_route(self) -> None:
        holdout = self.source.make_lineage(
            "holdout",
            cost_microusd_by_model={"economy": 5, "fallback": 1},
        )
        report = self.evaluate(holdout)
        fallback = next(
            route for route in self.plan.routes if route.model == "fallback"
        )
        self.assertTrue(
            all(
                item.cheapest_adequate_candidate_id == fallback.candidate_id
                and item.cost_regret_microusd == 4
                and item.latency_regret_ms == 0
                for item in report.profiles
            )
        )
        self.assertEqual(report.summary.mean_cost_regret_microusd, 4)
        self.assertEqual(report.summary.max_cost_regret_microusd, 4)

    def test_detects_selected_route_failure_with_adequate_alternative(self) -> None:
        holdout = self.source.make_lineage(
            "holdout", latency_ms_by_model={"economy": 200, "fallback": 12}
        )
        report = self.evaluate(holdout)
        self.assertEqual(report.summary.under_routed_profiles, 2)
        self.assertEqual(report.summary.under_routing_rate, 1)
        self.assertEqual(report.summary.selected_adequate_profiles, 0)
        self.assertTrue(
            all(
                item.under_routed
                and item.missed_adequate_alternative
                and len(item.adequate_candidate_ids) == 1
                for item in report.profiles
            )
        )

    def test_incomplete_cost_evidence_suppresses_regret_claims(self) -> None:
        holdout = self.source.make_lineage("holdout", "fallback")
        report = self.evaluate(holdout)
        fallback = next(
            route for route in self.plan.routes if route.model == "fallback"
        )
        self.assertTrue(
            all(
                item.missing_cost_adequate_candidate_ids == (fallback.candidate_id,)
                and item.cheapest_adequate_candidate_id is None
                and item.cost_regret_microusd is None
                and item.latency_regret_ms is None
                for item in report.profiles
            )
        )
        self.assertEqual(report.summary.regret_observed_profiles, 0)

    def test_claim_and_report_tampering_fail_closed(self) -> None:
        claim = self.claim(self.holdout)
        changed_claim = claim.model_copy(update={"raw_results_sha256": "f" * 64})
        with self.assertRaisesRegex(ValueError, "claim provenance"):
            evaluate_frozen_routing_policy(
                self.dataset,
                self.plan,
                *self.calibration,
                *self.holdout,
                self.manifest,
                self.sealed,
                self.calibration_report,
                self.policy,
                changed_claim,
            )
        report = self.evaluate()
        changed_report = report.model_copy(update={"candidate_policy_sha256": "f" * 64})
        with self.assertRaisesRegex(ValueError, "report provenance"):
            verify_frozen_policy_holdout_report(
                self.dataset,
                self.plan,
                *self.calibration,
                *self.holdout,
                self.manifest,
                self.sealed,
                self.calibration_report,
                self.policy,
                claim,
                changed_report,
            )

    def test_calibration_matrix_cannot_be_substituted_for_holdout(self) -> None:
        claim = self.claim(self.calibration)
        with self.assertRaisesRegex(ValueError, "exactly cover"):
            evaluate_frozen_routing_policy(
                self.dataset,
                self.plan,
                *self.calibration,
                *self.calibration,
                self.manifest,
                self.sealed,
                self.calibration_report,
                self.policy,
                claim,
            )

    def test_schema_cannot_grant_promotion_or_activation(self) -> None:
        report = self.evaluate()
        value = report.model_dump(mode="json")
        value["promotion_ready"] = True
        with self.assertRaises(ValidationError):
            FrozenPolicyHoldoutReport.model_validate(value)
        value["promotion_ready"] = False
        value["activation_authorized"] = True
        with self.assertRaises(ValidationError):
            FrozenPolicyHoldoutReport.model_validate(value)
        value = report.model_dump(mode="json")
        value["summary"]["under_routed_profiles"] = 1
        value["summary"]["under_routing_rate"] = 0.5
        with self.assertRaises(ValidationError):
            FrozenPolicyHoldoutReport.model_validate(value)

    def test_local_claim_is_private_exclusive_and_policy_keyed(self) -> None:
        with TemporaryDirectory() as directory:
            claim_directory = Path(directory) / "claims"
            claim_directory.mkdir(mode=0o700)
            claim = self.claim(self.holdout)
            path = claim_holdout_use(claim_directory, claim)
            self.assertEqual(path.name, f"{self.policy.candidate_policy_sha256}.json")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(
                HoldoutUseClaim.model_validate_json(path.read_bytes()), claim
            )
            with self.assertRaises(FileExistsError):
                claim_holdout_use(claim_directory, claim)
            claim_directory.chmod(0o750)
            other = claim.model_copy(update={"candidate_policy_sha256": "f" * 64})
            with self.assertRaisesRegex(ValueError, "group or other"):
                claim_holdout_use(claim_directory, other)

    def test_claim_directory_symlink_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir(mode=0o700)
            link = root / "claims"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(OSError):
                claim_holdout_use(link, self.claim(self.holdout))

    def test_cli_consumes_claim_once_and_writes_private_report(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            claim_directory = root / "claims"
            claim_directory.mkdir(mode=0o700)
            values: dict[str, Contract] = {
                "dataset": self.dataset,
                "plan": self.plan,
                "manifest": self.manifest,
                "sealed": self.sealed,
                "report": self.calibration_report,
                "policy": self.policy,
            }
            lineage_names = (
                "batch",
                "mapping",
                "raw",
                "grading",
                "dual",
                "grading_policy",
                "resolution_policy",
                "observations",
            )
            for prefix, lineage in (
                ("calibration", self.calibration),
                ("holdout", self.holdout),
            ):
                values.update(
                    {
                        f"{prefix}_{name}": value
                        for name, value in zip(lineage_names, lineage, strict=True)
                    }
                )
            paths = {name: root / f"{name}.json" for name in values}
            for name, value in values.items():
                private_write(paths[name], canonical_bytes(value))

            output = root / "holdout-report.json"
            arguments = [
                "eval-evaluate-routing-holdout",
                "--dataset",
                str(paths["dataset"]),
                "--plan",
                str(paths["plan"]),
                "--feature-manifest",
                str(paths["manifest"]),
                "--sealed-study",
                str(paths["sealed"]),
                "--calibration-report",
                str(paths["report"]),
                "--candidate-policy",
                str(paths["policy"]),
                "--holdout-use-directory",
                str(claim_directory),
            ]
            cli_names = (
                "batch",
                "mapping",
                "raw-results",
                "grading-batch",
                "dual-grading-resolution",
                "grading-trust-policy",
                "resolution-trust-policy",
                "dual-graded-observations",
            )
            for prefix in ("calibration", "holdout"):
                for cli_name, artifact_name in zip(
                    cli_names, lineage_names, strict=True
                ):
                    arguments.extend(
                        (
                            f"--{prefix}-{cli_name}",
                            str(paths[f"{prefix}_{artifact_name}"]),
                        )
                    )
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main([*arguments, "--output", str(output)]), 0)
            event = json.loads(stdout.getvalue())
            report = FrozenPolicyHoldoutReport.model_validate_json(output.read_bytes())
            self.assertEqual(
                event["holdout_report_sha256"], report.holdout_report_sha256
            )
            self.assertFalse(event["activation_authorized"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            second_output = root / "second-report.json"
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([*arguments, "--output", str(second_output)]), 2)
            self.assertFalse(second_output.exists())
