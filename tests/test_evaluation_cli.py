"""The offline evaluation CLI writes private, verified contracts."""

import io
import json
import stat
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mos_eisley.cli import main
from mos_eisley.core.models import Brief, canonical_bytes
from mos_eisley.evaluation.models import (
    CandidateGrid,
    EvalCase,
    EvaluationDataset,
    EvaluationGate,
    ExpectedFinding,
    Observation,
    ObservationSet,
    RouteCandidate,
    SweepPlan,
)


class EvaluationCliTests(TestCase):
    def test_plan_and_holdout_score_round_trip(self) -> None:
        finding = ExpectedFinding(
            id="defect", category="correctness", description="Known defect"
        )
        data = EvaluationDataset(
            id="cli-eval",
            cases=(
                EvalCase(
                    id="cal-defect",
                    split="calibration",
                    brief=Brief(spec="s", diff="bad"),
                    expected_findings=(finding,),
                ),
                EvalCase(
                    id="cal-clean",
                    split="calibration",
                    brief=Brief(spec="s", diff="good"),
                ),
                EvalCase(
                    id="hold-defect",
                    split="holdout",
                    brief=Brief(spec="s", diff="bad holdout"),
                    expected_findings=(finding,),
                ),
                EvalCase(
                    id="hold-clean",
                    split="holdout",
                    brief=Brief(spec="s", diff="good holdout"),
                ),
            ),
        )
        grid = CandidateGrid(
            routes=(
                RouteCandidate(
                    backend="fixture",
                    provider="fixture",
                    model="reviewer-v1",
                    effort="low",
                    client_version="test/1",
                    registry_sha256="a" * 64,
                ),
            )
        )
        quality_gate = EvaluationGate(
            min_detection_lower_bound=0,
            max_false_positive_upper_bound=1,
            min_completion_lower_bound=0,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_path = root / "dataset.json"
            candidates_path = root / "candidates.json"
            gate_path = root / "gate.json"
            plan_path = root / "private" / "plan.json"
            observations_path = root / "observations.json"
            report_path = root / "private" / "report.json"
            dataset_path.write_bytes(canonical_bytes(data))
            candidates_path.write_bytes(canonical_bytes(grid))
            gate_path.write_bytes(canonical_bytes(quality_gate))

            with redirect_stdout(io.StringIO()) as output:
                result = main(
                    [
                        "eval-plan",
                        "--dataset",
                        str(dataset_path),
                        "--candidates",
                        str(candidates_path),
                        "--gate",
                        str(gate_path),
                        "--repetitions",
                        "1",
                        "--seed",
                        "9",
                        "--output",
                        str(plan_path),
                    ]
                )
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue())["assignments"], 4)
            self.assertEqual(stat.S_IMODE(plan_path.stat().st_mode), 0o600)

            plan = SweepPlan.model_validate_json(plan_path.read_bytes())
            route_id = plan.routes[0].candidate_id
            observations = ObservationSet(
                plan_sha256=plan.plan_sha256,
                raw_results_sha256="d" * 64,
                adjudication_sha256="e" * 64,
                observations=(
                    Observation(
                        case_id="hold-defect",
                        candidate_id=route_id,
                        repetition=0,
                        status="completed",
                        detected_finding_ids=("defect",),
                        latency_ms=10,
                        adjudication="fixture",
                    ),
                    Observation(
                        case_id="hold-clean",
                        candidate_id=route_id,
                        repetition=0,
                        status="completed",
                        latency_ms=10,
                        adjudication="fixture",
                    ),
                ),
            )
            observations_path.write_bytes(canonical_bytes(observations))
            with redirect_stdout(io.StringIO()) as output:
                result = main(
                    [
                        "eval-score",
                        "--dataset",
                        str(dataset_path),
                        "--plan",
                        str(plan_path),
                        "--observations",
                        str(observations_path),
                        "--split",
                        "holdout",
                        "--output",
                        str(report_path),
                    ]
                )
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue())["eligible"], 1)
            self.assertEqual(stat.S_IMODE(report_path.stat().st_mode), 0o600)

            with (
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()) as errors,
            ):
                self.assertEqual(
                    main(
                        [
                            "eval-score",
                            "--dataset",
                            str(dataset_path),
                            "--plan",
                            str(plan_path),
                            "--observations",
                            str(observations_path),
                            "--split",
                            "holdout",
                            "--output",
                            str(report_path),
                        ]
                    ),
                    2,
                )
            self.assertIn("validation failed", errors.getvalue())
