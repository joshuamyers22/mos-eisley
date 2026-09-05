"""Deterministic sweep planning and conservative held-out quality gates."""

from __future__ import annotations

import hashlib
import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest
from mos_eisley.evaluation.models import (
    MAX_ASSIGNMENTS,
    Assignment,
    CandidateGrid,
    EvaluationDataset,
    EvaluationGate,
    Observation,
    ObservationSet,
    RouteCandidate,
    Split,
    SweepPlan,
)
from mos_eisley.evaluation.statistics import StatisticalAssessment, assess_groups

Z_95 = 1.959963984540054


class RateInterval(Contract):
    successes: Annotated[int, Field(ge=0)]
    trials: Annotated[int, Field(gt=0)]
    estimate: Annotated[float, Field(ge=0.0, le=1.0)]
    lower: Annotated[float, Field(ge=0.0, le=1.0)]
    upper: Annotated[float, Field(ge=0.0, le=1.0)]
    method: Literal["wilson_95"] = "wilson_95"


class RouteScore(Contract):
    candidate_id: Digest
    route: RouteCandidate
    detection: RateInterval
    clean_false_positive_runs: RateInterval
    completion: RateInterval
    statistical_assessment: StatisticalAssessment
    mean_cost_microusd: float | None
    cost_coverage: Annotated[float, Field(ge=0.0, le=1.0)]
    p95_latency_ms: Annotated[int, Field(ge=0)]
    passes_detection: bool
    passes_false_positives: bool
    passes_completion: bool
    passes_cost: bool
    passes_latency: bool
    eligible: bool

    @model_validator(mode="after")
    def route_identity_matches(self) -> Self:
        if self.candidate_id != self.route.candidate_id:
            raise ValueError("route score candidate identity mismatch")
        return self


class EvaluationReport(Contract):
    schema_version: Literal[2] = 2
    promotion_ready: Literal[False] = False
    plan_sha256: Digest
    dataset_sha256: Digest
    observations_sha256: Digest
    raw_results_sha256: Digest
    adjudication_sha256: Digest
    split: Split
    gate: EvaluationGate
    scores: tuple[RouteScore, ...]


def _order_key(seed: int, assignment: Assignment) -> bytes:
    value = (
        f"{seed}\0{assignment.case_id}\0{assignment.candidate_id}\0"
        f"{assignment.repetition}"
    )
    return hashlib.sha256(value.encode()).digest()


def make_plan(
    dataset: EvaluationDataset,
    candidates: CandidateGrid,
    repetitions: int,
    randomization_seed: int,
    gate: EvaluationGate,
) -> SweepPlan:
    if not 1 <= repetitions <= 100:
        raise ValueError("repetitions must be between 1 and 100")
    if not 0 <= randomization_seed <= 9_223_372_036_854_775_807:
        raise ValueError("randomization seed is outside the supported range")
    assignment_count = len(dataset.cases) * len(candidates.routes) * repetitions
    if assignment_count > MAX_ASSIGNMENTS:
        raise ValueError("evaluation matrix exceeds the assignment limit")
    assignments = [
        Assignment(
            case_id=case.id,
            split=case.split,
            candidate_id=route.candidate_id,
            repetition=repetition,
        )
        for case in dataset.cases
        for route in candidates.routes
        for repetition in range(repetitions)
    ]
    assignments.sort(key=lambda item: _order_key(randomization_seed, item))
    return SweepPlan(
        dataset_sha256=dataset.dataset_sha256,
        routes=candidates.routes,
        repetitions=repetitions,
        randomization_seed=randomization_seed,
        gate=gate,
        assignments=tuple(assignments),
    )


def _wilson(successes: int, trials: int) -> RateInterval:
    estimate = successes / trials
    denominator = 1.0 + Z_95**2 / trials
    center = (estimate + Z_95**2 / (2.0 * trials)) / denominator
    margin = (
        Z_95
        * math.sqrt(estimate * (1.0 - estimate) / trials + Z_95**2 / (4.0 * trials**2))
        / denominator
    )
    return RateInterval(
        successes=successes,
        trials=trials,
        estimate=estimate,
        lower=max(0.0, center - margin),
        upper=min(1.0, center + margin),
    )


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _expected_assignments(
    plan: SweepPlan, dataset: EvaluationDataset, split: Split
) -> set[tuple[str, str, int]]:
    return {
        (case.id, route.candidate_id, repetition)
        for case in dataset.cases
        if case.split == split
        for route in plan.routes
        for repetition in range(plan.repetitions)
    }


def _validate_observation_matrix(
    plan: SweepPlan,
    dataset: EvaluationDataset,
    observations: tuple[Observation, ...],
    split: Split,
) -> None:
    plan.validate_dataset(dataset)
    expected = _expected_assignments(plan, dataset, split)
    keys = tuple(observation.key for observation in observations)
    if len(keys) != len(set(keys)):
        raise ValueError("observations must have unique assignment keys")
    if set(keys) != expected:
        raise ValueError("observations do not exactly cover the requested split")


def _score_route(
    route: RouteCandidate,
    plan: SweepPlan,
    dataset: EvaluationDataset,
    observations: tuple[Observation, ...],
    split: Split,
) -> RouteScore:
    cases = {case.id: case for case in dataset.cases if case.split == split}
    selected = [
        observation
        for observation in observations
        if observation.candidate_id == route.candidate_id
    ]
    defect_trials = sum(len(cases[item.case_id].expected_findings) for item in selected)
    clean = [item for item in selected if not cases[item.case_id].expected_findings]
    if defect_trials == 0 or not clean:
        raise ValueError("each scored route needs defective and clean trials")

    detections = 0
    for item in selected:
        expected_ids = {finding.id for finding in cases[item.case_id].expected_findings}
        if not set(item.detected_finding_ids) <= expected_ids:
            raise ValueError("observation contains an unknown detected finding id")
        detections += len(item.detected_finding_ids)

    detection = _wilson(detections, defect_trials)
    false_positives = _wilson(
        sum(item.false_positive_count > 0 for item in clean), len(clean)
    )
    completion = _wilson(
        sum(item.status == "completed" for item in selected), len(selected)
    )
    assessment = assess_groups(
        cases, selected, plan.gate.statistical_design, len(plan.routes)
    )
    costs = [item.cost_microusd for item in selected if item.cost_microusd is not None]
    mean_cost = sum(costs) / len(costs) if costs else None
    cost_coverage = len(costs) / len(selected)
    gate = plan.gate
    passes_cost = gate.max_mean_cost_microusd is None or (
        cost_coverage == 1.0
        and mean_cost is not None
        and mean_cost <= gate.max_mean_cost_microusd
    )
    p95_latency = _p95([item.latency_ms for item in selected])
    passes_latency = (
        gate.max_p95_latency_ms is None or p95_latency <= gate.max_p95_latency_ms
    )
    checks = (
        assessment.detection is not None
        and assessment.detection.lower >= gate.min_detection_lower_bound,
        assessment.clean_false_positive_runs is not None
        and assessment.clean_false_positive_runs.upper
        <= gate.max_false_positive_upper_bound,
        assessment.completion is not None
        and assessment.completion.lower >= gate.min_completion_lower_bound,
        passes_cost,
        passes_latency,
    )
    return RouteScore(
        candidate_id=route.candidate_id,
        route=route,
        detection=detection,
        clean_false_positive_runs=false_positives,
        completion=completion,
        statistical_assessment=assessment,
        mean_cost_microusd=mean_cost,
        cost_coverage=cost_coverage,
        p95_latency_ms=p95_latency,
        passes_detection=checks[0],
        passes_false_positives=checks[1],
        passes_completion=checks[2],
        passes_cost=checks[3],
        passes_latency=checks[4],
        eligible=assessment.sufficient_groups and all(checks),
    )


def score_observation_matrix(
    plan: SweepPlan,
    dataset: EvaluationDataset,
    observations: tuple[Observation, ...],
    split: Split,
) -> tuple[RouteScore, ...]:
    """Score one exact split after source-specific provenance validation."""
    _validate_observation_matrix(plan, dataset, observations, split)
    return tuple(
        _score_route(route, plan, dataset, observations, split) for route in plan.routes
    )


def score(
    plan: SweepPlan,
    dataset: EvaluationDataset,
    observations: ObservationSet,
    split: Split,
) -> EvaluationReport:
    """Score one split exactly; omissions and cross-split leakage are rejected."""
    if observations.plan_sha256 != plan.plan_sha256:
        raise ValueError("observations do not match the sweep plan")
    scores = score_observation_matrix(plan, dataset, observations.observations, split)
    return EvaluationReport(
        plan_sha256=plan.plan_sha256,
        dataset_sha256=dataset.dataset_sha256,
        observations_sha256=observations.observations_sha256,
        raw_results_sha256=observations.raw_results_sha256,
        adjudication_sha256=observations.adjudication_sha256,
        split=split,
        gate=plan.gate,
        scores=scores,
    )
