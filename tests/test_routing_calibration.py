"""Profile calibration uses sealed design and authenticated calibration only."""

import io
import json
import stat
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import Contract, canonical_bytes
from mos_eisley.evaluation.adjudication import (
    AdjudicationSet,
    AdjudicatorProvenance,
    GradingBatch,
    make_grading_batch,
)
from mos_eisley.evaluation.authentication import (
    GradingTrustPolicy,
    authenticate_adjudication,
    sign_adjudication,
    trusted_adjudicator,
)
from mos_eisley.evaluation.execution import (
    BlindingMap,
    ExecutionBatch,
    RawResultSet,
    make_execution_batch,
    run_recorded_evaluation,
)
from mos_eisley.evaluation.lineage import (
    DualGradedObservationSet,
    compile_dual_graded_observations,
)
from mos_eisley.evaluation.lineage_scoring import DualLineageEvaluationReport
from mos_eisley.evaluation.models import Split
from mos_eisley.evaluation.resolution import (
    DualGradingResolution,
    ResolutionTrustPolicy,
    resolve_authenticated_adjudications,
)
from mos_eisley.evaluation.routing_calibration import (
    RoutingCalibrationReport,
    score_routing_calibration,
    verify_routing_calibration_report,
)
from mos_eisley.evaluation.routing_protocol import seal_routing_study
from mos_eisley.run.store import private_write
from tests.test_evaluation_execution import complete_cassette, grade_item
from tests.test_routing_protocol import study_inputs


class RoutingCalibrationTests(TestCase):
    def setUp(self) -> None:
        self.dataset, self.plan, self.manifest, protocol = study_inputs()
        self.sealed = seal_routing_study(
            self.dataset, self.plan, self.manifest, protocol
        )
        self.lineage = self.make_lineage("calibration")

    def make_lineage(
        self, split: Split
    ) -> tuple[
        ExecutionBatch,
        BlindingMap,
        RawResultSet,
        GradingBatch,
        DualGradingResolution,
        GradingTrustPolicy,
        ResolutionTrustPolicy,
        DualGradedObservationSet,
    ]:
        batch, mapping = make_execution_batch(self.plan, self.dataset, split, b"n" * 32)
        raw = run_recorded_evaluation(
            batch,
            complete_cassette(
                batch.batch_sha256,
                tuple(request.request_sha256 for request in batch.requests),
            ),
        )
        grading = make_grading_batch(self.dataset, self.plan, batch, mapping, raw)
        rubric = "b" * 64
        left_key = Ed25519PrivateKey.generate()
        right_key = Ed25519PrivateKey.generate()
        resolver_key = Ed25519PrivateKey.generate()
        grading_policy = GradingTrustPolicy(
            policy_id="routing-graders-v1",
            rubric_sha256=rubric,
            adjudicators=(
                trusted_adjudicator(
                    "routing-grader-a", left_key.public_key().public_bytes_raw()
                ),
                trusted_adjudicator(
                    "routing-grader-b", right_key.public_key().public_bytes_raw()
                ),
            ),
        )
        resolution_policy = ResolutionTrustPolicy(
            policy_id="routing-resolvers-v1",
            rubric_sha256=rubric,
            resolvers=(
                trusted_adjudicator(
                    "routing-resolver",
                    resolver_key.public_key().public_bytes_raw(),
                ),
            ),
        )
        judgments = tuple(grade_item(item) for item in grading.items)
        left = AdjudicationSet(
            grading_batch_sha256=grading.grading_batch_sha256,
            adjudicator=AdjudicatorProvenance(
                adjudicator_id="routing-grader-a",
                method="human",
                rubric_sha256=rubric,
                completed_at="2026-09-05T12:00:00Z",
            ),
            judgments=judgments,
        )
        right = AdjudicationSet(
            grading_batch_sha256=grading.grading_batch_sha256,
            adjudicator=AdjudicatorProvenance(
                adjudicator_id="routing-grader-b",
                method="human",
                rubric_sha256=rubric,
                completed_at="2026-09-05T12:05:00Z",
            ),
            judgments=judgments,
        )
        authenticated_left = authenticate_adjudication(
            grading,
            sign_adjudication(left, "routing-grader-a", left_key.private_bytes_raw()),
            grading_policy,
        )
        authenticated_right = authenticate_adjudication(
            grading,
            sign_adjudication(right, "routing-grader-b", right_key.private_bytes_raw()),
            grading_policy,
        )
        resolution = resolve_authenticated_adjudications(
            grading,
            authenticated_left,
            authenticated_right,
            grading_policy,
            resolution_policy,
            None,
        )
        observations = compile_dual_graded_observations(
            self.dataset,
            self.plan,
            batch,
            mapping,
            raw,
            grading,
            resolution,
            grading_policy,
            resolution_policy,
        )
        return (
            batch,
            mapping,
            raw,
            grading,
            resolution,
            grading_policy,
            resolution_policy,
            observations,
        )

    def score(self) -> RoutingCalibrationReport:
        return score_routing_calibration(
            self.dataset,
            self.plan,
            *self.lineage,
            self.manifest,
            self.sealed,
        )

    def verify(self, report: RoutingCalibrationReport) -> None:
        verify_routing_calibration_report(
            self.dataset,
            self.plan,
            *self.lineage,
            self.manifest,
            self.sealed,
            report,
        )

    def test_scores_every_profile_and_route_with_full_family_correction(self) -> None:
        report = self.score()
        self.assertEqual(len(report.profiles), 2)
        self.assertTrue(all(len(item.scores) == 2 for item in report.profiles))
        assessments = (
            score.statistical_assessment
            for profile in report.profiles
            for score in profile.scores
        )
        self.assertTrue(all(item.family_size == 24 for item in assessments))
        self.assertTrue(
            all(
                item.comparison_strata == 2 and item.family_size == 24
                for item in report.profiles
            )
        )
        self.assertEqual(report.split, "calibration")
        self.assertFalse(report.promotion_ready)
        self.assertFalse(report.activation_authorized)
        self.assertEqual(
            RoutingCalibrationReport.model_validate_json(canonical_bytes(report)),
            report,
        )
        self.verify(report)

    def test_holdout_lineage_is_rejected_by_calibration_boundary(self) -> None:
        holdout = self.make_lineage("holdout")
        with self.assertRaisesRegex(ValueError, "exactly cover"):
            score_routing_calibration(
                self.dataset,
                self.plan,
                *holdout,
                self.manifest,
                self.sealed,
            )

    def test_changed_study_lineage_or_report_fails_closed(self) -> None:
        changed_study = self.sealed.model_copy(update={"profile_ids": ("f" * 64,)})
        with self.assertRaisesRegex(ValueError, "routing study provenance"):
            score_routing_calibration(
                self.dataset,
                self.plan,
                *self.lineage,
                self.manifest,
                changed_study,
            )
        report = self.score()
        first_profile = report.profiles[0]
        first_score = first_profile.scores[0]
        changed_score = first_score.model_copy(
            update={"p95_latency_ms": first_score.p95_latency_ms + 1}
        )
        changed_report = report.model_copy(
            update={
                "profiles": (
                    first_profile.model_copy(
                        update={"scores": (changed_score, *first_profile.scores[1:])}
                    ),
                    *report.profiles[1:],
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "report provenance"):
            self.verify(changed_report)

    def test_report_schema_cannot_impersonate_aggregate_or_activate(self) -> None:
        report = self.score()
        with self.assertRaises(ValidationError):
            DualLineageEvaluationReport.model_validate_json(canonical_bytes(report))
        value = report.model_dump(mode="json")
        value["activation_authorized"] = True
        with self.assertRaises(ValidationError):
            RoutingCalibrationReport.model_validate(value)
        value = report.model_dump(mode="json")
        value["profiles"].append(value["profiles"][0])
        with self.assertRaises(ValidationError):
            RoutingCalibrationReport.model_validate(value)
        value = report.model_dump(mode="json")
        value["profiles"][0]["family_size"] = 12
        with self.assertRaises(ValidationError):
            RoutingCalibrationReport.model_validate(value)

    def test_cli_writes_private_reverifiable_calibration_report(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (
                batch,
                mapping,
                raw,
                grading,
                resolution,
                grading_policy,
                resolution_policy,
                observations,
            ) = self.lineage
            values: dict[str, Contract] = {
                "dataset": self.dataset,
                "plan": self.plan,
                "batch": batch,
                "mapping": mapping,
                "raw": raw,
                "grading": grading,
                "dual": resolution,
                "observations": observations,
                "grading_policy": grading_policy,
                "resolution_policy": resolution_policy,
                "manifest": self.manifest,
                "sealed": self.sealed,
            }
            paths = {name: root / f"{name}.json" for name in values}
            for name, value in values.items():
                private_write(paths[name], canonical_bytes(value))
            output = root / "calibration-report.json"
            arguments = [
                "eval-score-routing-calibration",
                "--dataset",
                str(paths["dataset"]),
                "--plan",
                str(paths["plan"]),
                "--batch",
                str(paths["batch"]),
                "--mapping",
                str(paths["mapping"]),
                "--raw-results",
                str(paths["raw"]),
                "--grading-batch",
                str(paths["grading"]),
                "--dual-grading-resolution",
                str(paths["dual"]),
                "--dual-graded-observations",
                str(paths["observations"]),
                "--grading-trust-policy",
                str(paths["grading_policy"]),
                "--resolution-trust-policy",
                str(paths["resolution_policy"]),
                "--feature-manifest",
                str(paths["manifest"]),
                "--sealed-study",
                str(paths["sealed"]),
                "--output",
                str(output),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(arguments), 0)
            event = json.loads(stdout.getvalue())
            report = RoutingCalibrationReport.model_validate_json(output.read_bytes())
            self.assertEqual(
                event["calibration_report_sha256"],
                report.calibration_report_sha256,
            )
            self.assertFalse(event["activation_authorized"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.verify(report)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(arguments), 2)
