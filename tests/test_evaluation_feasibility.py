"""G3 pre-spend feasibility must fail before an impossible fixed matrix runs."""

import io
import json
import stat
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pydantic import ValidationError

from mos_eisley.cli import main
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.skills import PromptAsset
from mos_eisley.evaluation.feasibility import (
    EvaluationFeasibilityReport,
    EvaluationStudyBudget,
    RouteCostCeiling,
    assess_evaluation_feasibility,
)
from mos_eisley.evaluation.models import (
    CandidateGrid,
    EvaluationGate,
    RouteCandidate,
)


def candidate_grid(count: int) -> CandidateGrid:
    return CandidateGrid(
        routes=tuple(
            RouteCandidate(
                backend="fixture",
                provider="fixture",
                model=f"reviewer-{index}",
                effort="low",
                client_version="fixture/1",
                registry_sha256="a" * 64,
                prompt=PromptAsset(mode="inline", instructions="Review carefully."),
            )
            for index in range(count)
        )
    )


def study_budget(
    grid: CandidateGrid,
    *,
    strata: int = 1,
    repetitions: int = 1,
    route_cost: int = 1,
    non_assignment_cost: int = 0,
    spend_ceiling: int = 1_000_000_000,
) -> EvaluationStudyBudget:
    return EvaluationStudyBudget(
        candidate_grid_sha256=digest(canonical_bytes(grid)),
        comparison_strata=tuple(f"profile-{index}" for index in range(strata)),
        repetitions=repetitions,
        route_cost_ceilings=tuple(
            RouteCostCeiling(
                candidate_id=route.candidate_id,
                cost_basis_sha256="b" * 64,
                max_cost_microusd=route_cost,
            )
            for route in grid.routes
        ),
        non_assignment_cost_ceiling_microusd=non_assignment_cost,
        spend_ceiling_microusd=spend_ceiling,
    )


class EvaluationFeasibilityTests(TestCase):
    def test_plan_reference_calculation_exposes_impossible_matrix(self) -> None:
        grid = candidate_grid(6)
        gate = EvaluationGate(
            min_detection_lower_bound=0.95,
            max_false_positive_upper_bound=0.05,
            min_completion_lower_bound=0.95,
        )
        report = assess_evaluation_feasibility(
            grid,
            gate,
            study_budget(grid, strata=4, repetitions=3, route_cost=100),
        )

        self.assertEqual(report.confidence_family_size, 144)
        self.assertEqual(
            report.best_case_required_detection_groups_per_stratum_split, 1732
        )
        self.assertEqual(report.best_case_required_clean_groups_per_stratum_split, 1732)
        self.assertEqual(report.best_case_minimum_clean_cases, 13_856)
        self.assertEqual(report.best_case_minimum_clean_assignments, 249_408)
        self.assertEqual(report.best_case_minimum_total_cases, 27_712)
        self.assertEqual(report.best_case_minimum_total_assignments, 498_816)
        self.assertEqual(report.best_case_maximum_total_cost_microusd, 49_881_600)
        self.assertFalse(report.minimum_resource_feasible)
        self.assertEqual(
            report.issues,
            ("dataset_case_ceiling_exceeded", "assignment_ceiling_exceeded"),
        )
        self.assertFalse(report.study_execution_authorized)
        self.assertFalse(report.promotion_ready)
        self.assertEqual(
            EvaluationFeasibilityReport.model_validate_json(canonical_bytes(report)),
            report,
        )

    def test_affordable_smaller_design_and_spend_rejection(self) -> None:
        grid = candidate_grid(1)
        gate = EvaluationGate(
            min_detection_lower_bound=0.5,
            max_false_positive_upper_bound=0.5,
            min_completion_lower_bound=0.5,
        )
        feasible = assess_evaluation_feasibility(
            grid,
            gate,
            study_budget(
                grid,
                route_cost=7,
                non_assignment_cost=10,
                spend_ceiling=850,
            ),
        )
        self.assertEqual(feasible.best_case_minimum_total_cases, 120)
        self.assertEqual(feasible.best_case_minimum_total_assignments, 120)
        self.assertEqual(feasible.best_case_maximum_total_cost_microusd, 850)
        self.assertTrue(feasible.minimum_resource_feasible)
        self.assertEqual(feasible.issues, ())

        over_budget = assess_evaluation_feasibility(
            grid,
            gate,
            study_budget(
                grid,
                route_cost=7,
                non_assignment_cost=10,
                spend_ceiling=849,
            ),
        )
        self.assertTrue(over_budget.within_dataset_case_ceiling)
        self.assertTrue(over_budget.within_assignment_ceiling)
        self.assertFalse(over_budget.within_spend_ceiling)
        self.assertEqual(over_budget.issues, ("spend_ceiling_exceeded",))

    def test_exact_best_case_targets_are_finite_sample_impossible(self) -> None:
        grid = candidate_grid(1)
        gate = EvaluationGate(
            min_detection_lower_bound=1.0,
            max_false_positive_upper_bound=0.0,
            min_completion_lower_bound=1.0,
        )
        report = assess_evaluation_feasibility(grid, gate, study_budget(grid))
        self.assertEqual(
            report.issues,
            (
                "exact_detection_target_unattainable",
                "exact_clean_risk_target_unattainable",
                "exact_completion_target_unattainable",
            ),
        )
        self.assertIsNone(report.best_case_minimum_total_cases)
        self.assertIsNone(report.within_spend_ceiling)
        self.assertFalse(report.minimum_resource_feasible)

    def test_completion_groups_add_cases_without_double_counting_quality(self) -> None:
        grid = candidate_grid(1)
        gate = EvaluationGate(
            min_detection_lower_bound=0.0,
            max_false_positive_upper_bound=1.0,
            min_completion_lower_bound=0.95,
        )
        report = assess_evaluation_feasibility(
            grid,
            gate,
            study_budget(grid, spend_ceiling=1_000_000_000),
        )
        self.assertEqual(
            report.best_case_required_detection_groups_per_stratum_split, 30
        )
        self.assertEqual(report.best_case_required_clean_groups_per_stratum_split, 30)
        self.assertEqual(
            report.best_case_required_completion_groups_per_stratum_split, 1097
        )
        # Per split: 30 defective + 30 clean + 1,067 completion-only cases.
        self.assertEqual(report.best_case_minimum_total_cases, 2254)
        self.assertTrue(report.minimum_resource_feasible)

    def test_budget_must_bind_unique_exact_routes_and_strata(self) -> None:
        grid = candidate_grid(2)
        budget = study_budget(grid)
        reversed_costs = budget.model_copy(
            update={"route_cost_ceilings": tuple(reversed(budget.route_cost_ceilings))}
        )
        gate = EvaluationGate(
            min_detection_lower_bound=0.5,
            max_false_positive_upper_bound=0.5,
            min_completion_lower_bound=0.5,
        )
        with self.assertRaisesRegex(ValueError, "exact candidate order"):
            assess_evaluation_feasibility(grid, gate, reversed_costs)
        with self.assertRaisesRegex(ValueError, "does not match"):
            assess_evaluation_feasibility(
                grid,
                gate,
                budget.model_copy(update={"candidate_grid_sha256": "b" * 64}),
            )
        with self.assertRaisesRegex(ValidationError, "comparison strata"):
            EvaluationStudyBudget(
                candidate_grid_sha256=budget.candidate_grid_sha256,
                comparison_strata=("same", "same"),
                repetitions=1,
                route_cost_ceilings=budget.route_cost_ceilings,
                non_assignment_cost_ceiling_microusd=0,
                spend_ceiling_microusd=1,
            )

    def test_cli_writes_private_content_addressed_report(self) -> None:
        grid = candidate_grid(1)
        gate = EvaluationGate(
            min_detection_lower_bound=0.5,
            max_false_positive_upper_bound=0.5,
            min_completion_lower_bound=0.5,
        )
        budget = study_budget(grid, route_cost=7, spend_ceiling=840)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            candidates_path = root / "candidates.json"
            gate_path = root / "gate.json"
            budget_path = root / "budget.json"
            output_path = root / "private" / "feasibility.json"
            candidates_path.write_bytes(canonical_bytes(grid))
            gate_path.write_bytes(canonical_bytes(gate))
            budget_path.write_bytes(canonical_bytes(budget))

            with redirect_stdout(io.StringIO()) as output:
                result = main(
                    [
                        "eval-feasibility",
                        "--candidates",
                        str(candidates_path),
                        "--gate",
                        str(gate_path),
                        "--study-budget",
                        str(budget_path),
                        "--output",
                        str(output_path),
                    ]
                )
            self.assertEqual(result, 0)
            event = json.loads(output.getvalue())
            report = EvaluationFeasibilityReport.model_validate_json(
                output_path.read_bytes()
            )
            self.assertEqual(event["report_sha256"], report.report_sha256)
            self.assertTrue(event["minimum_resource_feasible"])
            self.assertFalse(event["study_execution_authorized"])
            self.assertEqual(stat.S_IMODE(output_path.stat().st_mode), 0o600)

            rejected_budget = budget.model_copy(update={"spend_ceiling_microusd": 839})
            budget_path.write_bytes(canonical_bytes(rejected_budget))
            rejected_path = root / "private" / "rejected-feasibility.json"
            with redirect_stdout(io.StringIO()) as rejected_output:
                result = main(
                    [
                        "eval-feasibility",
                        "--candidates",
                        str(candidates_path),
                        "--gate",
                        str(gate_path),
                        "--study-budget",
                        str(budget_path),
                        "--output",
                        str(rejected_path),
                    ]
                )
            self.assertEqual(result, 1)
            self.assertEqual(
                json.loads(rejected_output.getvalue())["issues"],
                ["spend_ceiling_exceeded"],
            )
