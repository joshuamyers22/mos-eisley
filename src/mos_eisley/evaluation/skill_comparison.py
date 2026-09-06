"""Pre-registered paired evaluation of exact prompt-skill revisions."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.evaluation.adjudication import GradingBatch
from mos_eisley.evaluation.authentication import GradingTrustPolicy
from mos_eisley.evaluation.execution import BlindingMap, ExecutionBatch, RawResultSet
from mos_eisley.evaluation.lineage import DualGradedObservationSet
from mos_eisley.evaluation.lineage_scoring import score_dual_graded_observations
from mos_eisley.evaluation.models import (
    EvaluationDataset,
    Observation,
    Rate,
    RouteCandidate,
    Split,
    SweepPlan,
)
from mos_eisley.evaluation.resolution import (
    DualGradingResolution,
    ResolutionTrustPolicy,
)
from mos_eisley.evaluation.scoring import validate_observation_matrix

Delta = Annotated[float, Field(ge=-1.0, le=1.0)]
MAX_DELTA_MICROUSD = 1_000_000_000_000_000
MAX_DELTA_LATENCY_MS = 86_400_000
PAIRED_FAMILY_SIZE = 6


class SkillComparisonGate(Contract):
    schema_version: Literal[1] = 1
    max_detection_regression: Rate
    max_false_positive_increase: Rate
    max_completion_regression: Rate
    max_mean_cost_increase_microusd: (
        Annotated[int, Field(ge=-MAX_DELTA_MICROUSD, le=MAX_DELTA_MICROUSD)] | None
    ) = None
    max_p95_latency_increase_ms: (
        Annotated[int, Field(ge=-MAX_DELTA_LATENCY_MS, le=MAX_DELTA_LATENCY_MS)] | None
    ) = None


class SkillComparisonProtocol(Contract):
    """Fixed comparison design authored before either arm is inspected."""

    schema_version: Literal[1] = 1
    experiment_id: Identifier
    activation_authorized: Literal[False] = False
    dataset_sha256: Digest
    plan_sha256: Digest
    baseline_candidate_id: Digest
    candidate_candidate_id: Digest
    estimand: Literal["equal_independence_group_paired_delta"] = (
        "equal_independence_group_paired_delta"
    )
    stopping_rule: Literal["fixed_complete_matrix"] = "fixed_complete_matrix"
    family_scope: Literal["three_paired_metrics_both_splits"] = (
        "three_paired_metrics_both_splits"
    )
    holdout_rule: Literal["seal_before_holdout_then_evaluate_once"] = (
        "seal_before_holdout_then_evaluate_once"
    )
    gate: SkillComparisonGate

    @model_validator(mode="after")
    def distinct_arms(self) -> Self:
        if self.baseline_candidate_id == self.candidate_candidate_id:
            raise ValueError("skill comparison arms must be distinct")
        return self

    @property
    def protocol_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SealedSkillComparison(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["sealed_skill_comparison"] = "sealed_skill_comparison"
    activation_authorized: Literal[False] = False
    protocol: SkillComparisonProtocol
    dataset_sha256: Digest
    plan_sha256: Digest
    baseline_prompt_sha256: Digest
    candidate_prompt_sha256: Digest

    @property
    def sealed_comparison_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillHoldoutUseClaim(Contract):
    """Deterministic payload consumed exclusively before holdout scoring."""

    schema_version: Literal[1] = 1
    mode: Literal["skill_comparison_holdout_use_claim"] = (
        "skill_comparison_holdout_use_claim"
    )
    consumed: Literal[True] = True
    activation_authorized: Literal[False] = False
    sealed_comparison_sha256: Digest
    dataset_sha256: Digest
    plan_sha256: Digest
    execution_batch_sha256: Digest
    mapping_sha256: Digest
    raw_results_sha256: Digest
    grading_batch_sha256: Digest
    grading_trust_policy_sha256: Digest
    resolution_trust_policy_sha256: Digest
    dual_grading_resolution_sha256: Digest
    dual_graded_observations_sha256: Digest

    @property
    def claim_sha256(self) -> str:
        return digest(canonical_bytes(self))


class PairedDeltaInterval(Contract):
    method: Literal["paired_group_hoeffding_bonferroni_95_family"] = (
        "paired_group_hoeffding_bonferroni_95_family"
    )
    groups: Annotated[int, Field(ge=1, le=5000)]
    estimate: Delta
    lower: Delta
    upper: Delta
    radius: Annotated[float, Field(gt=0)]

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        expected_radius = math.sqrt(
            2 * math.log(2 * PAIRED_FAMILY_SIZE / 0.05) / self.groups
        )
        if self.radius != expected_radius:
            raise ValueError("paired interval radius is inconsistent")
        if self.lower != max(-1.0, self.estimate - self.radius) or self.upper != min(
            1.0, self.estimate + self.radius
        ):
            raise ValueError("paired interval bounds are inconsistent")
        return self


class SkillComparisonReport(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["dual_authenticated_skill_comparison"] = (
        "dual_authenticated_skill_comparison"
    )
    promotion_ready: Literal[False] = False
    activation_authorized: Literal[False] = False
    sealed_comparison_sha256: Digest
    holdout_use_claim_sha256: Digest | None
    dual_lineage_report_sha256: Digest
    dataset_sha256: Digest
    plan_sha256: Digest
    dual_graded_observations_sha256: Digest
    split: Split
    baseline_candidate_id: Digest
    candidate_candidate_id: Digest
    baseline_prompt_sha256: Digest
    candidate_prompt_sha256: Digest
    gate: SkillComparisonGate
    minimum_groups_per_metric: Annotated[int, Field(ge=2, le=5000)]
    detection_delta: PairedDeltaInterval
    clean_false_positive_delta: PairedDeltaInterval
    completion_delta: PairedDeltaInterval
    mean_cost_delta_microusd: (
        Annotated[float, Field(ge=-MAX_DELTA_MICROUSD, le=MAX_DELTA_MICROUSD)] | None
    )
    paired_cost_coverage: Annotated[float, Field(ge=0.0, le=1.0)]
    p95_latency_delta_ms: Annotated[
        int, Field(ge=-MAX_DELTA_LATENCY_MS, le=MAX_DELTA_LATENCY_MS)
    ]
    passes_detection_noninferiority: bool
    passes_false_positive_noninferiority: bool
    passes_completion_noninferiority: bool
    passes_cost: bool
    passes_latency: bool
    sufficient_groups: bool
    passes_registered_gate: bool

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        expected_sufficient = all(
            interval.groups >= self.minimum_groups_per_metric
            for interval in (
                self.detection_delta,
                self.clean_false_positive_delta,
                self.completion_delta,
            )
        )
        expected_detection = (
            self.detection_delta.lower >= -self.gate.max_detection_regression
        )
        expected_false_positive = (
            self.clean_false_positive_delta.upper
            <= self.gate.max_false_positive_increase
        )
        expected_completion = (
            self.completion_delta.lower >= -self.gate.max_completion_regression
        )
        expected_cost = self.gate.max_mean_cost_increase_microusd is None or (
            self.paired_cost_coverage == 1.0
            and self.mean_cost_delta_microusd is not None
            and self.mean_cost_delta_microusd
            <= self.gate.max_mean_cost_increase_microusd
        )
        expected_latency = self.gate.max_p95_latency_increase_ms is None or (
            self.p95_latency_delta_ms <= self.gate.max_p95_latency_increase_ms
        )
        supplied = (
            self.sufficient_groups,
            self.passes_detection_noninferiority,
            self.passes_false_positive_noninferiority,
            self.passes_completion_noninferiority,
            self.passes_cost,
            self.passes_latency,
        )
        expected_components = (
            expected_sufficient,
            expected_detection,
            expected_false_positive,
            expected_completion,
            expected_cost,
            expected_latency,
        )
        if supplied != expected_components:
            raise ValueError("skill comparison component gate result is inconsistent")
        expected = expected_sufficient and all(
            (
                expected_detection,
                expected_false_positive,
                expected_completion,
                expected_cost,
                expected_latency,
            )
        )
        if self.passes_registered_gate != expected:
            raise ValueError("skill comparison gate result is inconsistent")
        if self.baseline_candidate_id == self.candidate_candidate_id:
            raise ValueError("skill comparison report arms must be distinct")
        if self.baseline_prompt_sha256 == self.candidate_prompt_sha256:
            raise ValueError("skill comparison report prompts must differ")
        if (self.split == "holdout") != (self.holdout_use_claim_sha256 is not None):
            raise ValueError("skill comparison holdout claim presence is inconsistent")
        return self

    @property
    def skill_comparison_report_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _controlled_routes(
    protocol: SkillComparisonProtocol, plan: SweepPlan
) -> tuple[RouteCandidate, RouteCandidate]:
    if len(plan.routes) != 2:
        raise ValueError("skill comparison plans require exactly two routes")
    routes = {route.candidate_id: route for route in plan.routes}
    if set(routes) != {
        protocol.baseline_candidate_id,
        protocol.candidate_candidate_id,
    }:
        raise ValueError("skill comparison protocol does not cover both plan routes")
    baseline = routes[protocol.baseline_candidate_id]
    candidate = routes[protocol.candidate_candidate_id]
    if candidate.prompt.mode != "skill" or candidate.prompt.skill is None:
        raise ValueError("candidate arm must use an exact persona skill")
    if baseline.prompt.prompt_sha256 == candidate.prompt.prompt_sha256:
        raise ValueError("skill comparison prompt assets must differ")
    if baseline.model_copy(update={"prompt": candidate.prompt}) != candidate:
        raise ValueError("skill comparison arms may differ only by prompt asset")
    return baseline, candidate


def _group_counts(dataset: EvaluationDataset, split: Split) -> tuple[int, int, int]:
    cases = [case for case in dataset.cases if case.split == split]
    if any(case.independence_group is None for case in cases):
        raise ValueError("skill comparison requires declared independence groups")
    defect = {case.independence_group for case in cases if case.expected_findings}
    clean = {case.independence_group for case in cases if not case.expected_findings}
    all_groups = {case.independence_group for case in cases}
    return len(defect), len(clean), len(all_groups)


def seal_skill_comparison(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    protocol: SkillComparisonProtocol,
) -> SealedSkillComparison:
    """Validate prompt-only experimental control before reading outcomes."""

    plan.validate_dataset(dataset)
    if protocol.dataset_sha256 != dataset.dataset_sha256:
        raise ValueError("skill comparison protocol does not match the dataset")
    if protocol.plan_sha256 != plan.plan_sha256:
        raise ValueError("skill comparison protocol does not match the plan")
    baseline, candidate = _controlled_routes(protocol, plan)
    minimum = plan.gate.statistical_design.min_groups_per_metric
    for split in ("calibration", "holdout"):
        if any(count < minimum for count in _group_counts(dataset, split)):
            raise ValueError("skill comparison has too few independent groups")
    return SealedSkillComparison(
        protocol=protocol,
        dataset_sha256=dataset.dataset_sha256,
        plan_sha256=plan.plan_sha256,
        baseline_prompt_sha256=baseline.prompt.prompt_sha256,
        candidate_prompt_sha256=candidate.prompt.prompt_sha256,
    )


def verify_sealed_skill_comparison(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    artifact: SealedSkillComparison,
) -> None:
    if seal_skill_comparison(dataset, plan, artifact.protocol) != artifact:
        raise ValueError("sealed skill comparison provenance mismatch")


def make_skill_holdout_use_claim(
    sealed: SealedSkillComparison,
    batch: ExecutionBatch,
    mapping: BlindingMap,
    raw_results: RawResultSet,
    grading_batch: GradingBatch,
    dual_grading: DualGradingResolution,
    grading_policy: GradingTrustPolicy,
    resolution_policy: ResolutionTrustPolicy,
    observations: DualGradedObservationSet,
) -> SkillHoldoutUseClaim:
    return SkillHoldoutUseClaim(
        sealed_comparison_sha256=sealed.sealed_comparison_sha256,
        dataset_sha256=sealed.dataset_sha256,
        plan_sha256=sealed.plan_sha256,
        execution_batch_sha256=batch.batch_sha256,
        mapping_sha256=mapping.mapping_sha256,
        raw_results_sha256=raw_results.raw_results_sha256,
        grading_batch_sha256=grading_batch.grading_batch_sha256,
        grading_trust_policy_sha256=grading_policy.policy_sha256,
        resolution_trust_policy_sha256=resolution_policy.policy_sha256,
        dual_grading_resolution_sha256=(dual_grading.dual_grading_resolution_sha256),
        dual_graded_observations_sha256=(observations.dual_graded_observations_sha256),
    )


def _paired_interval(values: Sequence[float]) -> PairedDeltaInterval:
    if not values or not all(
        math.isfinite(value) and -1 <= value <= 1 for value in values
    ):
        raise ValueError("paired group deltas must be finite and within [-1, 1]")
    # Hoeffding for a variable with range width two, Bonferroni-corrected over
    # detection, false-positive risk, and completion across both splits.
    radius = math.sqrt(2 * math.log(2 * PAIRED_FAMILY_SIZE / 0.05) / len(values))
    estimate = math.fsum(values) / len(values)
    return PairedDeltaInterval(
        groups=len(values),
        estimate=estimate,
        lower=max(-1.0, estimate - radius),
        upper=min(1.0, estimate + radius),
        radius=radius,
    )


def _metric_delta(
    dataset: EvaluationDataset,
    observations: tuple[Observation, ...],
    split: Split,
    baseline_id: str,
    candidate_id: str,
    include: Callable[[int], bool],
    value: Callable[[Observation, int], float],
) -> PairedDeltaInterval:
    cases = {
        case.id: case
        for case in dataset.cases
        if case.split == split and include(len(case.expected_findings))
    }
    by_arm_case: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for item in observations:
        if item.case_id in cases and item.candidate_id in {baseline_id, candidate_id}:
            by_arm_case[(item.candidate_id, item.case_id)].append(item)
    group_values: dict[str, list[float]] = defaultdict(list)
    for case_id, case in cases.items():
        baseline = by_arm_case[(baseline_id, case_id)]
        candidate = by_arm_case[(candidate_id, case_id)]
        if not baseline or len(baseline) != len(candidate):
            raise ValueError("skill comparison observations are not paired")
        expected = len(case.expected_findings)
        baseline_value = math.fsum(value(item, expected) for item in baseline) / len(
            baseline
        )
        candidate_value = math.fsum(value(item, expected) for item in candidate) / len(
            candidate
        )
        group = case.independence_group
        if group is None:
            raise ValueError("skill comparison requires independence groups")
        group_values[group].append(candidate_value - baseline_value)
    return _paired_interval(
        tuple(
            math.fsum(values) / len(values)
            for _, values in sorted(group_values.items())
        )
    )


def _p95(values: Sequence[int]) -> int:
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _compare_verified_observations(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    observations: DualGradedObservationSet,
    sealed: SealedSkillComparison,
    split: Split,
    dual_lineage_report_sha256: str,
    holdout_use_claim_sha256: str | None,
) -> SkillComparisonReport:
    verify_sealed_skill_comparison(dataset, plan, sealed)
    validate_observation_matrix(plan, dataset, observations.observations, split)
    protocol = sealed.protocol
    baseline_id = protocol.baseline_candidate_id
    candidate_id = protocol.candidate_candidate_id
    detection = _metric_delta(
        dataset,
        observations.observations,
        split,
        baseline_id,
        candidate_id,
        lambda expected: expected > 0,
        lambda item, expected: len(item.detected_finding_ids) / expected,
    )
    false_positives = _metric_delta(
        dataset,
        observations.observations,
        split,
        baseline_id,
        candidate_id,
        lambda expected: expected == 0,
        lambda item, _: float(item.status == "error" or item.false_positive_count > 0),
    )
    completion = _metric_delta(
        dataset,
        observations.observations,
        split,
        baseline_id,
        candidate_id,
        lambda _: True,
        lambda item, _: float(item.status == "completed"),
    )
    indexed = {
        (item.case_id, item.repetition, item.candidate_id): item
        for item in observations.observations
    }
    pairs = [
        (
            indexed[(case.id, repetition, baseline_id)],
            indexed[(case.id, repetition, candidate_id)],
        )
        for case in dataset.cases
        if case.split == split
        for repetition in range(plan.repetitions)
    ]
    cost_deltas = [
        candidate.cost_microusd - baseline.cost_microusd
        for baseline, candidate in pairs
        if baseline.cost_microusd is not None and candidate.cost_microusd is not None
    ]
    mean_cost_delta = math.fsum(cost_deltas) / len(cost_deltas) if cost_deltas else None
    cost_coverage = len(cost_deltas) / len(pairs)
    latency_delta = _p95(
        [candidate.latency_ms - baseline.latency_ms for baseline, candidate in pairs]
    )
    gate = protocol.gate
    minimum = plan.gate.statistical_design.min_groups_per_metric
    sufficient = all(
        interval.groups >= minimum
        for interval in (detection, false_positives, completion)
    )
    passes_detection = detection.lower >= -gate.max_detection_regression
    passes_false_positives = false_positives.upper <= gate.max_false_positive_increase
    passes_completion = completion.lower >= -gate.max_completion_regression
    passes_cost = gate.max_mean_cost_increase_microusd is None or (
        cost_coverage == 1.0
        and mean_cost_delta is not None
        and mean_cost_delta <= gate.max_mean_cost_increase_microusd
    )
    passes_latency = gate.max_p95_latency_increase_ms is None or (
        latency_delta <= gate.max_p95_latency_increase_ms
    )
    passed = sufficient and all(
        (
            passes_detection,
            passes_false_positives,
            passes_completion,
            passes_cost,
            passes_latency,
        )
    )
    return SkillComparisonReport(
        sealed_comparison_sha256=sealed.sealed_comparison_sha256,
        holdout_use_claim_sha256=holdout_use_claim_sha256,
        dual_lineage_report_sha256=dual_lineage_report_sha256,
        dataset_sha256=dataset.dataset_sha256,
        plan_sha256=plan.plan_sha256,
        dual_graded_observations_sha256=(observations.dual_graded_observations_sha256),
        split=split,
        baseline_candidate_id=baseline_id,
        candidate_candidate_id=candidate_id,
        baseline_prompt_sha256=sealed.baseline_prompt_sha256,
        candidate_prompt_sha256=sealed.candidate_prompt_sha256,
        gate=gate,
        minimum_groups_per_metric=minimum,
        detection_delta=detection,
        clean_false_positive_delta=false_positives,
        completion_delta=completion,
        mean_cost_delta_microusd=mean_cost_delta,
        paired_cost_coverage=cost_coverage,
        p95_latency_delta_ms=latency_delta,
        passes_detection_noninferiority=passes_detection,
        passes_false_positive_noninferiority=passes_false_positives,
        passes_completion_noninferiority=passes_completion,
        passes_cost=passes_cost,
        passes_latency=passes_latency,
        sufficient_groups=sufficient,
        passes_registered_gate=passed,
    )


def score_authenticated_skill_comparison(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    batch: ExecutionBatch,
    mapping: BlindingMap,
    raw_results: RawResultSet,
    grading_batch: GradingBatch,
    dual_grading: DualGradingResolution,
    grading_policy: GradingTrustPolicy,
    resolution_policy: ResolutionTrustPolicy,
    observations: DualGradedObservationSet,
    sealed: SealedSkillComparison,
    split: Split,
    holdout_use_claim: SkillHoldoutUseClaim | None = None,
) -> SkillComparisonReport:
    """Reverify complete dual-grade lineage before paired prompt comparison."""

    expected_claim = make_skill_holdout_use_claim(
        sealed,
        batch,
        mapping,
        raw_results,
        grading_batch,
        dual_grading,
        grading_policy,
        resolution_policy,
        observations,
    )
    if split == "holdout":
        if holdout_use_claim != expected_claim:
            raise ValueError("skill comparison holdout use claim provenance mismatch")
    elif holdout_use_claim is not None:
        raise ValueError("calibration scoring cannot consume a holdout use claim")
    lineage_report = score_dual_graded_observations(
        dataset,
        plan,
        batch,
        mapping,
        raw_results,
        grading_batch,
        dual_grading,
        grading_policy,
        resolution_policy,
        observations,
        split,
    )
    return _compare_verified_observations(
        dataset,
        plan,
        observations,
        sealed,
        split,
        lineage_report.dual_lineage_report_sha256,
        holdout_use_claim.claim_sha256 if holdout_use_claim is not None else None,
    )


def verify_authenticated_skill_comparison_report(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    batch: ExecutionBatch,
    mapping: BlindingMap,
    raw_results: RawResultSet,
    grading_batch: GradingBatch,
    dual_grading: DualGradingResolution,
    grading_policy: GradingTrustPolicy,
    resolution_policy: ResolutionTrustPolicy,
    observations: DualGradedObservationSet,
    sealed: SealedSkillComparison,
    holdout_use_claim: SkillHoldoutUseClaim | None,
    artifact: SkillComparisonReport,
) -> None:
    """Recompute a stored report from every independently supplied source."""

    rebuilt = score_authenticated_skill_comparison(
        dataset,
        plan,
        batch,
        mapping,
        raw_results,
        grading_batch,
        dual_grading,
        grading_policy,
        resolution_policy,
        observations,
        sealed,
        artifact.split,
        holdout_use_claim,
    )
    if rebuilt != artifact:
        raise ValueError("skill comparison report provenance mismatch")
