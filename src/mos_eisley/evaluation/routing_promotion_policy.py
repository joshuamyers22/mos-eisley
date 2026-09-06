"""Pre-holdout acceptance thresholds for routing-policy promotion."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.evaluation.routing_policy import FrozenCandidateRoutingPolicy
from mos_eisley.evaluation.routing_protocol import SealedRoutingStudy


class RoutingPromotionPolicy(Contract):
    """Thresholds that must be fixed and pinned before holdout is consumed."""

    schema_version: Literal[1] = 1
    mode: Literal["pre_holdout_routing_promotion_policy"] = (
        "pre_holdout_routing_promotion_policy"
    )
    policy_id: Identifier
    activation_authorized: Literal[False] = False
    population_unit: Literal["sealed_profiles_equal_weight"] = (
        "sealed_profiles_equal_weight"
    )
    candidate_policy_sha256: Digest
    sealed_study_sha256: Digest
    min_calibrated_policy_coverage: Annotated[float, Field(ge=0, le=1)]
    min_selected_adequacy_rate: Annotated[float, Field(ge=0, le=1)]
    max_under_routing_rate: Annotated[float, Field(ge=0, le=1)]
    max_fail_closed_rate: Annotated[float, Field(ge=0, le=1)]
    max_missed_adequate_alternative_rate: Annotated[float, Field(ge=0, le=1)]
    min_regret_observation_rate: Annotated[float, Field(ge=0, le=1)]
    max_mean_cost_regret_microusd: Annotated[
        float, Field(ge=0, le=1_000_000_000_000_000)
    ]
    max_mean_latency_regret_ms: Annotated[float, Field(ge=0)]

    @property
    def promotion_policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


def verify_routing_promotion_policy(
    policy: RoutingPromotionPolicy,
    candidate: FrozenCandidateRoutingPolicy,
    sealed_study: SealedRoutingStudy,
) -> None:
    if (
        policy.candidate_policy_sha256 != candidate.candidate_policy_sha256
        or policy.sealed_study_sha256 != sealed_study.sealed_study_sha256
        or candidate.sealed_study_sha256 != sealed_study.sealed_study_sha256
    ):
        raise ValueError("routing promotion policy provenance mismatch")
