"""Score only reverified dual-grade observations while promotion stays disabled."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.evaluation.adjudication import GradingBatch
from mos_eisley.evaluation.authentication import GradingTrustPolicy
from mos_eisley.evaluation.execution import BlindingMap, ExecutionBatch, RawResultSet
from mos_eisley.evaluation.lineage import (
    DualGradedObservationSet,
    verify_dual_graded_observations,
)
from mos_eisley.evaluation.models import (
    EvaluationDataset,
    EvaluationGate,
    Split,
    SweepPlan,
)
from mos_eisley.evaluation.resolution import (
    DualGradingResolution,
    ResolutionTrustPolicy,
)
from mos_eisley.evaluation.scoring import RouteScore, score_observation_matrix


class DualLineageEvaluationReport(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["dual_authenticated_scoring"] = "dual_authenticated_scoring"
    promotion_ready: Literal[False] = False
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
    split: Split
    gate: EvaluationGate
    scores: Annotated[tuple[RouteScore, ...], Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def unique_routes(self) -> Self:
        candidate_ids = tuple(score.candidate_id for score in self.scores)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("dual-lineage report routes must be unique")
        return self

    @property
    def dual_lineage_report_sha256(self) -> str:
        return digest(canonical_bytes(self))


def score_dual_graded_observations(
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
    split: Split,
) -> DualLineageEvaluationReport:
    """Reverify all source artifacts before calculating one exact split."""
    verify_dual_graded_observations(
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
    )
    scores = score_observation_matrix(plan, dataset, observations.observations, split)
    return DualLineageEvaluationReport(
        dataset_sha256=dataset.dataset_sha256,
        plan_sha256=plan.plan_sha256,
        execution_batch_sha256=batch.batch_sha256,
        mapping_sha256=mapping.mapping_sha256,
        raw_results_sha256=raw_results.raw_results_sha256,
        grading_batch_sha256=grading_batch.grading_batch_sha256,
        grading_trust_policy_sha256=grading_policy.policy_sha256,
        resolution_trust_policy_sha256=resolution_policy.policy_sha256,
        dual_grading_resolution_sha256=(dual_grading.dual_grading_resolution_sha256),
        dual_graded_observations_sha256=(observations.dual_graded_observations_sha256),
        split=split,
        gate=plan.gate,
        scores=scores,
    )


def verify_dual_lineage_evaluation_report(
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
    artifact: DualLineageEvaluationReport,
) -> None:
    """Recompute a stored report from every independently supplied source."""
    rebuilt = score_dual_graded_observations(
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
        artifact.split,
    )
    if rebuilt != artifact:
        raise ValueError("dual-lineage evaluation report provenance mismatch")
