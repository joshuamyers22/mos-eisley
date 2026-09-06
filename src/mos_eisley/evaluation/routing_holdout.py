"""One-time, non-activating holdout evaluation of a frozen routing policy."""

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
from mos_eisley.evaluation.routing_calibration import RoutingCalibrationReport
from mos_eisley.evaluation.routing_policy import (
    FrozenCandidateRoutingPolicy,
    FrozenProfileDecision,
    verify_frozen_candidate_routing_policy,
)
from mos_eisley.evaluation.routing_protocol import (
    DifficultyProfile,
    PromptFeatureManifest,
    SealedRoutingStudy,
)
from mos_eisley.evaluation.scoring import (
    RouteScore,
    score_route_subset,
    validate_observation_matrix,
)
from mos_eisley.evaluation.statistics import MAX_CONFIDENCE_FAMILY


class HoldoutUseClaim(Contract):
    """Deterministic payload written exclusively before holdout scoring starts."""

    schema_version: Literal[1] = 1
    mode: Literal["frozen_policy_holdout_use_claim"] = "frozen_policy_holdout_use_claim"
    consumed: Literal[True] = True
    activation_authorized: Literal[False] = False
    candidate_policy_sha256: Digest
    sealed_study_sha256: Digest
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


class HoldoutProfileEvaluation(Contract):
    profile_id: Digest
    frozen_decision: FrozenProfileDecision
    comparison_strata: Annotated[int, Field(ge=1, le=5000)]
    statistical_family: Literal["all_profiles_routes_metrics_both_splits"] = (
        "all_profiles_routes_metrics_both_splits"
    )
    family_size: Annotated[int, Field(ge=6, le=MAX_CONFIDENCE_FAMILY)]
    scores: Annotated[tuple[RouteScore, ...], Field(min_length=1, max_length=128)]
    adequate_candidate_ids: Annotated[tuple[Digest, ...], Field(max_length=128)] = ()
    missing_cost_adequate_candidate_ids: Annotated[
        tuple[Digest, ...], Field(max_length=128)
    ] = ()
    cheapest_adequate_candidate_id: Digest | None = None
    selected_adequate: bool
    under_routed: bool
    missed_adequate_alternative: bool
    cost_regret_microusd: (
        Annotated[float, Field(ge=0, le=1_000_000_000_000_000)] | None
    ) = None
    latency_regret_ms: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        if self.profile_id != self.frozen_decision.profile_id:
            raise ValueError("holdout profile identity mismatch")
        candidate_ids = tuple(score.candidate_id for score in self.scores)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("holdout profile routes must be unique")
        expected_family_size = len(self.scores) * self.comparison_strata * 3 * 2
        if self.family_size != expected_family_size or any(
            score.statistical_assessment.family_size != self.family_size
            for score in self.scores
        ):
            raise ValueError("holdout profile confidence family mismatch")
        by_id = {score.candidate_id: score for score in self.scores}
        considered = set(self.frozen_decision.considered_candidate_ids)
        if not considered <= set(candidate_ids):
            raise ValueError("frozen decision references an unscored holdout route")
        expected_adequate = tuple(
            sorted(
                candidate_id
                for candidate_id in considered
                if by_id[candidate_id].eligible
            )
        )
        expected_missing = tuple(
            candidate_id
            for candidate_id in expected_adequate
            if by_id[candidate_id].cost_coverage != 1.0
            or by_id[candidate_id].mean_cost_microusd is None
        )
        adequate = set(expected_adequate)
        missing = set(expected_missing)
        if (
            self.adequate_candidate_ids != expected_adequate
            or self.missing_cost_adequate_candidate_ids != expected_missing
        ):
            raise ValueError("holdout adequate candidate sets are inconsistent")
        selected_candidate_id = self.frozen_decision.selected_candidate_id
        if (
            selected_candidate_id is not None
            and selected_candidate_id not in candidate_ids
        ):
            raise ValueError("selected holdout route was not scored")
        expected_selected_adequate = selected_candidate_id in adequate
        if self.selected_adequate != expected_selected_adequate:
            raise ValueError("selected holdout adequacy is inconsistent")
        expected_under_routed = (
            selected_candidate_id is not None
            and not self.selected_adequate
            and bool(adequate)
        )
        expected_missed = not self.selected_adequate and bool(adequate)
        if (
            self.under_routed != expected_under_routed
            or self.missed_adequate_alternative != expected_missed
        ):
            raise ValueError("holdout missed-alternative status is inconsistent")
        if missing:
            if (
                self.cheapest_adequate_candidate_id is not None
                or self.cost_regret_microusd is not None
                or self.latency_regret_ms is not None
            ):
                raise ValueError("incomplete holdout cost evidence cannot claim regret")
        elif adequate:
            cheapest_score = min(
                (by_id[candidate_id] for candidate_id in adequate),
                key=lambda score: (
                    score.mean_cost_microusd,
                    score.p95_latency_ms,
                    score.candidate_id,
                ),
            )
            if self.cheapest_adequate_candidate_id != cheapest_score.candidate_id:
                raise ValueError("cheapest holdout route is inconsistent")
            expected_cost_regret: float | None = None
            expected_latency_regret: int | None = None
            if expected_selected_adequate:
                selected_score = by_id[selected_candidate_id]
                assert selected_score.mean_cost_microusd is not None
                assert cheapest_score.mean_cost_microusd is not None
                expected_cost_regret = max(
                    0.0,
                    selected_score.mean_cost_microusd
                    - cheapest_score.mean_cost_microusd,
                )
                expected_latency_regret = max(
                    0, selected_score.p95_latency_ms - cheapest_score.p95_latency_ms
                )
            if (
                self.cost_regret_microusd != expected_cost_regret
                or self.latency_regret_ms != expected_latency_regret
            ):
                raise ValueError("holdout regret is inconsistent")
        elif any(
            value is not None
            for value in (
                self.cheapest_adequate_candidate_id,
                self.cost_regret_microusd,
                self.latency_regret_ms,
            )
        ):
            raise ValueError("empty adequate set cannot claim cheapest route or regret")
        return self


class HoldoutRoutingSummary(Contract):
    profiles: Annotated[int, Field(ge=1, le=5000)]
    calibrated_route_profiles: Annotated[int, Field(ge=0, le=5000)]
    fallback_route_profiles: Annotated[int, Field(ge=0, le=5000)]
    fail_closed_profiles: Annotated[int, Field(ge=0, le=5000)]
    served_profiles: Annotated[int, Field(ge=0, le=5000)]
    selected_adequate_profiles: Annotated[int, Field(ge=0, le=5000)]
    under_routed_profiles: Annotated[int, Field(ge=0, le=5000)]
    unserved_with_adequate_alternative_profiles: Annotated[int, Field(ge=0, le=5000)]
    regret_observed_profiles: Annotated[int, Field(ge=0, le=5000)]
    calibrated_policy_coverage: Annotated[float, Field(ge=0, le=1)]
    selected_adequacy_rate: Annotated[float, Field(ge=0, le=1)]
    under_routing_rate: Annotated[float, Field(ge=0, le=1)]
    mean_cost_regret_microusd: (
        Annotated[float, Field(ge=0, le=1_000_000_000_000_000)] | None
    ) = None
    max_cost_regret_microusd: (
        Annotated[float, Field(ge=0, le=1_000_000_000_000_000)] | None
    ) = None
    mean_latency_regret_ms: Annotated[float, Field(ge=0)] | None = None
    max_latency_regret_ms: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def counts_are_consistent(self) -> Self:
        if (
            self.calibrated_route_profiles
            + self.fallback_route_profiles
            + self.fail_closed_profiles
            != self.profiles
            or self.served_profiles
            != self.calibrated_route_profiles + self.fallback_route_profiles
        ):
            raise ValueError("holdout policy-action counts are inconsistent")
        if any(
            value > self.profiles
            for value in (
                self.selected_adequate_profiles,
                self.under_routed_profiles,
                self.unserved_with_adequate_alternative_profiles,
                self.regret_observed_profiles,
            )
        ):
            raise ValueError("holdout outcome count exceeds profile count")
        if (
            self.calibrated_policy_coverage
            != self.calibrated_route_profiles / self.profiles
            or self.selected_adequacy_rate
            != self.selected_adequate_profiles / self.profiles
            or self.under_routing_rate != self.under_routed_profiles / self.profiles
        ):
            raise ValueError("holdout summary rates do not match counts")
        regret_metric_presence = tuple(
            value is not None
            for value in (
                self.mean_cost_regret_microusd,
                self.max_cost_regret_microusd,
                self.mean_latency_regret_ms,
                self.max_latency_regret_ms,
            )
        )
        if len(set(regret_metric_presence)) != 1 or regret_metric_presence[0] != (
            self.regret_observed_profiles > 0
        ):
            raise ValueError("holdout regret coverage and metrics are inconsistent")
        return self


class FrozenPolicyHoldoutReport(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["frozen_policy_holdout_evaluation"] = (
        "frozen_policy_holdout_evaluation"
    )
    split: Literal["holdout"] = "holdout"
    holdout_status: Literal["evaluated_once_candidate_only"] = (
        "evaluated_once_candidate_only"
    )
    promotion_ready: Literal[False] = False
    activation_authorized: Literal[False] = False
    candidate_policy_sha256: Digest
    holdout_use_claim_sha256: Digest
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
        tuple[HoldoutProfileEvaluation, ...], Field(min_length=1, max_length=5000)
    ]
    summary: HoldoutRoutingSummary

    @model_validator(mode="after")
    def canonical_profiles(self) -> Self:
        profile_ids = tuple(item.profile_id for item in self.profiles)
        if tuple(sorted(set(profile_ids))) != profile_ids:
            raise ValueError("holdout profiles must be unique and sorted")
        if any(item.comparison_strata != len(self.profiles) for item in self.profiles):
            raise ValueError("holdout comparison strata must cover all profiles")
        if self.summary.profiles != len(self.profiles):
            raise ValueError("holdout summary profile count mismatch")
        if self.summary != _summary(self.profiles):
            raise ValueError("holdout summary does not match profile results")
        return self

    @property
    def holdout_report_sha256(self) -> str:
        return digest(canonical_bytes(self))


def make_holdout_use_claim(
    policy: FrozenCandidateRoutingPolicy,
    batch: ExecutionBatch,
    mapping: BlindingMap,
    raw_results: RawResultSet,
    grading_batch: GradingBatch,
    dual_grading: DualGradingResolution,
    grading_policy: GradingTrustPolicy,
    resolution_policy: ResolutionTrustPolicy,
    observations: DualGradedObservationSet,
) -> HoldoutUseClaim:
    return HoldoutUseClaim(
        candidate_policy_sha256=policy.candidate_policy_sha256,
        sealed_study_sha256=policy.sealed_study_sha256,
        dataset_sha256=policy.dataset_sha256,
        plan_sha256=policy.plan_sha256,
        execution_batch_sha256=batch.batch_sha256,
        mapping_sha256=mapping.mapping_sha256,
        raw_results_sha256=raw_results.raw_results_sha256,
        grading_batch_sha256=grading_batch.grading_batch_sha256,
        grading_trust_policy_sha256=grading_policy.policy_sha256,
        resolution_trust_policy_sha256=resolution_policy.policy_sha256,
        dual_grading_resolution_sha256=dual_grading.dual_grading_resolution_sha256,
        dual_graded_observations_sha256=observations.dual_graded_observations_sha256,
    )


def _evaluate_profile(
    profile: DifficultyProfile,
    scores: tuple[RouteScore, ...],
    policy: FrozenCandidateRoutingPolicy,
    comparison_strata: int,
) -> HoldoutProfileEvaluation:
    decision = next(
        item for item in policy.decisions if item.profile_id == profile.profile_id
    )
    by_id = {score.candidate_id: score for score in scores}
    adequate = tuple(
        sorted(
            candidate_id
            for candidate_id in decision.considered_candidate_ids
            if by_id[candidate_id].eligible
        )
    )
    missing = tuple(
        candidate_id
        for candidate_id in adequate
        if by_id[candidate_id].cost_coverage != 1.0
        or by_id[candidate_id].mean_cost_microusd is None
    )
    cheapest: str | None = None
    regret: float | None = None
    latency_regret: int | None = None
    if adequate and not missing:
        cheapest_score = min(
            (by_id[candidate_id] for candidate_id in adequate),
            key=lambda score: (
                score.mean_cost_microusd,
                score.p95_latency_ms,
                score.candidate_id,
            ),
        )
        cheapest = cheapest_score.candidate_id
        if decision.selected_candidate_id in adequate:
            selected_cost = by_id[decision.selected_candidate_id].mean_cost_microusd
            assert selected_cost is not None
            assert cheapest_score.mean_cost_microusd is not None
            regret = max(0.0, selected_cost - cheapest_score.mean_cost_microusd)
            latency_regret = max(
                0,
                by_id[decision.selected_candidate_id].p95_latency_ms
                - cheapest_score.p95_latency_ms,
            )
    selected_adequate = decision.selected_candidate_id in adequate
    return HoldoutProfileEvaluation(
        profile_id=profile.profile_id,
        frozen_decision=decision,
        comparison_strata=comparison_strata,
        family_size=len(scores) * comparison_strata * 3 * 2,
        scores=scores,
        adequate_candidate_ids=adequate,
        missing_cost_adequate_candidate_ids=missing,
        cheapest_adequate_candidate_id=cheapest,
        selected_adequate=selected_adequate,
        under_routed=(
            decision.selected_candidate_id is not None
            and not selected_adequate
            and bool(adequate)
        ),
        missed_adequate_alternative=not selected_adequate and bool(adequate),
        cost_regret_microusd=regret,
        latency_regret_ms=latency_regret,
    )


def _summary(profiles: tuple[HoldoutProfileEvaluation, ...]) -> HoldoutRoutingSummary:
    regrets = [
        item.cost_regret_microusd
        for item in profiles
        if item.cost_regret_microusd is not None
    ]
    latency_regrets = [
        item.latency_regret_ms
        for item in profiles
        if item.latency_regret_ms is not None
    ]
    profile_count = len(profiles)
    return HoldoutRoutingSummary(
        profiles=profile_count,
        calibrated_route_profiles=sum(
            item.frozen_decision.action == "calibrated_route" for item in profiles
        ),
        fallback_route_profiles=sum(
            item.frozen_decision.action == "role_fallback" for item in profiles
        ),
        fail_closed_profiles=sum(
            item.frozen_decision.action == "fail_closed" for item in profiles
        ),
        served_profiles=sum(
            item.frozen_decision.selected_candidate_id is not None for item in profiles
        ),
        selected_adequate_profiles=sum(item.selected_adequate for item in profiles),
        under_routed_profiles=sum(item.under_routed for item in profiles),
        unserved_with_adequate_alternative_profiles=sum(
            item.frozen_decision.selected_candidate_id is None
            and item.missed_adequate_alternative
            for item in profiles
        ),
        regret_observed_profiles=len(regrets),
        calibrated_policy_coverage=(
            sum(item.frozen_decision.action == "calibrated_route" for item in profiles)
            / profile_count
        ),
        selected_adequacy_rate=(
            sum(item.selected_adequate for item in profiles) / profile_count
        ),
        under_routing_rate=(
            sum(item.under_routed for item in profiles) / profile_count
        ),
        mean_cost_regret_microusd=(sum(regrets) / len(regrets) if regrets else None),
        max_cost_regret_microusd=max(regrets) if regrets else None,
        mean_latency_regret_ms=(
            sum(latency_regrets) / len(latency_regrets) if latency_regrets else None
        ),
        max_latency_regret_ms=max(latency_regrets) if latency_regrets else None,
    )


def evaluate_frozen_routing_policy(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration_batch: ExecutionBatch,
    calibration_mapping: BlindingMap,
    calibration_raw_results: RawResultSet,
    calibration_grading_batch: GradingBatch,
    calibration_dual_grading: DualGradingResolution,
    calibration_grading_policy: GradingTrustPolicy,
    calibration_resolution_policy: ResolutionTrustPolicy,
    calibration_observations: DualGradedObservationSet,
    holdout_batch: ExecutionBatch,
    holdout_mapping: BlindingMap,
    holdout_raw_results: RawResultSet,
    holdout_grading_batch: GradingBatch,
    holdout_dual_grading: DualGradingResolution,
    holdout_grading_policy: GradingTrustPolicy,
    holdout_resolution_policy: ResolutionTrustPolicy,
    holdout_observations: DualGradedObservationSet,
    manifest: PromptFeatureManifest,
    sealed_study: SealedRoutingStudy,
    calibration_report: RoutingCalibrationReport,
    policy: FrozenCandidateRoutingPolicy,
    claim: HoldoutUseClaim,
) -> FrozenPolicyHoldoutReport:
    """Reverify both lineages, then evaluate the frozen decisions on holdout."""
    verify_frozen_candidate_routing_policy(
        dataset,
        plan,
        calibration_batch,
        calibration_mapping,
        calibration_raw_results,
        calibration_grading_batch,
        calibration_dual_grading,
        calibration_grading_policy,
        calibration_resolution_policy,
        calibration_observations,
        manifest,
        sealed_study,
        calibration_report,
        policy,
    )
    expected_claim = make_holdout_use_claim(
        policy,
        holdout_batch,
        holdout_mapping,
        holdout_raw_results,
        holdout_grading_batch,
        holdout_dual_grading,
        holdout_grading_policy,
        holdout_resolution_policy,
        holdout_observations,
    )
    if claim != expected_claim:
        raise ValueError("holdout use claim provenance mismatch")
    verify_dual_graded_observations(
        dataset,
        plan,
        holdout_batch,
        holdout_mapping,
        holdout_raw_results,
        holdout_grading_batch,
        holdout_dual_grading,
        holdout_grading_policy,
        holdout_resolution_policy,
        holdout_observations,
    )
    validate_observation_matrix(
        plan, dataset, holdout_observations.observations, "holdout"
    )

    cases = {case.id: case for case in dataset.cases}
    profiles: dict[str, DifficultyProfile] = {}
    case_ids: dict[str, set[str]] = defaultdict(set)
    for assignment in manifest.assignments:
        profile = sealed_study.protocol.feature_partition.profile(assignment.features)
        profiles[profile.profile_id] = profile
        if cases[assignment.case_id].split == "holdout":
            case_ids[profile.profile_id].add(assignment.case_id)
    if tuple(sorted(profiles)) != sealed_study.profile_ids:
        raise ValueError("sealed routing study profile coverage mismatch")

    comparison_strata = len(profiles)
    evaluated = tuple(
        _evaluate_profile(
            profiles[profile_id],
            tuple(
                score_route_subset(
                    route,
                    plan,
                    dataset,
                    holdout_observations.observations,
                    "holdout",
                    frozenset(case_ids[profile_id]),
                    comparison_strata,
                )
                for route in plan.routes
            ),
            policy,
            comparison_strata,
        )
        for profile_id in sorted(profiles)
    )
    return FrozenPolicyHoldoutReport(
        candidate_policy_sha256=policy.candidate_policy_sha256,
        holdout_use_claim_sha256=claim.claim_sha256,
        sealed_study_sha256=sealed_study.sealed_study_sha256,
        protocol_sha256=sealed_study.protocol_sha256,
        feature_manifest_sha256=manifest.manifest_sha256,
        dataset_sha256=dataset.dataset_sha256,
        plan_sha256=plan.plan_sha256,
        execution_batch_sha256=holdout_batch.batch_sha256,
        mapping_sha256=holdout_mapping.mapping_sha256,
        raw_results_sha256=holdout_raw_results.raw_results_sha256,
        grading_batch_sha256=holdout_grading_batch.grading_batch_sha256,
        grading_trust_policy_sha256=holdout_grading_policy.policy_sha256,
        resolution_trust_policy_sha256=holdout_resolution_policy.policy_sha256,
        dual_grading_resolution_sha256=holdout_dual_grading.dual_grading_resolution_sha256,
        dual_graded_observations_sha256=holdout_observations.dual_graded_observations_sha256,
        gate=plan.gate,
        profiles=evaluated,
        summary=_summary(evaluated),
    )


def verify_frozen_policy_holdout_report(
    dataset: EvaluationDataset,
    plan: SweepPlan,
    calibration_batch: ExecutionBatch,
    calibration_mapping: BlindingMap,
    calibration_raw_results: RawResultSet,
    calibration_grading_batch: GradingBatch,
    calibration_dual_grading: DualGradingResolution,
    calibration_grading_policy: GradingTrustPolicy,
    calibration_resolution_policy: ResolutionTrustPolicy,
    calibration_observations: DualGradedObservationSet,
    holdout_batch: ExecutionBatch,
    holdout_mapping: BlindingMap,
    holdout_raw_results: RawResultSet,
    holdout_grading_batch: GradingBatch,
    holdout_dual_grading: DualGradingResolution,
    holdout_grading_policy: GradingTrustPolicy,
    holdout_resolution_policy: ResolutionTrustPolicy,
    holdout_observations: DualGradedObservationSet,
    manifest: PromptFeatureManifest,
    sealed_study: SealedRoutingStudy,
    calibration_report: RoutingCalibrationReport,
    policy: FrozenCandidateRoutingPolicy,
    claim: HoldoutUseClaim,
    artifact: FrozenPolicyHoldoutReport,
) -> None:
    rebuilt = evaluate_frozen_routing_policy(
        dataset,
        plan,
        calibration_batch,
        calibration_mapping,
        calibration_raw_results,
        calibration_grading_batch,
        calibration_dual_grading,
        calibration_grading_policy,
        calibration_resolution_policy,
        calibration_observations,
        holdout_batch,
        holdout_mapping,
        holdout_raw_results,
        holdout_grading_batch,
        holdout_dual_grading,
        holdout_grading_policy,
        holdout_resolution_policy,
        holdout_observations,
        manifest,
        sealed_study,
        calibration_report,
        policy,
        claim,
    )
    if rebuilt != artifact:
        raise ValueError("frozen policy holdout report provenance mismatch")
