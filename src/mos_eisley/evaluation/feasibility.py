"""Best-case fixed-matrix resource feasibility before evaluation spending."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    canonical_bytes,
    digest,
)
from mos_eisley.evaluation.models import (
    MAX_ASSIGNMENTS,
    MAX_CASES,
    CandidateGrid,
    EvaluationGate,
)
from mos_eisley.evaluation.statistics import MAX_CONFIDENCE_FAMILY

SPLIT_COUNT = 2
FAMILY_CONFIDENCE_ERROR = 0.05
MAX_MICROUSD = 1_000_000_000_000_000
MAX_TOTAL_MICROUSD = MAX_MICROUSD * MAX_ASSIGNMENTS
Count = Annotated[int, Field(ge=0)]
GroupCount = Annotated[int, Field(ge=2)]

FeasibilityIssue = Literal[
    "exact_detection_target_unattainable",
    "exact_clean_risk_target_unattainable",
    "exact_completion_target_unattainable",
    "dataset_case_ceiling_exceeded",
    "assignment_ceiling_exceeded",
    "spend_ceiling_exceeded",
]


class RouteCostCeiling(Contract):
    """Worst-case cost for one assignment on one exact candidate route."""

    candidate_id: Digest
    cost_basis_sha256: Digest
    max_cost_microusd: Annotated[int, Field(ge=0, le=MAX_MICROUSD)]


class EvaluationStudyBudget(Contract):
    """Pre-registered resource ceilings for one fixed-matrix study."""

    schema_version: Literal[1] = 1
    candidate_grid_sha256: Digest
    comparison_strata: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=5000)
    ]
    repetitions: Annotated[int, Field(ge=1, le=100)]
    route_cost_ceilings: Annotated[
        tuple[RouteCostCeiling, ...], Field(min_length=1, max_length=128)
    ]
    dataset_case_ceiling: Annotated[int, Field(ge=2, le=MAX_CASES)] = MAX_CASES
    assignment_ceiling: Annotated[int, Field(ge=1, le=MAX_ASSIGNMENTS)] = (
        MAX_ASSIGNMENTS
    )
    non_assignment_cost_ceiling_microusd: Annotated[int, Field(ge=0, le=MAX_MICROUSD)]
    spend_ceiling_microusd: Annotated[int, Field(ge=0, le=MAX_TOTAL_MICROUSD)]

    @model_validator(mode="after")
    def unique_dimensions(self) -> Self:
        if len(self.comparison_strata) != len(set(self.comparison_strata)):
            raise ValueError("comparison strata must be unique")
        candidate_ids = tuple(item.candidate_id for item in self.route_cost_ceilings)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("route cost candidate ids must be unique")
        return self

    @property
    def budget_sha256(self) -> str:
        return digest(canonical_bytes(self))


class EvaluationFeasibilityReport(Contract):
    """A lower-bound resource report, never execution or promotion authority."""

    schema_version: Literal[1] = 1
    candidate_grid_sha256: Digest
    gate_sha256: Digest
    budget_sha256: Digest
    confidence_family_size: Annotated[int, Field(ge=6, le=MAX_CONFIDENCE_FAMILY)]
    interval_alpha: Annotated[float, Field(gt=0, lt=1)]
    best_case_required_detection_groups_per_stratum_split: GroupCount | None
    best_case_required_clean_groups_per_stratum_split: GroupCount | None
    best_case_required_completion_groups_per_stratum_split: GroupCount | None
    best_case_minimum_clean_cases: Count | None
    best_case_minimum_defective_cases: Count | None
    best_case_minimum_total_cases: Count | None
    best_case_minimum_clean_assignments: Count | None
    best_case_minimum_total_assignments: Count | None
    best_case_maximum_total_cost_microusd: Count | None
    within_dataset_case_ceiling: bool | None
    within_assignment_ceiling: bool | None
    within_spend_ceiling: bool | None
    minimum_resource_feasible: bool
    issues: tuple[FeasibilityIssue, ...] = ()
    inference_method_changed: Literal[False] = False
    holdout_inspected: Literal[False] = False
    provider_request_authorized: Literal[False] = False
    study_execution_authorized: Literal[False] = False
    promotion_ready: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if len(self.issues) != len(set(self.issues)):
            raise ValueError("feasibility issues must be unique")
        exact_issues = {
            "exact_detection_target_unattainable",
            "exact_clean_risk_target_unattainable",
            "exact_completion_target_unattainable",
        }
        totals = (
            self.best_case_minimum_clean_cases,
            self.best_case_minimum_defective_cases,
            self.best_case_minimum_total_cases,
            self.best_case_minimum_clean_assignments,
            self.best_case_minimum_total_assignments,
            self.best_case_maximum_total_cost_microusd,
        )
        ceiling_results = (
            self.within_dataset_case_ceiling,
            self.within_assignment_ceiling,
            self.within_spend_ceiling,
        )
        has_exact_issue = bool(exact_issues.intersection(self.issues))
        if has_exact_issue and any(issue not in exact_issues for issue in self.issues):
            raise ValueError("finite-sample and resource issues cannot be combined")
        if has_exact_issue and not all(
            value is None for value in totals + ceiling_results
        ):
            raise ValueError("finite-sample totals do not match feasibility issues")
        if not has_exact_issue and any(
            value is None for value in totals + ceiling_results
        ):
            raise ValueError("finite-sample totals do not match feasibility issues")
        if self.minimum_resource_feasible != (not self.issues):
            raise ValueError("feasibility decision does not match its issues")
        expected_ceiling_issues = (
            "dataset_case_ceiling_exceeded",
            "assignment_ceiling_exceeded",
            "spend_ceiling_exceeded",
        )
        if not has_exact_issue and any(
            (result is False) != (issue in self.issues)
            for result, issue in zip(
                ceiling_results, expected_ceiling_issues, strict=True
            )
        ):
            raise ValueError("ceiling decisions do not match feasibility issues")
        if self.interval_alpha != FAMILY_CONFIDENCE_ERROR / self.confidence_family_size:
            raise ValueError("interval alpha does not match the confidence family")
        return self

    @property
    def report_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _required_groups(
    maximum_radius: float, family_size: int, minimum_groups: int
) -> int | None:
    if maximum_radius <= 0:
        return None
    numerator = math.log(2 * family_size / FAMILY_CONFIDENCE_ERROR)
    required = max(
        minimum_groups,
        math.ceil(numerator / (2 * maximum_radius * maximum_radius)),
    )
    # Defend the boundary against a floating-point quotient just below an integer.
    while math.sqrt(numerator / (2 * required)) > maximum_radius:
        required += 1
    return required


def assess_evaluation_feasibility(
    candidates: CandidateGrid,
    gate: EvaluationGate,
    budget: EvaluationStudyBudget,
) -> EvaluationFeasibilityReport:
    """Calculate the least expensive best-case design under the fixed protocol."""

    candidate_grid_sha256 = digest(canonical_bytes(candidates))
    if budget.candidate_grid_sha256 != candidate_grid_sha256:
        raise ValueError("study budget does not match the candidate grid")
    candidate_ids = tuple(route.candidate_id for route in candidates.routes)
    cost_ids = tuple(item.candidate_id for item in budget.route_cost_ceilings)
    if cost_ids != candidate_ids:
        raise ValueError("route cost ceilings must match the exact candidate order")

    stratum_count = len(budget.comparison_strata)
    route_count = len(candidates.routes)
    family_size = route_count * stratum_count * 3 * SPLIT_COUNT
    minimum_groups = gate.statistical_design.min_groups_per_metric
    detection_groups = _required_groups(
        1.0 - gate.min_detection_lower_bound, family_size, minimum_groups
    )
    clean_groups = _required_groups(
        gate.max_false_positive_upper_bound, family_size, minimum_groups
    )
    completion_groups = _required_groups(
        1.0 - gate.min_completion_lower_bound, family_size, minimum_groups
    )

    issues: list[FeasibilityIssue] = []
    if detection_groups is None:
        issues.append("exact_detection_target_unattainable")
    if clean_groups is None:
        issues.append("exact_clean_risk_target_unattainable")
    if completion_groups is None:
        issues.append("exact_completion_target_unattainable")

    gate_sha256 = digest(canonical_bytes(gate))
    if None in (detection_groups, clean_groups, completion_groups):
        return EvaluationFeasibilityReport(
            candidate_grid_sha256=candidate_grid_sha256,
            gate_sha256=gate_sha256,
            budget_sha256=budget.budget_sha256,
            confidence_family_size=family_size,
            interval_alpha=FAMILY_CONFIDENCE_ERROR / family_size,
            best_case_required_detection_groups_per_stratum_split=detection_groups,
            best_case_required_clean_groups_per_stratum_split=clean_groups,
            best_case_required_completion_groups_per_stratum_split=completion_groups,
            best_case_minimum_clean_cases=None,
            best_case_minimum_defective_cases=None,
            best_case_minimum_total_cases=None,
            best_case_minimum_clean_assignments=None,
            best_case_minimum_total_assignments=None,
            best_case_maximum_total_cost_microusd=None,
            within_dataset_case_ceiling=None,
            within_assignment_ceiling=None,
            within_spend_ceiling=None,
            minimum_resource_feasible=False,
            issues=tuple(issues),
        )
    assert detection_groups is not None
    assert clean_groups is not None
    assert completion_groups is not None

    # The lower bound allows clean and defective cases to share group identities.
    # Completion can reuse those groups and needs extra cases only for additional
    # independent groups beyond both quality-metric requirements.
    shared_quality_groups = max(detection_groups, clean_groups)
    extra_completion_cases = max(0, completion_groups - shared_quality_groups)
    stratum_split_multiplier = stratum_count * SPLIT_COUNT
    clean_cases = clean_groups * stratum_split_multiplier
    defective_cases = detection_groups * stratum_split_multiplier
    total_cases = (
        detection_groups + clean_groups + extra_completion_cases
    ) * stratum_split_multiplier
    clean_assignments = clean_cases * route_count * budget.repetitions
    total_assignments = total_cases * route_count * budget.repetitions
    route_cost_sum = sum(item.max_cost_microusd for item in budget.route_cost_ceilings)
    total_cost = (
        total_cases * budget.repetitions * route_cost_sum
        + budget.non_assignment_cost_ceiling_microusd
    )

    within_cases = total_cases <= budget.dataset_case_ceiling
    within_assignments = total_assignments <= budget.assignment_ceiling
    within_spend = total_cost <= budget.spend_ceiling_microusd
    if not within_cases:
        issues.append("dataset_case_ceiling_exceeded")
    if not within_assignments:
        issues.append("assignment_ceiling_exceeded")
    if not within_spend:
        issues.append("spend_ceiling_exceeded")

    return EvaluationFeasibilityReport(
        candidate_grid_sha256=candidate_grid_sha256,
        gate_sha256=gate_sha256,
        budget_sha256=budget.budget_sha256,
        confidence_family_size=family_size,
        interval_alpha=FAMILY_CONFIDENCE_ERROR / family_size,
        best_case_required_detection_groups_per_stratum_split=detection_groups,
        best_case_required_clean_groups_per_stratum_split=clean_groups,
        best_case_required_completion_groups_per_stratum_split=completion_groups,
        best_case_minimum_clean_cases=clean_cases,
        best_case_minimum_defective_cases=defective_cases,
        best_case_minimum_total_cases=total_cases,
        best_case_minimum_clean_assignments=clean_assignments,
        best_case_minimum_total_assignments=total_assignments,
        best_case_maximum_total_cost_microusd=total_cost,
        within_dataset_case_ceiling=within_cases,
        within_assignment_ceiling=within_assignments,
        within_spend_ceiling=within_spend,
        minimum_resource_feasible=not issues,
        issues=tuple(issues),
    )
