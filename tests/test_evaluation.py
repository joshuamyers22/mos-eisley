"""Evaluation plans are reproducible and cannot hide failed or missing trials."""

from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.core.models import Brief
from mos_eisley.evaluation.models import (
    CandidateGrid,
    EvalCase,
    EvaluationDataset,
    EvaluationGate,
    ExpectedFinding,
    Observation,
    ObservationSet,
    RouteCandidate,
)
from mos_eisley.evaluation.scoring import make_plan, score


def dataset() -> EvaluationDataset:
    finding = ExpectedFinding(
        id="boundary-defect",
        category="correctness",
        description="The upper boundary is rejected.",
    )
    return EvaluationDataset(
        id="routing-v1",
        cases=(
            EvalCase(
                id="calibration-defective",
                split="calibration",
                brief=Brief(spec="Accept 10.", diff="if value < 10", constraints=""),
                expected_findings=(finding,),
                risk_tags=("boundary",),
            ),
            EvalCase(
                id="calibration-clean",
                split="calibration",
                brief=Brief(spec="Accept 10.", diff="if value <= 10", constraints=""),
            ),
            EvalCase(
                id="holdout-defective",
                split="holdout",
                brief=Brief(spec="Accept 20.", diff="if value < 20", constraints=""),
                expected_findings=(finding,),
                risk_tags=("boundary",),
            ),
            EvalCase(
                id="holdout-clean",
                split="holdout",
                brief=Brief(spec="Accept 20.", diff="if value <= 20", constraints=""),
            ),
        ),
    )


def candidates() -> CandidateGrid:
    return CandidateGrid(
        routes=(
            RouteCandidate(
                backend="fixture",
                provider="fixture",
                model="reviewer-v1",
                effort="low",
                client_version="mos-eisley-test/1",
                registry_sha256="a" * 64,
            ),
        )
    )


def gate() -> EvaluationGate:
    return EvaluationGate(
        min_detection_lower_bound=0.8,
        max_false_positive_upper_bound=0.2,
        min_completion_lower_bound=0.8,
        max_mean_cost_microusd=100,
        max_p95_latency_ms=50,
    )


class EvaluationTests(TestCase):
    def test_plan_is_complete_randomized_and_content_addressed(self) -> None:
        data = dataset()
        grid = candidates()
        first = make_plan(data, grid, 20, 7, gate())
        repeated = make_plan(data, grid, 20, 7, gate())
        other_seed = make_plan(data, grid, 20, 8, gate())

        self.assertEqual(first, repeated)
        self.assertEqual(first.plan_sha256, repeated.plan_sha256)
        self.assertEqual(len(first.assignments), 80)
        self.assertNotEqual(first.assignments, other_seed.assignments)
        self.assertNotEqual(first.plan_sha256, other_seed.plan_sha256)

    def test_repetitions_alone_cannot_establish_eligibility(self) -> None:
        data = dataset()
        plan = make_plan(data, candidates(), 20, 7, gate())
        route_id = plan.routes[0].candidate_id
        observations = ObservationSet(
            plan_sha256=plan.plan_sha256,
            raw_results_sha256="d" * 64,
            adjudication_sha256="e" * 64,
            observations=tuple(
                Observation(
                    case_id=case_id,
                    candidate_id=route_id,
                    repetition=repetition,
                    status="completed",
                    detected_finding_ids=("boundary-defect",)
                    if case_id == "holdout-defective"
                    else (),
                    false_positive_count=0,
                    latency_ms=40,
                    cost_microusd=75,
                    adjudication="human",
                )
                for case_id in ("holdout-defective", "holdout-clean")
                for repetition in range(20)
            ),
        )

        report = score(plan, data, observations, "holdout")
        result = report.scores[0]
        self.assertFalse(result.eligible)
        self.assertEqual(
            result.statistical_assessment.issues, ("missing_independence_groups",)
        )
        self.assertFalse(report.promotion_ready)
        self.assertEqual(result.route, plan.routes[0])
        self.assertEqual(report.gate, plan.gate)
        self.assertEqual(report.observations_sha256, observations.observations_sha256)
        self.assertGreaterEqual(result.detection.lower, 0.8)
        self.assertLessEqual(result.clean_false_positive_runs.upper, 0.2)
        self.assertEqual(result.mean_cost_microusd, 75.0)
        self.assertEqual(result.cost_coverage, 1.0)
        self.assertEqual(result.p95_latency_ms, 40)

        with self.assertRaisesRegex(ValueError, "exactly cover"):
            score(
                plan,
                data,
                observations.model_copy(
                    update={"observations": observations.observations[:-1]}
                ),
                "holdout",
            )
        with self.assertRaisesRegex(ValueError, "do not match the sweep plan"):
            score(
                plan,
                data,
                observations.model_copy(update={"plan_sha256": "0" * 64}),
                "holdout",
            )

    def test_failures_count_against_detection_and_completion(self) -> None:
        data = dataset()
        plan = make_plan(data, candidates(), 2, 4, gate())
        route_id = plan.routes[0].candidate_id
        observations = ObservationSet(
            plan_sha256=plan.plan_sha256,
            raw_results_sha256="d" * 64,
            adjudication_sha256="e" * 64,
            observations=(
                Observation(
                    case_id="holdout-defective",
                    candidate_id=route_id,
                    repetition=0,
                    status="error",
                    latency_ms=50,
                    cost_microusd=10,
                    adjudication="fixture",
                    error="timeout",
                ),
                Observation(
                    case_id="holdout-defective",
                    candidate_id=route_id,
                    repetition=1,
                    status="completed",
                    detected_finding_ids=("boundary-defect",),
                    latency_ms=10,
                    cost_microusd=10,
                    adjudication="fixture",
                ),
                Observation(
                    case_id="holdout-clean",
                    candidate_id=route_id,
                    repetition=0,
                    status="completed",
                    false_positive_count=1,
                    latency_ms=10,
                    adjudication="fixture",
                ),
                Observation(
                    case_id="holdout-clean",
                    candidate_id=route_id,
                    repetition=1,
                    status="completed",
                    latency_ms=10,
                    cost_microusd=10,
                    adjudication="fixture",
                ),
            ),
        )

        result = score(plan, data, observations, "holdout").scores[0]
        self.assertEqual(result.detection.estimate, 0.5)
        self.assertEqual(result.completion.estimate, 0.75)
        self.assertEqual(result.clean_false_positive_runs.estimate, 0.5)
        self.assertEqual(result.cost_coverage, 0.75)
        self.assertFalse(result.passes_cost)
        self.assertFalse(result.eligible)

    def test_plan_bounds_are_checked_before_matrix_expansion(self) -> None:
        with self.assertRaisesRegex(ValueError, "repetitions"):
            make_plan(dataset(), candidates(), 101, 0, gate())

    def test_invalid_labels_and_duplicate_observations_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            EvalCase(
                id="duplicate-label",
                split="holdout",
                brief=Brief(spec="s", diff="d"),
                expected_findings=(
                    ExpectedFinding(
                        id="same", category="correctness", description="one"
                    ),
                    ExpectedFinding(id="same", category="security", description="two"),
                ),
            )

        observation = Observation(
            case_id="holdout-clean",
            candidate_id="b" * 64,
            repetition=0,
            status="completed",
            latency_ms=1,
            adjudication="fixture",
        )
        with self.assertRaises(ValidationError):
            ObservationSet(
                plan_sha256="c" * 64,
                raw_results_sha256="d" * 64,
                adjudication_sha256="e" * 64,
                observations=(observation, observation),
            )

    def test_unknown_ground_truth_id_is_rejected_during_scoring(self) -> None:
        data = dataset()
        plan = make_plan(data, candidates(), 1, 0, gate())
        route_id = plan.routes[0].candidate_id
        observations = ObservationSet(
            plan_sha256=plan.plan_sha256,
            raw_results_sha256="d" * 64,
            adjudication_sha256="e" * 64,
            observations=(
                Observation(
                    case_id="holdout-defective",
                    candidate_id=route_id,
                    repetition=0,
                    status="completed",
                    detected_finding_ids=("not-ground-truth",),
                    latency_ms=1,
                    adjudication="human",
                ),
                Observation(
                    case_id="holdout-clean",
                    candidate_id=route_id,
                    repetition=0,
                    status="completed",
                    latency_ms=1,
                    adjudication="human",
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "unknown detected"):
            score(plan, data, observations, "holdout")

    def test_plan_split_tampering_is_rejected(self) -> None:
        data = dataset()
        plan = make_plan(data, candidates(), 1, 0, gate())
        assignment = plan.assignments[0]
        wrong_split = "holdout" if assignment.split == "calibration" else "calibration"
        tampered = plan.model_copy(
            update={
                "assignments": (
                    assignment.model_copy(update={"split": wrong_split}),
                    *plan.assignments[1:],
                )
            }
        )
        selected_split = assignment.split
        selected = tuple(
            Observation(
                case_id=item.case_id,
                candidate_id=item.candidate_id,
                repetition=item.repetition,
                status="completed",
                latency_ms=1,
                adjudication="fixture",
            )
            for item in plan.assignments
            if item.split == selected_split
        )
        with self.assertRaisesRegex(ValueError, "complete evaluation matrix"):
            score(
                tampered,
                data,
                ObservationSet(
                    plan_sha256=tampered.plan_sha256,
                    raw_results_sha256="d" * 64,
                    adjudication_sha256="e" * 64,
                    observations=selected,
                ),
                selected_split,
            )
