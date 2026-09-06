"""Profile-aware calibration scoring from fully reverified dual-grade lineage."""

from __future__ import annotations

from collections import defaultdict
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
from mos_eisley.evaluation.models import EvaluationDataset, EvaluationGate, SweepPlan
from mos_eisley.evaluation.resolution import (
    DualGradingResolution,
    ResolutionTrustPolicy,
)
from mos_eisley.evaluation.routing_protocol import (
    DifficultyProfile,
    PromptFeatureManifest,
    SealedRoutingStudy,
    verify_sealed_routing_study,
)
from mos_eisley.evaluation.scoring import (
    RouteScore,
    score_route_subset,
    validate_observation_matrix,
)
from mos_eisley.evaluation.statistics import MAX_CONFIDENCE_FAMILY


class ProfileCalibrationScore(Contract):
    profile_id: Digest
    profile: DifficultyProfile
    comparison_strata: Annotated[int, Field(ge=1, le=5000)]
    statistical_family: Literal["all_profiles_routes_metrics_both_splits"] = (
        "all_profiles_routes_metrics_both_splits"
    )
    family_size: Annotated[int, Field(ge=6, le=MAX_CONFIDENCE_FAMILY)]
    scores: Annotated[tuple[RouteScore, ...], Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def consistent_profile_and_routes(self) -> Self:
        if self.profile_id != self.profile.profile_id:
            raise ValueError("calibration profile identity mismatch")
        candidate_ids = tuple(score.candidate_id for score in self.scores)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("calibration profile routes must be unique")
        expected_family_size = len(self.scores) * self.comparison_strata * 3 * 2
        if self.family_size != expected_family_size or any(
            score.statistical_assessment.family_size != self.family_size
            for score in self.scores
        ):
            raise ValueError("calibration profile confidence family mismatch")
        return self


class RoutingCalibrationReport(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["sealed_profile_calibration"] = "sealed_profile_calibration"
    split: Literal["calibration"] = "calibration"
    promotion_ready: Literal[False] = False
    activation_authorized: Literal[False] = False
    sealed_study_sha256: Digest
    protocol_sha256: Digest
    feature_manifest_sha256: Digest
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
    gate: EvaluationGate
    profiles: Annotated[
        tuple[ProfileCalibrationScore, ...], Field(min_length=1, max_length=5000)
    ]

    @model_validator(mode="after")
    def canonical_profiles_and_routes(self) -> Self:
        profile_ids = tuple(item.profile_id for item in self.profiles)
        if tuple(sorted(set(profile_ids))) != profile_ids:
            raise ValueError("calibration profiles must be unique and sorted")
        candidate_sets = {
            tuple(score.candidate_id for score in item.scores) for item in self.profiles
        }
        if len(candidate_sets) != 1:
            raise ValueError("calibration profiles must score the same route set")
        if any(item.comparison_strata != len(self.profiles) for item in self.profiles):
            raise ValueError("calibration comparison strata must cover all profiles")
        return self

    @property
    def calibration_report_sha256(self) -> str:
        return digest(canonical_bytes(self))


def score_routing_calibration(
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
    manifest: PromptFeatureManifest,
    sealed_study: SealedRoutingStudy,
) -> RoutingCalibrationReport:
    """Score calibration only; no holdout selector exists on this boundary."""
    verify_sealed_routing_study(dataset, plan, manifest, sealed_study)
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
    validate_observation_matrix(plan, dataset, observations.observations, "calibration")

    protocol = sealed_study.protocol
    cases = {case.id: case for case in dataset.cases}
    profiles: dict[str, DifficultyProfile] = {}
    case_ids: dict[str, set[str]] = defaultdict(set)
    for assignment in manifest.assignments:
        case = cases[assignment.case_id]
        profile = protocol.feature_partition.profile(assignment.features)
        profiles[profile.profile_id] = profile
        if case.split == "calibration":
            case_ids[profile.profile_id].add(case.id)
    if tuple(sorted(profiles)) != sealed_study.profile_ids:
        raise ValueError("sealed routing study profile coverage mismatch")

    comparison_strata = len(profiles)
    results = tuple(
        ProfileCalibrationScore(
            profile_id=profile_id,
            profile=profiles[profile_id],
            comparison_strata=comparison_strata,
            family_size=len(plan.routes) * comparison_strata * 3 * 2,
            scores=tuple(
                score_route_subset(
                    route,
                    plan,
                    dataset,
                    observations.observations,
                    "calibration",
                    frozenset(case_ids[profile_id]),
                    comparison_strata,
                )
                for route in plan.routes
            ),
        )
        for profile_id in sorted(profiles)
    )
    return RoutingCalibrationReport(
        sealed_study_sha256=sealed_study.sealed_study_sha256,
        protocol_sha256=protocol.protocol_sha256,
        feature_manifest_sha256=manifest.manifest_sha256,
        dataset_sha256=dataset.dataset_sha256,
        plan_sha256=plan.plan_sha256,
        execution_batch_sha256=batch.batch_sha256,
        mapping_sha256=mapping.mapping_sha256,
        raw_results_sha256=raw_results.raw_results_sha256,
        grading_batch_sha256=grading_batch.grading_batch_sha256,
        grading_trust_policy_sha256=grading_policy.policy_sha256,
        resolution_trust_policy_sha256=resolution_policy.policy_sha256,
        dual_grading_resolution_sha256=dual_grading.dual_grading_resolution_sha256,
        dual_graded_observations_sha256=observations.dual_graded_observations_sha256,
        gate=plan.gate,
        profiles=results,
    )


def verify_routing_calibration_report(
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
    manifest: PromptFeatureManifest,
    sealed_study: SealedRoutingStudy,
    artifact: RoutingCalibrationReport,
) -> None:
    """Recompute profile scores from every independent source artifact."""
    rebuilt = score_routing_calibration(
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
        manifest,
        sealed_study,
    )
    if rebuilt != artifact:
        raise ValueError("routing calibration report provenance mismatch")
