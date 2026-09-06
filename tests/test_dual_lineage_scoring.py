"""Authenticated scoring retains full lineage and cannot authorize promotion."""

import base64
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
from mos_eisley.evaluation.lineage_scoring import (
    DualLineageEvaluationReport,
    score_dual_graded_observations,
    verify_dual_lineage_evaluation_report,
)
from mos_eisley.evaluation.scoring import EvaluationReport, score_observation_matrix
from mos_eisley.run.store import private_write
from tests.test_dual_lineage_observations import DualLineageObservationTests


class DualLineageScoringTests(TestCase):
    def setUp(self) -> None:
        self.source = DualLineageObservationTests()
        self.source.setUp()
        self.observations = self.source.compile()

    def score(self) -> DualLineageEvaluationReport:
        return score_dual_graded_observations(
            self.source.dataset,
            self.source.plan,
            self.source.batch,
            self.source.mapping,
            self.source.raw_results,
            self.source.grading_batch,
            self.source.dual_grading,
            self.source.grading_policy,
            self.source.resolution_policy,
            self.observations,
            "holdout",
        )

    def verify(self, report: DualLineageEvaluationReport) -> None:
        verify_dual_lineage_evaluation_report(
            self.source.dataset,
            self.source.plan,
            self.source.batch,
            self.source.mapping,
            self.source.raw_results,
            self.source.grading_batch,
            self.source.dual_grading,
            self.source.grading_policy,
            self.source.resolution_policy,
            self.observations,
            report,
        )

    def test_scores_reverified_lineage_and_retains_every_source_digest(self) -> None:
        report = self.score()
        self.assertEqual(report.dataset_sha256, self.source.dataset.dataset_sha256)
        self.assertEqual(report.plan_sha256, self.source.plan.plan_sha256)
        self.assertEqual(report.execution_batch_sha256, self.source.batch.batch_sha256)
        self.assertEqual(report.mapping_sha256, self.source.mapping.mapping_sha256)
        self.assertEqual(
            report.raw_results_sha256, self.source.raw_results.raw_results_sha256
        )
        self.assertEqual(
            report.grading_batch_sha256,
            self.source.grading_batch.grading_batch_sha256,
        )
        self.assertEqual(
            report.dual_grading_resolution_sha256,
            self.source.dual_grading.dual_grading_resolution_sha256,
        )
        self.assertEqual(
            report.dual_graded_observations_sha256,
            self.observations.dual_graded_observations_sha256,
        )
        self.assertEqual(report.split, "holdout")
        self.assertEqual(len(report.scores), 1)
        self.assertFalse(report.promotion_ready)
        self.verify(report)

    def test_changed_source_or_observation_fails_before_scoring(self) -> None:
        first = self.observations.observations[0]
        changed_observations = self.observations.model_copy(
            update={
                "observations": (
                    first.model_copy(update={"latency_ms": first.latency_ms + 1}),
                    *self.observations.observations[1:],
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "observation provenance"):
            score_dual_graded_observations(
                self.source.dataset,
                self.source.plan,
                self.source.batch,
                self.source.mapping,
                self.source.raw_results,
                self.source.grading_batch,
                self.source.dual_grading,
                self.source.grading_policy,
                self.source.resolution_policy,
                changed_observations,
                "holdout",
            )
        changed_raw = self.source.raw_results.model_copy(
            update={"batch_sha256": "f" * 64}
        )
        with self.assertRaises(ValueError):
            score_dual_graded_observations(
                self.source.dataset,
                self.source.plan,
                self.source.batch,
                self.source.mapping,
                changed_raw,
                self.source.grading_batch,
                self.source.dual_grading,
                self.source.grading_policy,
                self.source.resolution_policy,
                self.observations,
                "holdout",
            )

    def test_wrong_split_and_edited_report_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly cover"):
            score_dual_graded_observations(
                self.source.dataset,
                self.source.plan,
                self.source.batch,
                self.source.mapping,
                self.source.raw_results,
                self.source.grading_batch,
                self.source.dual_grading,
                self.source.grading_policy,
                self.source.resolution_policy,
                self.observations,
                "calibration",
            )
        report = self.score()
        changed = report.model_copy(update={"raw_results_sha256": "f" * 64})
        with self.assertRaisesRegex(ValueError, "report provenance"):
            self.verify(changed)

    def test_shared_scoring_engine_rejects_validation_bypassed_duplicates(
        self,
    ) -> None:
        duplicated = (
            *self.observations.observations,
            self.observations.observations[0],
        )
        with self.assertRaisesRegex(ValueError, "unique assignment"):
            score_observation_matrix(
                self.source.plan, self.source.dataset, duplicated, "holdout"
            )

    def test_report_schema_is_distinct_and_promotion_is_literal_false(self) -> None:
        report = self.score()
        with self.assertRaises(ValidationError):
            EvaluationReport.model_validate_json(canonical_bytes(report))
        value = report.model_dump(mode="json")
        value["promotion_ready"] = True
        with self.assertRaises(ValidationError):
            DualLineageEvaluationReport.model_validate(value)
        value = report.model_dump(mode="json")
        value["scores"].append(value["scores"][0])
        with self.assertRaises(ValidationError):
            DualLineageEvaluationReport.model_validate(value)

    def test_cli_writes_private_reverifiable_nonpromotable_report(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            values: dict[str, Contract] = {
                "dataset": self.source.dataset,
                "plan": self.source.plan,
                "batch": self.source.batch,
                "mapping": self.source.mapping,
                "raw": self.source.raw_results,
                "grading": self.source.grading_batch,
                "dual": self.source.dual_grading,
                "observations": self.observations,
                "grading_policy": self.source.grading_policy,
                "resolution_policy": self.source.resolution_policy,
            }
            paths = {name: root / f"{name}.json" for name in values}
            for name, value in values.items():
                private_write(paths[name], canonical_bytes(value))
            output = root / "dual-score.json"
            arguments = [
                "eval-score-dual",
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
                "--split",
                "holdout",
                "--output",
                str(output),
            ]
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(arguments), 0)
            event = json.loads(stdout.getvalue())
            report = DualLineageEvaluationReport.model_validate_json(
                output.read_bytes()
            )
            self.assertEqual(
                event["dual_lineage_report_sha256"],
                report.dual_lineage_report_sha256,
            )
            self.assertEqual(event["split"], "holdout")
            self.assertFalse(event["promotion_ready"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.verify(report)
            for signer in (
                self.source.left_signer,
                self.source.right_signer,
                self.source.resolution_signer,
            ):
                private_key = signer.private_bytes_raw()
                self.assertNotIn(private_key, output.read_bytes())
                self.assertNotIn(base64.b64encode(private_key), output.read_bytes())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(arguments), 2)
