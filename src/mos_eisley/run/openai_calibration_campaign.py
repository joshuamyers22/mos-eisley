"""Commit the unexecuted OpenAI calibration remainder without authorizing it."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.protocol import Effort
from mos_eisley.evaluation.execution import ExecutionBatch
from mos_eisley.evaluation.models import MAX_ASSIGNMENTS
from mos_eisley.run.openai_conformance_conversion import (
    OpenAIConformanceCalibrationSeed,
)

Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]


class OpenAICalibrationProfilePlan(Contract):
    """One exact route's static pricing and token reservation envelope."""

    model: Identifier
    effort: Effort
    pricing_source: Annotated[str, Field(min_length=1, max_length=1000)]
    input_microusd_per_million: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    cache_write_microusd_per_million: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    output_microusd_per_million: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    max_input_tokens: Annotated[int, Field(gt=0, le=200_000)]
    max_output_tokens: Annotated[int, Field(gt=0, le=4096)]
    max_cost_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]

    @model_validator(mode="after")
    def exact_cost_ceiling(self) -> Self:
        calculated = (
            self.max_input_tokens
            * max(
                self.input_microusd_per_million,
                self.cache_write_microusd_per_million,
            )
            + self.max_output_tokens * self.output_microusd_per_million
            + 999_999
        ) // 1_000_000
        if self.max_cost_microusd != calculated:
            raise ValueError("profile maximum cost must equal its token-rate ceiling")
        return self

    @property
    def profile(self) -> str:
        return f"{self.model}/{self.effort}"

    @property
    def profile_plan_sha256(self) -> str:
        return digest(canonical_bytes(self))


class OpenAICalibrationCampaignPolicy(Contract):
    """Reviewed, non-authorizing budget commitment for the frozen remainder."""

    schema_version: Literal[1] = 1
    mode: Literal["openai_calibration_campaign_policy"] = (
        "openai_calibration_campaign_policy"
    )
    policy_id: Identifier
    plan_sha256: Digest
    batch_sha256: Digest
    calibration_seed_sha256: Digest
    pricing_checked_at: datetime
    execution_batch_assignments: Literal[360] = 360
    seeded_assignments: Literal[18] = 18
    pending_assignments: Literal[342] = 342
    assignments_per_profile: Literal[60] = 60
    seeded_assignments_per_profile: Literal[3] = 3
    pending_assignments_per_profile: Literal[57] = 57
    profiles: Annotated[
        tuple[OpenAICalibrationProfilePlan, ...], Field(min_length=6, max_length=6)
    ]
    aggregate_max_cost_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    provider: Literal["openai"] = "openai"
    service_tier: Literal["default"] = "default"
    command: Literal["eval-plan-openai-calibration-campaign"] = (
        "eval-plan-openai-calibration-campaign"
    )
    preserve_frozen_batch_order: Literal[True] = True
    exact_remaining_coverage_required: Literal[True] = True
    fixed_matrix_required: Literal[True] = True
    offline_only: Literal[True] = True
    cached_input_discount_assumed: Literal[False] = False
    cache_write_exposure_included: Literal[True] = True
    batch_api_authorized: Literal[False] = False
    fast_mode_authorized: Literal[False] = False
    tool_access_authorized: Literal[False] = False
    credential_access_authorized: Literal[False] = False
    spend_reservation_authorized: Literal[False] = False
    provider_request_authorized: Literal[False] = False
    retry_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def exact_profile_matrix(self) -> Self:
        if (
            self.pricing_checked_at.tzinfo is None
            or self.pricing_checked_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("pricing check timestamp must use an explicit UTC offset")
        profiles = tuple(item.profile for item in self.profiles)
        if profiles != tuple(sorted(set(profiles))):
            raise ValueError("campaign profiles must be sorted and unique")
        expected = sum(
            item.max_cost_microusd * self.pending_assignments_per_profile
            for item in self.profiles
        )
        if self.aggregate_max_cost_microusd != expected:
            raise ValueError(
                "aggregate ceiling must equal all pending profile ceilings"
            )
        return self

    @property
    def campaign_policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class OpenAICalibrationCampaignAssignment(Contract):
    sequence: Annotated[int, Field(ge=1, le=MAX_ASSIGNMENTS)]
    batch_position: Annotated[int, Field(ge=1, le=MAX_ASSIGNMENTS)]
    sample_id: Digest
    candidate_id: Digest
    evaluation_request_sha256: Digest
    model: Identifier
    effort: Effort
    profile_plan_sha256: Digest
    max_cost_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    execution_authorized: Literal[False] = False

    @property
    def profile(self) -> str:
        return f"{self.model}/{self.effort}"


class OpenAICalibrationCampaignManifest(Contract):
    """Hash-only plan that remains inert until each request is freshly authorized."""

    schema_version: Literal[1] = 1
    mode: Literal["openai_calibration_campaign_manifest"] = (
        "openai_calibration_campaign_manifest"
    )
    campaign_policy_sha256: Digest
    calibration_seed_sha256: Digest
    plan_sha256: Digest
    batch_sha256: Digest
    execution_batch_assignments: Literal[360] = 360
    seeded_assignments: Literal[18] = 18
    planned_assignments: Literal[342] = 342
    assignments: Annotated[
        tuple[OpenAICalibrationCampaignAssignment, ...],
        Field(min_length=342, max_length=342),
    ]
    aggregate_max_cost_microusd: Money
    exact_seed_lineage_verified: Literal[True] = True
    exact_remaining_coverage_verified: Literal[True] = True
    frozen_batch_order_verified: Literal[True] = True
    request_content_embedded: Literal[False] = False
    credential_accessed: Literal[False] = False
    spend_reserved: Literal[False] = False
    provider_request_sent: Literal[False] = False
    execution_authorized: Literal[False] = False
    grading_authorized: Literal[False] = False
    scoring_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    routing_activation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def exact_assignment_matrix(self) -> Self:
        if tuple(item.sequence for item in self.assignments) != tuple(
            range(1, self.planned_assignments + 1)
        ):
            raise ValueError("campaign assignment sequences must be contiguous")
        batch_positions = tuple(item.batch_position for item in self.assignments)
        if batch_positions != tuple(sorted(batch_positions)):
            raise ValueError("campaign assignments must preserve frozen batch order")
        unique_fields = (
            batch_positions,
            tuple(item.sample_id for item in self.assignments),
            tuple(item.evaluation_request_sha256 for item in self.assignments),
        )
        if any(len(values) != len(set(values)) for values in unique_fields):
            raise ValueError("campaign assignment identities must be unique")
        profile_counts = Counter(item.profile for item in self.assignments)
        if len(profile_counts) != 6 or set(profile_counts.values()) != {57}:
            raise ValueError("campaign must contain 57 assignments in each profile")
        if self.aggregate_max_cost_microusd != sum(
            item.max_cost_microusd for item in self.assignments
        ):
            raise ValueError("campaign manifest aggregate ceiling is inconsistent")
        return self

    @property
    def campaign_manifest_sha256(self) -> str:
        return digest(canonical_bytes(self))


def plan_openai_calibration_campaign(
    batch: ExecutionBatch,
    seed: OpenAIConformanceCalibrationSeed,
    policy: OpenAICalibrationCampaignPolicy,
) -> OpenAICalibrationCampaignManifest:
    """Bind the exact unexecuted remainder without granting execution authority."""

    batch = ExecutionBatch.model_validate_json(canonical_bytes(batch))
    seed = OpenAIConformanceCalibrationSeed.model_validate_json(canonical_bytes(seed))
    policy = OpenAICalibrationCampaignPolicy.model_validate_json(
        canonical_bytes(policy)
    )
    if (
        batch.plan_sha256 != policy.plan_sha256
        or batch.batch_sha256 != policy.batch_sha256
        or len(batch.requests) != policy.execution_batch_assignments
    ):
        raise ValueError("execution batch does not match the campaign policy")
    if (
        seed.calibration_seed_sha256 != policy.calibration_seed_sha256
        or seed.plan_sha256 != batch.plan_sha256
        or seed.batch_sha256 != batch.batch_sha256
        or seed.execution_batch_assignments != len(batch.requests)
        or seed.converted_assignments != policy.seeded_assignments
    ):
        raise ValueError("calibration seed does not match the campaign policy")

    requests = {item.sample_id: item for item in batch.requests}
    seed_samples = {item.sample_id for item in seed.results}
    if len(seed_samples) != policy.seeded_assignments or not seed_samples <= set(
        requests
    ):
        raise ValueError("calibration seed does not exactly cover batch requests")
    for result in seed.results:
        request = requests[result.sample_id]
        if (
            result.candidate_id != request.route.candidate_id
            or result.evaluation_request_sha256 != request.request_sha256
            or result.model != request.route.model
            or result.effort != request.route.effort
            or request.route.provider != policy.provider
        ):
            raise ValueError("calibration seed request lineage mismatch")

    profile_plans = {item.profile: item for item in policy.profiles}
    batch_profiles = Counter(
        f"{request.route.model}/{request.route.effort}" for request in batch.requests
    )
    seed_profiles = Counter(f"{item.model}/{item.effort}" for item in seed.results)
    expected_batch = {
        profile: policy.assignments_per_profile for profile in profile_plans
    }
    expected_seed = {
        profile: policy.seeded_assignments_per_profile for profile in profile_plans
    }
    if batch_profiles != expected_batch or seed_profiles != expected_seed:
        raise ValueError("batch or seed does not match the campaign profile matrix")
    if any(request.route.provider != policy.provider for request in batch.requests):
        raise ValueError("campaign contains a non-OpenAI route")

    assignments: list[OpenAICalibrationCampaignAssignment] = []
    for batch_position, request in enumerate(batch.requests, start=1):
        if request.sample_id in seed_samples:
            continue
        profile = f"{request.route.model}/{request.route.effort}"
        plan = profile_plans[profile]
        assignments.append(
            OpenAICalibrationCampaignAssignment(
                sequence=len(assignments) + 1,
                batch_position=batch_position,
                sample_id=request.sample_id,
                candidate_id=request.route.candidate_id,
                evaluation_request_sha256=request.request_sha256,
                model=request.route.model,
                effort=request.route.effort,
                profile_plan_sha256=plan.profile_plan_sha256,
                max_cost_microusd=plan.max_cost_microusd,
            )
        )
    if len(assignments) != policy.pending_assignments:
        raise ValueError("campaign remainder does not match the policy")
    return OpenAICalibrationCampaignManifest(
        campaign_policy_sha256=policy.campaign_policy_sha256,
        calibration_seed_sha256=seed.calibration_seed_sha256,
        plan_sha256=batch.plan_sha256,
        batch_sha256=batch.batch_sha256,
        assignments=tuple(assignments),
        aggregate_max_cost_microusd=policy.aggregate_max_cost_microusd,
    )
