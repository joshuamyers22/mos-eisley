"""Offline domain expectations, missing/failure accounting, and label boundaries."""

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from test_analysis_evidence import artifact as base_artifact

from mos_eisley.analysis.artifacts import AnalysisArtifact, load_artifact, save_artifact
from mos_eisley.analysis.controller import (
    AnalysisConfig,
    AnalysisRunIdentity,
    run_identity,
)
from mos_eisley.analysis.evaluation import (
    EvaluationArm,
    EvaluationCase,
    EvaluationInputs,
    EvaluationSuite,
    ExpectedCell,
    ExpectedOutcome,
    Observation,
    evaluate,
    public_plan,
)
from mos_eisley.analysis.evaluation_demo import run_demo
from mos_eisley.analysis.evidence import (
    AnalysisAnswer,
    AnalysisEvidence,
    CellClaim,
    checked_answer,
    sql_records,
)
from mos_eisley.analysis.fixture_server import REVISION
from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ToolResultBlock

IDENTITY = AnalysisRunIdentity(
    settings_sha256="b" * 64, system_sha256="c" * 64, tool_catalog_sha256="d" * 64
)


def captured(
    values: tuple[int | float | str, ...] = (42,), source: str = "raw"
) -> AnalysisArtifact:
    result = base_artifact().result
    traces = [result.tool_trace[0]]
    evidence = [result.evidence[0]]
    claims: list[CellClaim] = []
    for index, value in enumerate(values):
        trace = result.tool_trace[1]
        call = trace.call.model_copy(update={"id": f"metric-{index}"})
        response = cast(ToolResultBlock, trace.response)
        raw = json.loads(response.content)
        raw["structured_content"].update(
            {
                "rows": [[value]],
                "backend": "fixture",
                "source": source,
                "units": "items",
            }
        )
        response = response.model_copy(
            update={"call_id": call.id, "content": json.dumps(raw)}
        )
        result_id = f"result-{index + 2:04d}"
        traces.append(
            trace.model_copy(
                update={"call": call, "response": response, "result_id": result_id}
            )
        )
        evidence.append(
            AnalysisEvidence(
                result_id=result_id,
                tool=call.name,
                complete=True,
                result_sha256=digest(canonical_bytes(response)),
            )
        )
        claims.append(
            CellClaim(result_id=result_id, row=0, column="total", value=value)
        )
    proposal = AnalysisAnswer(
        status="answer",
        text="unused",
        result_ids=tuple(c.result_id for c in claims),
        claims=tuple(claims),
    )
    result = result.model_copy(
        update={
            "run_identity": IDENTITY,
            "tool_trace": tuple(traces),
            "sql_trail": sql_records(tuple(traces)),
            "evidence": tuple(evidence),
            "tool_calls": len(traces),
            "answer": checked_answer(proposal, tuple(traces)),
        }
    )
    return AnalysisArtifact.model_validate_json(
        AnalysisArtifact(result=result).model_dump_json()
    )


def cell(**changes: object) -> ExpectedCell:
    return ExpectedCell.model_validate(
        {
            "tool": "run_metric",
            "arguments": {"name": "total", "revision": REVISION},
            "submitted_sql": "SELECT 42 AS total",
            "source_metadata": {
                "backend": "fixture",
                "source": "raw",
                "units": "items",
            },
            "reviewed_units": "items",
            "row": 0,
            "column": "total",
            "value": 42,
            **changes,
        }
    )


def suite(
    *, cells: tuple[ExpectedCell, ...] | None = None, order: str = "ordered"
) -> EvaluationSuite:
    return EvaluationSuite.model_validate(
        {
            "id": "synthetic",
            "reviewer": "fixture-reviewer",
            "reviewed_at": datetime.now(UTC) - timedelta(hours=1),
            "arms": (
                EvaluationArm(
                    id="seeded",
                    provider="fixture",
                    model="tool-reviewer-v1",
                    run_identity=IDENTITY,
                    semantic_revision=REVISION,
                ),
            ),
            "cases": (
                EvaluationCase(
                    id="total",
                    family="totals",
                    split="development",
                    question="What is the total?",
                    fixture_sha256="e" * 64,
                    expectations=(
                        ExpectedOutcome.model_validate(
                            {
                                "arm_id": "seeded",
                                "status": "answer",
                                "claim_order": order,
                                "cells": cells if cells is not None else (cell(),),
                            }
                        ),
                    ),
                ),
            ),
        }
    )


class EvaluationTests(TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def observation(
        self, artifact: AnalysisArtifact | None = None, case_id: str = "total"
    ) -> Observation:
        path = save_artifact(self.root, artifact or captured(), 3600)
        manifest, _ = load_artifact(path)
        return Observation(
            case_id=case_id,
            arm_id="seeded",
            artifact_path=str(path),
            artifact_sha256=manifest.payload_sha256,
        )

    def score(self, labels: EvaluationSuite, observations: tuple[Observation, ...]):
        return evaluate(
            labels,
            EvaluationInputs(
                suite_sha256=digest(canonical_bytes(labels)),
                split="development",
                observations=observations,
            ),
        )

    def test_correct_saved_run_matches_reviewed_sql_source_and_value(self) -> None:
        report = self.score(suite(), (self.observation(),))
        self.assertEqual(report.cases[0].outcome, "match")
        self.assertEqual(report.arms[0].matched_cases, 1)
        self.assertEqual(report.arms[0].reported_usage["bytes.input"], 10)
        self.assertFalse(report.promotion_ready)
        self.assertFalse(report.fixture_snapshot_verified)
        self.assertFalse(report.controlled_comparison_verified)
        self.assertFalse(report.explanation_quality_assessed)

    def test_true_cell_from_wrong_source_metric_or_sql_does_not_pass(self) -> None:
        observation = self.observation()
        for expected in (
            cell(value=99),
            cell(submitted_sql="SELECT 99 AS total"),
            cell(arguments={"name": "different_metric", "revision": REVISION}),
            cell(
                source_metadata={
                    "backend": "fixture",
                    "source": "other",
                    "units": "items",
                }
            ),
            cell(
                source_metadata={
                    "backend": "fixture",
                    "source": "raw",
                    "units": "dollars",
                },
                reviewed_units="dollars",
            ),
            cell(
                source_metadata={
                    "backend": "fixture",
                    "source": "raw",
                    "units": "items",
                    "data_snapshot": "frozen-other-source",
                }
            ),
        ):
            with self.subTest(expected=expected.tool):
                row = self.score(suite(cells=(expected,)), (observation,)).cases[0]
                self.assertEqual(row.outcome, "mismatch")
                self.assertIn("claims_mismatch", row.reasons)

    def test_missing_failed_and_invalid_runs_remain_in_denominator(self) -> None:
        labels = suite()
        cases = tuple(
            labels.cases[0].model_copy(
                update={"id": name, "family": name, "question": f"Question {name}"}
            )
            for name in ("missing", "failure", "invalid")
        )
        labels = labels.model_copy(update={"cases": cases})
        report = self.score(
            labels,
            (
                Observation(case_id="failure", arm_id="seeded", failure="timeout"),
                Observation(
                    case_id="invalid",
                    arm_id="seeded",
                    artifact_path=str(self.root / "absent"),
                    artifact_sha256="f" * 64,
                ),
            ),
        )
        arm = report.arms[0]
        self.assertEqual(
            (arm.planned_cases, arm.missing_cases, arm.failed_cases, arm.invalid_cases),
            (3, 1, 1, 1),
        )
        self.assertEqual(arm.spending_unknown_cases, 3)
        self.assertEqual(arm.usage_unknown_cases, 3)
        self.assertFalse(report.observations_complete)

    def test_unexpected_duplicate_and_reused_observations_rejected(self) -> None:
        labels = suite()
        obs = self.observation()
        for observations in (
            (obs, obs),
            (obs.model_copy(update={"case_id": "holdout"}),),
            (obs.model_copy(update={"arm_id": "other"}),),
        ):
            with self.assertRaises(ValueError):
                self.score(labels, observations)
        labels = labels.model_copy(
            update={
                "cases": (
                    labels.cases[0],
                    labels.cases[0].model_copy(
                        update={
                            "id": "other",
                            "family": "other",
                            "question": "Other question",
                        }
                    ),
                )
            }
        )
        with self.assertRaises(ValueError):
            self.score(labels, (obs, obs.model_copy(update={"case_id": "other"})))

    def test_modified_suite_or_artifact_hash_cannot_silently_replace_frozen_inputs(
        self,
    ) -> None:
        labels = suite()
        obs = self.observation()
        with self.assertRaises(ValueError):
            evaluate(
                labels,
                EvaluationInputs(
                    suite_sha256="a" * 64, split="development", observations=(obs,)
                ),
            )
        score = self.score(
            labels, (obs.model_copy(update={"artifact_sha256": "f" * 64}),)
        ).cases[0]
        self.assertEqual(score.reasons, ("artifact_hash_mismatch",))
        path = Path(cast(str, obs.artifact_path)) / "result.json"
        path.write_bytes(path.read_bytes() + b" ")
        self.assertEqual(
            self.score(labels, (obs,)).cases[0].reasons, ("invalid_artifact",)
        )

    def test_question_model_settings_revision_and_review_time_are_bound(self) -> None:
        labels = suite()
        obs = self.observation()
        variants = (
            (
                labels.model_copy(
                    update={
                        "cases": (
                            labels.cases[0].model_copy(
                                update={"question": "Wrong question"}
                            ),
                        )
                    }
                ),
                "question_mismatch",
            ),
            (
                labels.model_copy(
                    update={
                        "arms": (
                            labels.arms[0].model_copy(update={"model": "other-model"}),
                        )
                    }
                ),
                "model_mismatch",
            ),
            (
                labels.model_copy(
                    update={
                        "arms": (
                            labels.arms[0].model_copy(
                                update={
                                    "run_identity": IDENTITY.model_copy(
                                        update={"settings_sha256": "f" * 64}
                                    )
                                }
                            ),
                        )
                    }
                ),
                "run_identity_mismatch",
            ),
            (
                labels.model_copy(
                    update={
                        "arms": (
                            labels.arms[0].model_copy(
                                update={"semantic_revision": "f" * 64}
                            ),
                        )
                    }
                ),
                "semantic_revision_mismatch",
            ),
            (
                labels.model_copy(
                    update={"reviewed_at": datetime.now(UTC) + timedelta(hours=1)}
                ),
                "run_predates_review",
            ),
        )
        for changed, reason in variants:
            with self.subTest(reason=reason):
                self.assertIn(reason, self.score(changed, (obs,)).cases[0].reasons)
        old = captured().model_copy(
            update={
                "result": captured().result.model_copy(update={"run_identity": None})
            }
        )
        self.assertIn(
            "run_identity_mismatch",
            self.score(labels, (self.observation(old),)).cases[0].reasons,
        )

    def test_status_matching_does_not_claim_to_grade_explanation_text(self) -> None:
        artifact = captured()
        artifact = artifact.model_copy(
            update={
                "result": artifact.result.model_copy(
                    update={
                        "answer": AnalysisAnswer(
                            status="clarify", text="Which date range?"
                        ),
                        "value_verification": "not_applicable",
                    }
                )
            }
        )
        labels = suite()
        obs = self.observation(artifact)
        self.assertIn("status_mismatch", self.score(labels, (obs,)).cases[0].reasons)
        expected = ExpectedOutcome(arm_id="seeded", status="clarify")
        labels = labels.model_copy(
            update={
                "cases": (
                    labels.cases[0].model_copy(update={"expectations": (expected,)}),
                )
            }
        )
        report = self.score(labels, (obs,))
        self.assertEqual(report.cases[0].outcome, "match")
        self.assertFalse(report.explanation_quality_assessed)

    def test_type_preserving_tolerances_and_inclusive_boundary(self) -> None:
        for actual, expected, tolerance, outcome in (
            (1.01, 1.0, "0.01", "match"),
            (1.0101, 1.0, "0.01", "mismatch"),
            ("1.01", "1.00", "0.01", "match"),
            ("1.01", 1.0, "0.01", "mismatch"),
            ("1_0", "10", "0.1", "mismatch"),
            (1, 1.0, "0", "mismatch"),
        ):
            report = self.score(
                suite(cells=(cell(value=expected, absolute_tolerance=tolerance),)),
                (self.observation(captured((actual,))),),
            )
            self.assertEqual(report.cases[0].outcome, outcome)

    def test_unordered_matching_uses_each_claim_once_with_overlapping_tolerances(
        self,
    ) -> None:
        obs = self.observation(captured((1.0, 2.0)))
        cells = (cell(value=1.5, absolute_tolerance="0.5"), cell(value=1.0))
        self.assertEqual(
            self.score(suite(cells=cells, order="unordered"), (obs,)).cases[0].outcome,
            "match",
        )
        self.assertEqual(
            self.score(suite(cells=cells), (obs,)).cases[0].outcome, "mismatch"
        )
        repeated = (cell(value=2.0), cell(value=2.0))
        self.assertEqual(
            self.score(suite(cells=repeated, order="unordered"), (obs,))
            .cases[0]
            .outcome,
            "mismatch",
        )
        self.assertEqual(
            self.score(suite(cells=(cell(value=1.0),)), (obs,)).cases[0].outcome,
            "mismatch",
        )

    def test_public_tasks_exclude_labels_and_holdout_cases(self) -> None:
        labels = suite()
        holdout = labels.cases[0].model_copy(
            update={
                "id": "unseen",
                "family": "unseen",
                "question": "Holdout question",
                "split": "holdout",
            }
        )
        labels = labels.model_copy(update={"cases": (*labels.cases, holdout)})
        task_json = json.dumps(public_plan(labels, "development"))
        for secret in (
            "SELECT 42",
            '"value"',
            '"expected',
            "reviewed_units",
            "Holdout question",
        ):
            self.assertNotIn(secret, task_json)
        self.assertIn("What is the total?", task_json)
        report = evaluate(
            labels,
            EvaluationInputs(
                suite_sha256=digest(canonical_bytes(labels)), split="holdout"
            ),
        )
        self.assertEqual([row.case_id for row in report.cases], ["unseen"])

    def test_suite_rejects_family_leakage_duplicates_and_incomplete_arm_labels(
        self,
    ) -> None:
        labels = suite()
        for extra in (
            labels.cases[0],
            labels.cases[0].model_copy(
                update={"id": "other", "split": "holdout", "question": "Other"}
            ),
            labels.cases[0].model_copy(update={"id": "other", "family": "other"}),
            labels.cases[0].model_copy(
                update={
                    "id": "other",
                    "family": "other",
                    "question": "Other",
                    "expectations": (),
                }
            ),
        ):
            with self.assertRaises(ValueError):
                public_plan(
                    labels.model_copy(update={"cases": (*labels.cases, extra)}),
                    "development",
                )
        with self.assertRaises(ValueError):
            public_plan(labels, "holdout")
        with self.assertRaises(ValueError):
            ExpectedOutcome(arm_id="seeded", status="unavailable", cells=(cell(),))
        invalid_cells: tuple[dict[str, object], ...] = (
            {"arguments": {}},
            {"source_metadata": {}},
            {"reviewed_units": "wrong"},
            {"absolute_tolerance": "-1"},
            {"absolute_tolerance": "1", "value": "NaN"},
        )
        for changes in invalid_cells:
            with self.assertRaises(ValueError):
                cell(**changes)

    def test_identity_is_question_independent_and_budget_sensitive(self) -> None:
        config = AnalysisConfig(
            provider="fixture",
            model="tool-reviewer-v1",
            account="fixture",
            question="First",
        )
        first = run_identity(config, ())
        self.assertEqual(
            first, run_identity(config.model_copy(update={"question": "Second"}), ())
        )
        self.assertNotEqual(
            first, run_identity(config.model_copy(update={"max_tool_calls": 3}), ())
        )

    def test_cli_is_offline_private_and_never_overwrites_outputs(self) -> None:
        labels = suite()
        obs = self.observation()
        inputs = EvaluationInputs(
            suite_sha256=digest(canonical_bytes(labels)),
            split="development",
            observations=(obs,),
        )
        (self.root / "suite.json").write_bytes(canonical_bytes(labels))
        (self.root / "inputs.json").write_bytes(canonical_bytes(inputs))
        with (
            patch("mos_eisley.analysis.cli.EphemeralOpenAITransport") as provider,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                main(
                    [
                        "analysis-eval-plan",
                        "--suite",
                        str(self.root / "suite.json"),
                        "--split",
                        "development",
                        "--output",
                        str(self.root / "tasks.json"),
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "analysis-evaluate",
                        "--suite",
                        str(self.root / "suite.json"),
                        "--inputs",
                        str(self.root / "inputs.json"),
                        "--output",
                        str(self.root / "report.json"),
                    ]
                ),
                0,
            )
            provider.assert_not_called()
        self.assertEqual((self.root / "report.json").stat().st_mode & 0o777, 0o600)
        raw_report = (self.root / "report.json").read_text()
        self.assertNotIn("SELECT", raw_report)
        self.assertNotIn("What is the total", raw_report)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(
                main(
                    [
                        "analysis-evaluate",
                        "--suite",
                        str(self.root / "suite.json"),
                        "--inputs",
                        str(self.root / "inputs.json"),
                        "--output",
                        str(self.root / "report.json"),
                    ]
                ),
                2,
            )
        self.assertEqual(
            json.loads(err.getvalue()), {"type": "analysis.evaluation.failed"}
        )


class EvaluationDemoTests(IsolatedAsyncioTestCase):
    async def test_demo_uses_real_mcp_and_reports_missing_and_failed_assignments(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            path, report = await run_demo(Path(directory))
            self.assertTrue((path / "suite.json").exists())
            self.assertEqual(
                (
                    report.arms[0].matched_cases,
                    report.arms[0].failed_cases,
                    report.arms[0].missing_cases,
                ),
                (1, 1, 1),
            )
            self.assertFalse(report.promotion_ready)
            inputs = json.loads((path / "inputs.json").read_bytes())
            bundle = Path(inputs["observations"][0]["artifact_path"])
            _, recorded = load_artifact(bundle)
            self.assertIsNotNone(recorded.result.run_identity)
