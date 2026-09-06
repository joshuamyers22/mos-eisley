"""Statistical gates must not turn repeated or correlated fixtures into evidence."""

from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.core.models import Brief, canonical_bytes
from mos_eisley.core.skills import PromptAsset
from mos_eisley.evaluation.models import (
    CandidateGrid,
    EvalCase,
    EvaluationDataset,
    EvaluationGate,
    ExpectedFinding,
    Observation,
    ObservationSet,
    RouteCandidate,
    StatisticalDesign,
)
from mos_eisley.evaluation.scoring import EvaluationReport, make_plan, score
from mos_eisley.evaluation.statistics import (
    MAX_CONFIDENCE_FAMILY,
    assess_groups,
    group_interval,
)


def grouped_dataset(groups: int) -> EvaluationDataset:
    finding = ExpectedFinding(
        id="defect", category="correctness", description="Known boundary defect"
    )
    return EvaluationDataset(
        id="grouped-fixture",
        cases=tuple(
            EvalCase(
                id=f"{split}-{index}-{kind}",
                split=split,
                independence_group=f"{split}-{index}",
                brief=Brief(spec=f"{split} case {index}", diff=kind),
                expected_findings=(finding,) if kind == "defective" else (),
            )
            for split in ("calibration", "holdout")
            for index in range(groups if split == "holdout" else 1)
            for kind in ("clean", "defective")
        ),
    )


def perfect_report(
    data: EvaluationDataset, repetitions: int = 1, routes: int = 1
) -> EvaluationReport:
    grid = CandidateGrid(
        routes=tuple(
            RouteCandidate(
                backend="fixture",
                provider="fixture",
                model=f"model-{index}",
                effort="low",
                client_version="fixture/1",
                registry_sha256="a" * 64,
                prompt=PromptAsset(mode="inline", instructions="Review carefully."),
            )
            for index in range(routes)
        )
    )
    plan = make_plan(
        data,
        grid,
        repetitions,
        7,
        EvaluationGate(
            min_detection_lower_bound=0.8,
            max_false_positive_upper_bound=0.2,
            min_completion_lower_bound=0.8,
        ),
    )
    cases = {case.id: case for case in data.cases}
    observations = ObservationSet(
        plan_sha256=plan.plan_sha256,
        raw_results_sha256="b" * 64,
        adjudication_sha256="c" * 64,
        observations=tuple(
            Observation(
                case_id=item.case_id,
                candidate_id=item.candidate_id,
                repetition=item.repetition,
                status="completed",
                detected_finding_ids=tuple(
                    finding.id for finding in cases[item.case_id].expected_findings
                ),
                latency_ms=10,
                adjudication="fixture",
            )
            for item in plan.assignments
            if item.split == "holdout"
        ),
    )
    return score(plan, data, observations, "holdout")


class EvaluationStatisticsTests(TestCase):
    def test_bound_matches_reference_and_covers_boundary_outcomes(self) -> None:
        result = group_interval([1.0] * 100, 6)
        self.assertAlmostEqual(result.radius, 0.16553910298388702)
        self.assertAlmostEqual(result.lower, 0.834460897016113)
        self.assertEqual(result.upper, 1.0)
        zero = group_interval([0.0] * 100, 6)
        self.assertEqual(zero.lower, 0.0)
        self.assertAlmostEqual(zero.upper, result.radius)
        # A single flawless group still has the full uncertainty range.
        self.assertEqual(group_interval([1.0], 6).lower, 0.0)

    def test_repetitions_never_increase_independent_sample_size(self) -> None:
        data = grouped_dataset(1)
        first = perfect_report(data)
        repeated = perfect_report(data, repetitions=100)
        single = first.scores[0]
        many = repeated.scores[0]
        self.assertGreater(many.detection.lower, single.detection.lower)
        self.assertEqual(many.statistical_assessment, single.statistical_assessment)
        self.assertFalse(many.eligible)
        self.assertEqual(many.statistical_assessment.issues, ("too_few_groups",))

    def test_independent_groups_can_pass_without_promoting_fixture_routes(self) -> None:
        report = perfect_report(grouped_dataset(100))
        result = report.scores[0]
        self.assertTrue(result.eligible)
        self.assertFalse(report.promotion_ready)
        assessment = result.statistical_assessment
        self.assertEqual(assessment.family_size, 6)
        self.assertEqual(assessment.interval_alpha, 0.05 / 6)
        self.assertIsNotNone(assessment.detection)
        assert assessment.detection is not None
        self.assertEqual(assessment.detection.groups, 100)
        self.assertAlmostEqual(assessment.detection.lower, 0.834460897016113)
        self.assertEqual(
            EvaluationReport.model_validate_json(canonical_bytes(report)), report
        )

    def test_more_routes_widen_the_family_corrected_bounds(self) -> None:
        data = grouped_dataset(100)
        one = perfect_report(data).scores[0].statistical_assessment
        two = perfect_report(data, routes=2).scores[0].statistical_assessment
        assert one.detection is not None and two.detection is not None
        self.assertEqual(two.family_size, 12)
        self.assertLess(two.detection.lower, one.detection.lower)
        self.assertGreater(two.detection.radius, one.detection.radius)

    def test_equal_group_weighting_and_failed_clean_review_penalty(self) -> None:
        label = ExpectedFinding(id="bug", category="correctness", description="Defect")
        cases = {
            name: EvalCase(
                id=name,
                split="holdout",
                independence_group=group,
                brief=Brief(spec=name, diff="fixture"),
                expected_findings=(label,) if defective else (),
            )
            for name, group, defective in (
                ("a-found", "a", True),
                ("a-missed", "a", True),
                ("a-clean", "a", False),
                ("b-found", "b", True),
                ("b-clean", "b", False),
            )
        }
        observations = tuple(
            Observation(
                case_id=name,
                candidate_id="a" * 64,
                repetition=0,
                status="error" if name == "a-clean" else "completed",
                error="timeout" if name == "a-clean" else None,
                detected_finding_ids=("bug",) if name.endswith("found") else (),
                latency_ms=1,
                adjudication="fixture",
            )
            for name in cases
        )
        result = assess_groups(
            cases, observations, StatisticalDesign(min_groups_per_metric=2), 1
        )
        assert result.detection is not None
        assert result.clean_false_positive_runs is not None
        assert result.completion is not None
        # Group A detects half, group B all: equal group mean is .75, not 2/3.
        self.assertEqual(result.detection.estimate, 0.75)
        self.assertEqual(result.detection.groups, 2)
        # An unavailable clean review contributes a worst-case positive rate.
        self.assertEqual(result.clean_false_positive_runs.estimate, 0.5)
        self.assertAlmostEqual(result.completion.estimate, (2 / 3 + 1) / 2)
        self.assertTrue(result.sufficient_groups)

    def test_group_cannot_leak_into_holdout(self) -> None:
        data = grouped_dataset(1)
        changed = data.cases[-1].model_copy(
            update={"independence_group": data.cases[0].independence_group}
        )
        with self.assertRaisesRegex(ValidationError, "cannot cross"):
            EvaluationDataset(id="leaking", cases=(*data.cases[:-1], changed))

    def test_relabeling_identical_briefs_does_not_create_independent_cases(
        self,
    ) -> None:
        data = grouped_dataset(1)
        duplicate = data.cases[-1].model_copy(
            update={"id": "copied-case", "independence_group": "new-group"}
        )
        with self.assertRaisesRegex(ValidationError, "duplicate evaluation briefs"):
            EvaluationDataset(id="duplicated", cases=(*data.cases, duplicate))

    def test_fixed_design_and_schema_version_are_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            StatisticalDesign.model_validate_json('{"stopping_rule":"until_pass"}')
        with self.assertRaises(ValidationError):
            StatisticalDesign(min_groups_per_metric=1)
        data = grouped_dataset(1).model_dump(mode="json")
        data["schema_version"] = 1
        with self.assertRaises(ValidationError):
            EvaluationDataset.model_validate(data)

    def test_invalid_rates_and_comparison_families_are_rejected(self) -> None:
        for values in ([], [float("nan")], [float("inf")], [-0.1], [1.1]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                group_interval(values, 6)
        for family in (0, 5, MAX_CONFIDENCE_FAMILY + 1):
            with self.subTest(family=family), self.assertRaises(ValueError):
                group_interval([0.5], family)
