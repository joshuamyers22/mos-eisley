"""Freeze a non-activating candidate policy from calibration evidence only."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.evaluation.adjudication import GradingBatch
from mos_eisley.evaluation.authentication import GradingTrustPolicy
from mos_eisley.evaluation.execution import BlindingMap, ExecutionBatch, RawResultSet
from mos_eisley.evaluation.lineage import DualGradedObservationSet
from mos_eisley.evaluation.models import EvaluationDataset, RouteCandidate, SweepPlan
from mos_eisley.evaluation.resolution import (
    DualGradingResolution,
    ResolutionTrustPolicy,
)
from mos_eisley.evaluation.routing_calibration import (
    ProfileCalibrationScore,
    RoutingCalibrationReport,
    verify_routing_calibration_report,
)
from mos_eisley.evaluation.routing_protocol import (
    DifficultyProfile,
    PromptFeatureManifest,
    RoleRouteConstraint,
    SealedRoutingStudy,
)

DecisionBasis = Literal[
    "calibrated_quality_and_cost",
    "no_quality_eligible_route",
    "no_cost_eligible_route",
    "incomplete_cost_evidence",
]
DecisionAction = Literal["calibrated_route", "role_fallback", "fail_closed"]


class FrozenProfileDecision(Contract):
    profile_id: Digest
    profile: DifficultyProfile
    role: Identifier
    basis: DecisionBasis
    action: DecisionAction
    considered_candidate_ids: Annotated[
        tuple[Digest, ...], Field(min_length=1, max_length=128)
    ]
    fallback_candidate_id: Digest
    excluded_below_floor_candidate_ids: Annotated[
        tuple[Digest, ...], Field(max_length=128)
    ] = ()
    quality_eligible_candidate_ids: Annotated[
        tuple[Digest, ...], Field(max_length=128)
    ] = ()
    selection_eligible_candidate_ids: Annotated[
        tuple[Digest, ...], Field(max_length=128)
    ] = ()
    missing_cost_candidate_ids: Annotated[
        tuple[Digest, ...], Field(max_length=128)
    ] = ()
    selected_candidate_id: Digest | None = None
    selected_route: RouteCandidate | None = None
    selected_mean_cost_microusd: (
        Annotated[float, Field(ge=0, le=1_000_000_000_000_000)] | None
    ) = None
    selected_p95_latency_ms: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        if self.profile_id != self.profile.profile_id or self.role != self.profile.role:
            raise ValueError("frozen decision profile identity mismatch")
        collections = (
            self.considered_candidate_ids,
            self.excluded_below_floor_candidate_ids,
            self.quality_eligible_candidate_ids,
            self.selection_eligible_candidate_ids,
            self.missing_cost_candidate_ids,
        )
        if any(tuple(sorted(set(values))) != values for values in collections):
            raise ValueError("frozen decision candidate ids must be unique and sorted")
        considered = set(self.considered_candidate_ids)
        excluded = set(self.excluded_below_floor_candidate_ids)
        eligible = set(self.quality_eligible_candidate_ids)
        selectable = set(self.selection_eligible_candidate_ids)
        missing = set(self.missing_cost_candidate_ids)
        if (
            considered & excluded
            or not eligible <= considered
            or not selectable <= eligible
            or not missing <= eligible
            or selectable & missing
        ):
            raise ValueError("frozen decision candidate sets are inconsistent")
        if self.fallback_candidate_id not in considered:
            raise ValueError("frozen decision fallback is outside the role floor")
        selected_pair = (self.selected_candidate_id is None) == (
            self.selected_route is None
        )
        if not selected_pair:
            raise ValueError("frozen decision selected route identity is incomplete")
        if self.selected_route is not None and (
            self.selected_route.candidate_id != self.selected_candidate_id
            or self.selected_candidate_id not in considered
        ):
            raise ValueError("frozen decision selected route is outside the role floor")

        metrics_present = (
            self.selected_mean_cost_microusd is not None
            and self.selected_p95_latency_ms is not None
        )
        if self.basis == "calibrated_quality_and_cost":
            if (
                self.action != "calibrated_route"
                or not eligible
                or not selectable
                or missing
                or self.selected_candidate_id not in selectable
                or not metrics_present
            ):
                raise ValueError("calibrated frozen decision is inconsistent")
        elif self.basis == "no_quality_eligible_route":
            if eligible or selectable or missing or self.action == "calibrated_route":
                raise ValueError("no-quality frozen decision is inconsistent")
        elif self.basis == "no_cost_eligible_route":
            if (
                not eligible
                or selectable
                or missing
                or self.action == "calibrated_route"
            ):
                raise ValueError("no-cost-eligible frozen decision is inconsistent")
        elif not eligible or not missing or self.action == "calibrated_route":
            raise ValueError("incomplete-cost frozen decision is inconsistent")

        if self.action == "role_fallback" and (
            self.selected_route is None
            or self.selected_candidate_id != self.fallback_candidate_id
        ):
            raise ValueError("fallback decision requires the sealed fallback route")
        if self.action == "fail_closed" and self.selected_route is not None:
            raise ValueError("fail-closed decision cannot select a route")
        if self.action != "calibrated_route" and (
            self.selected_mean_cost_microusd is not None
            or self.selected_p95_latency_ms is not None
        ):
            raise ValueError("uncalibrated decision cannot claim selected metrics")
        return self


class FrozenCandidateRoutingPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["calibration_frozen_candidate_policy"] = (
        "calibration_frozen_candidate_policy"
    )
    source_split: Literal["calibration"] = "calibration"
    holdout_status: Literal["not_evaluated"] = "not_evaluated"
    promotion_ready: Literal[False] = False
    activation_authorized: Literal[False] = False
    selection_objective: Literal["min_mean_cost_then_p95_latency_then_candidate_id"] = (
        "min_mean_cost_then_p95_latency_then_candidate_id"
    )
    uncalibrated_action: Literal["role_fallback", "fail_closed"]
    sealed_study_sha256: Digest
    protocol_sha256: Digest
    feature_manifest_sha256: Digest
    dataset_sha256: Digest
    plan_sha256: Digest
    calibration_report_sha256: Digest
    decisions: Annotated[
        tuple[FrozenProfileDecision, ...], Field(min_length=1, max_length=5000)
    ]

    @model_validator(mode="after")
    def canonical_and_consistent_decisions(self) -> Self:
        profile_ids = tuple(item.profile_id for item in self.decisions)
        if tuple(sorted(set(profile_ids))) != profile_ids:
            raise ValueError("frozen policy profiles must be unique and sorted")
        expected_action = (
            "role_fallback"
            if self.uncalibrated_action == "role_fallback"
            else "fail_closed"
        )
        if any(
            item.basis != "calibrated_quality_and_cost"
            and item.action != expected_action
            for item in self.decisions
        ):
            raise ValueError("frozen policy uncalibrated action differs from protocol")
        return self

    @property
    def candidate_policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _uncalibrated_decision(
    profile_score: ProfileCalibrationScore,
    constraint: RoleRouteConstraint,
    routes: dict[str, RouteCandidate],
    excluded: tuple[str, ...],
    eligible: tuple[str, ...],
    selectable: tuple[str, ...],
    missing: tuple[str, ...],
    action: Literal["role_fallback", "fail_closed"],
) -> FrozenProfileDecision:
    selected_id = (
        constraint.fallback_candidate_id if action == "role_fallback" else None
    )
    return FrozenProfileDecision(
        profile_id=profile_score.profile_id,
        profile=profile_score.profile,
        role=profile_score.profile.role,
        basis=(
            "incomplete_cost_evidence"
            if missing
            else "no_quality_eligible_route"
            if not eligible
            else "no_cost_eligible_route"
        ),
        action=action,
        considered_candidate_ids=constraint.permitted_candidate_ids,
        fallback_candidate_id=constraint.fallback_candidate_id,
        excluded_below_floor_candidate_ids=excluded,
        quality_eligible_candidate_ids=eligible,
        selection_eligible_candidate_ids=selectable,
        missing_cost_candidate_ids=missing,
        selected_candidate_id=selected_id,
        selected_route=routes[selected_id] if selected_id is not None else None,
    )


def _freeze_profile(
    profile_score: ProfileCalibrationScore,
    constraint: RoleRouteConstraint,
    routes: dict[str, RouteCandidate],
    uncalibrated_action: Literal["role_fallback", "fail_closed"],
) -> FrozenProfileDecision:
    permitted = set(constraint.permitted_candidate_ids)
    scores = {score.candidate_id: score for score in profile_score.scores}
    excluded = tuple(sorted(set(scores) - permitted))
    quality_eligible = tuple(
        sorted(
            candidate_id
            for candidate_id in permitted
            if scores[candidate_id].statistical_assessment.sufficient_groups
            and scores[candidate_id].passes_detection
            and scores[candidate_id].passes_false_positives
            and scores[candidate_id].passes_completion
            and scores[candidate_id].passes_latency
        )
    )
    missing = tuple(
        candidate_id
        for candidate_id in quality_eligible
        if scores[candidate_id].cost_coverage != 1.0
        or scores[candidate_id].mean_cost_microusd is None
    )
    selectable = tuple(
        candidate_id
        for candidate_id in quality_eligible
        if candidate_id not in missing and scores[candidate_id].passes_cost
    )
    if not selectable or missing:
        return _uncalibrated_decision(
            profile_score,
            constraint,
            routes,
            excluded,
            quality_eligible,
            selectable,
            missing,
            uncalibrated_action,
        )

    selected = min(
        (scores[candidate_id] for candidate_id in selectable),
        key=lambda score: (
            score.mean_cost_microusd,
            score.p95_latency_ms,
            score.candidate_id,
        ),
    )
    assert selected.mean_cost_microusd is not None
    return FrozenProfileDecision(
        profile_id=profile_score.profile_id,
        profile=profile_score.profile,
        role=profile_score.profile.role,
        basis="calibrated_quality_and_cost",
        action="calibrated_route",
        considered_candidate_ids=constraint.permitted_candidate_ids,
        fallback_candidate_id=constraint.fallback_candidate_id,
        excluded_below_floor_candidate_ids=excluded,
        quality_eligible_candidate_ids=quality_eligible,
        selection_eligible_candidate_ids=selectable,
        selected_candidate_id=selected.candidate_id,
        selected_route=selected.route,
        selected_mean_cost_microusd=selected.mean_cost_microusd,
        selected_p95_latency_ms=selected.p95_latency_ms,
    )


def freeze_candidate_routing_policy(
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
    calibration_report: RoutingCalibrationReport,
) -> FrozenCandidateRoutingPolicy:
    """Reverify calibration evidence and freeze the preregistered rule exactly."""
    verify_routing_calibration_report(
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
        calibration_report,
    )
    protocol = sealed_study.protocol
    constraints = {item.role: item for item in protocol.role_constraints}
    routes = {route.candidate_id: route for route in plan.routes}
    decisions = tuple(
        _freeze_profile(
            profile_score,
            constraints[profile_score.profile.role],
            routes,
            protocol.uncalibrated_action,
        )
        for profile_score in calibration_report.profiles
    )
    return FrozenCandidateRoutingPolicy(
        uncalibrated_action=protocol.uncalibrated_action,
        sealed_study_sha256=sealed_study.sealed_study_sha256,
        protocol_sha256=protocol.protocol_sha256,
        feature_manifest_sha256=manifest.manifest_sha256,
        dataset_sha256=dataset.dataset_sha256,
        plan_sha256=plan.plan_sha256,
        calibration_report_sha256=calibration_report.calibration_report_sha256,
        decisions=decisions,
    )


def verify_frozen_candidate_routing_policy(
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
    calibration_report: RoutingCalibrationReport,
    artifact: FrozenCandidateRoutingPolicy,
) -> None:
    """Recompute the candidate policy from every independent source."""
    rebuilt = freeze_candidate_routing_policy(
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
        calibration_report,
    )
    if rebuilt != artifact:
        raise ValueError("frozen candidate routing policy provenance mismatch")
