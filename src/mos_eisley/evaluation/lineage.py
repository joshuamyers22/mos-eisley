"""Compile observations without discarding authenticated dual-grade lineage."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.evaluation.adjudication import (
    GradingBatch,
    join_validated_judgments,
    make_grading_batch,
)
from mos_eisley.evaluation.authentication import GradingTrustPolicy
from mos_eisley.evaluation.execution import BlindingMap, ExecutionBatch, RawResultSet
from mos_eisley.evaluation.models import (
    MAX_ASSIGNMENTS,
    EvaluationDataset,
    Observation,
    SweepPlan,
)
from mos_eisley.evaluation.resolution import (
    DualGradingResolution,
    ResolutionTrustPolicy,
    verify_dual_grading_resolution,
)


class DualGradedObservationSet(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["dual_authenticated_grading"] = "dual_authenticated_grading"
    promotion_eligible: Literal[False] = False
    dataset_sha256: Digest
    plan_sha256: Digest
    execution_batch_sha256: Digest
    mapping_sha256: Digest
    raw_results_sha256: Digest
    grading_batch_sha256: Digest
    grading_trust_policy_sha256: Digest
    resolution_trust_policy_sha256: Digest
    dual_grading_resolution_sha256: Digest
    observations: Annotated[
        tuple[Observation, ...], Field(min_length=1, max_length=MAX_ASSIGNMENTS)
    ]

    @model_validator(mode="after")
    def unique_observations(self) -> Self:
        keys = tuple(observation.key for observation in self.observations)
        if len(keys) != len(set(keys)):
            raise ValueError("observations must have unique assignment keys")
        if any(
            observation.adjudication != "human" for observation in self.observations
        ):
            raise ValueError("dual-graded observations require human adjudication")
        return self

    @property
    def dual_graded_observations_sha256(self) -> str:
        return digest(canonical_bytes(self))


def compile_dual_graded_observations(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    batch: ExecutionBatch,
    mapping: BlindingMap,
    raw_results: RawResultSet,
    grading_batch: GradingBatch,
    dual_grading: DualGradingResolution,
    grading_policy: GradingTrustPolicy,
    resolution_policy: ResolutionTrustPolicy,
) -> DualGradedObservationSet:
    """Join labels only after reverifying the complete dual-grade source chain."""
    expected_grading_batch = make_grading_batch(
        dataset, plan, batch, mapping, raw_results
    )
    if grading_batch != expected_grading_batch:
        raise ValueError("grading batch does not match its source artifacts")
    verify_dual_grading_resolution(
        grading_batch, dual_grading, grading_policy, resolution_policy
    )
    observations = join_validated_judgments(
        mapping, raw_results, dual_grading.resolved_judgments, "human"
    )
    return DualGradedObservationSet(
        dataset_sha256=dataset.dataset_sha256,
        plan_sha256=plan.plan_sha256,
        execution_batch_sha256=batch.batch_sha256,
        mapping_sha256=mapping.mapping_sha256,
        raw_results_sha256=raw_results.raw_results_sha256,
        grading_batch_sha256=grading_batch.grading_batch_sha256,
        grading_trust_policy_sha256=grading_policy.policy_sha256,
        resolution_trust_policy_sha256=resolution_policy.policy_sha256,
        dual_grading_resolution_sha256=(dual_grading.dual_grading_resolution_sha256),
        observations=observations,
    )


def verify_dual_graded_observations(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    batch: ExecutionBatch,
    mapping: BlindingMap,
    raw_results: RawResultSet,
    grading_batch: GradingBatch,
    dual_grading: DualGradingResolution,
    grading_policy: GradingTrustPolicy,
    resolution_policy: ResolutionTrustPolicy,
    artifact: DualGradedObservationSet,
) -> None:
    """Rebuild stored observations from independently supplied source artifacts."""
    rebuilt = compile_dual_graded_observations(
        dataset,
        plan,
        batch,
        mapping,
        raw_results,
        grading_batch,
        dual_grading,
        grading_policy,
        resolution_policy,
    )
    if rebuilt != artifact:
        raise ValueError("dual-graded observation provenance mismatch")
