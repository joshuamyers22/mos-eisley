"""Pure, non-authorizing resolution of one frozen routing candidate."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.registry import ModelRegistry
from mos_eisley.evaluation.models import RouteCandidate, SweepPlan
from mos_eisley.evaluation.routing_policy import FrozenCandidateRoutingPolicy
from mos_eisley.evaluation.routing_protocol import (
    ObservablePromptFeatures,
    SealedRoutingStudy,
)
from mos_eisley.run.routing_preflight import RoutingRuntimePreflight

DenialReason = Literal[
    "provenance_mismatch",
    "preflight_expired",
    "unknown_role",
    "unseen_profile",
    "policy_fail_closed",
    "policy_inconsistent",
    "candidate_not_eligible",
    "route_identity_mismatch",
    "registry_mismatch",
    "backend_mismatch",
    "client_mismatch",
    "model_missing",
    "effort_unsupported",
    "capability_unqualified",
]
SelectionSource = Literal[
    "calibrated_route", "policy_fallback", "unseen_profile_fallback"
]
RegistryVerification = Literal["fixture", "documented", "live_conformance"]


class ExactRouteRequirements(Contract):
    schema_version: Literal[1] = 1
    role: Identifier
    output_contract: Identifier
    tool_requirements: Annotated[tuple[Identifier, ...], Field(max_length=64)] = ()
    requires_structured_output: bool

    @model_validator(mode="after")
    def canonical_tools(self) -> Self:
        if tuple(sorted(set(self.tool_requirements))) != self.tool_requirements:
            raise ValueError("route tool requirements must be unique and sorted")
        return self

    @property
    def requirements_sha256(self) -> str:
        return digest(canonical_bytes(self))


class ExactRouteSelection(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["exact_route_selection"] = "exact_route_selection"
    candidate_id: Digest
    route: RouteCandidate
    profile_id: Digest
    role: Identifier
    source: SelectionSource
    candidate_policy_sha256: Digest
    preflight_sha256: Digest
    requirements_sha256: Digest
    registry_sha256: Digest
    registry_verification: RegistryVerification

    @model_validator(mode="after")
    def matching_route(self) -> Self:
        if self.candidate_id != self.route.candidate_id:
            raise ValueError("selected route identity mismatch")
        if self.registry_sha256 != self.route.registry_sha256:
            raise ValueError("selected route registry mismatch")
        return self


class ExactRouteDenial(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["exact_route_denial"] = "exact_route_denial"
    reason: DenialReason


def _deny(reason: DenialReason) -> ExactRouteDenial:
    return ExactRouteDenial(reason=reason)


def resolve_exact_route(
    *,
    plan: SweepPlan,
    sealed_study: SealedRoutingStudy,
    policy: FrozenCandidateRoutingPolicy,
    preflight: RoutingRuntimePreflight,
    features: ObservablePromptFeatures,
    requirements: ExactRouteRequirements,
    registry: ModelRegistry,
    installed_backend: str,
    installed_client_version: str,
    now: datetime,
) -> ExactRouteSelection | ExactRouteDenial:
    """Select exact frozen route bytes; the result never authorizes a provider send."""

    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("resolution time must use an explicit UTC offset")

    protocol = sealed_study.protocol
    if (
        plan.plan_sha256 != sealed_study.plan_sha256
        or plan.plan_sha256 != protocol.plan_sha256
        or plan.plan_sha256 != policy.plan_sha256
        or sealed_study.sealed_study_sha256 != policy.sealed_study_sha256
        or protocol.protocol_sha256 != policy.protocol_sha256
        or protocol.feature_manifest_sha256 != sealed_study.feature_manifest_sha256
        or protocol.dataset_sha256 != sealed_study.dataset_sha256
        or sealed_study.feature_manifest_sha256 != policy.feature_manifest_sha256
        or sealed_study.dataset_sha256 != policy.dataset_sha256
        or protocol.uncalibrated_action != policy.uncalibrated_action
        or preflight.candidate_policy_sha256 != policy.candidate_policy_sha256
        or preflight.unavailable_action != policy.uncalibrated_action
    ):
        return _deny("provenance_mismatch")
    try:
        preflight.check_current(now)
    except ValueError:
        return _deny("preflight_expired")

    routes = {route.candidate_id: route for route in plan.routes}
    if len(routes) != len(plan.routes):
        return _deny("route_identity_mismatch")
    constraints = [
        constraint
        for constraint in protocol.role_constraints
        if constraint.role == features.role
    ]
    if len(constraints) != 1:
        return _deny("unknown_role")
    if (
        requirements.role != features.role
        or requirements.output_contract != features.output_contract
        or requirements.tool_requirements != features.tool_requirements
    ):
        return _deny("capability_unqualified")

    constraint = constraints[0]
    profile = protocol.feature_partition.profile(features)
    decisions = [
        decision
        for decision in policy.decisions
        if decision.profile_id == profile.profile_id
    ]
    if len(decisions) > 1:
        return _deny("policy_inconsistent")
    frozen_route: RouteCandidate | None = None
    if decisions:
        decision = decisions[0]
        frozen_route = decision.selected_route
        if (
            decision.profile != profile
            or decision.role != constraint.role
            or decision.fallback_candidate_id != constraint.fallback_candidate_id
            or decision.considered_candidate_ids != constraint.permitted_candidate_ids
        ):
            return _deny("policy_inconsistent")
        if decision.action == "fail_closed":
            return _deny("policy_fail_closed")
        candidate_id = decision.selected_candidate_id
        if candidate_id is None:
            return _deny("policy_inconsistent")
        if decision.action == "role_fallback":
            if (
                policy.uncalibrated_action != "role_fallback"
                or candidate_id != constraint.fallback_candidate_id
            ):
                return _deny("policy_inconsistent")
            source: SelectionSource = "policy_fallback"
        elif decision.action == "calibrated_route":
            if candidate_id not in decision.selection_eligible_candidate_ids:
                return _deny("policy_inconsistent")
            source = "calibrated_route"
        else:
            return _deny("policy_inconsistent")
    else:
        if policy.uncalibrated_action != "role_fallback":
            return _deny("unseen_profile")
        candidate_id = constraint.fallback_candidate_id
        source = "unseen_profile_fallback"

    if (
        candidate_id not in constraint.permitted_candidate_ids
        or candidate_id not in preflight.eligible_candidate_ids
    ):
        return _deny("candidate_not_eligible")
    route = routes.get(candidate_id)
    if route is None or route.candidate_id != candidate_id:
        return _deny("route_identity_mismatch")
    if decisions and frozen_route != route:
        return _deny("route_identity_mismatch")

    registry_sha256 = digest(canonical_bytes(registry))
    if registry_sha256 != route.registry_sha256:
        return _deny("registry_mismatch")
    if installed_backend != route.backend:
        return _deny("backend_mismatch")
    if installed_client_version != route.client_version:
        return _deny("client_mismatch")
    specs = [
        spec
        for spec in registry.models
        if spec.provider == route.provider and spec.id == route.model
    ]
    if len(specs) != 1:
        return _deny("model_missing")
    spec = specs[0]
    if route.effort not in spec.efforts:
        return _deny("effort_unsupported")
    if (requirements.tool_requirements and not spec.tool_calling) or (
        requirements.requires_structured_output and not spec.structured_output
    ):
        return _deny("capability_unqualified")

    return ExactRouteSelection(
        candidate_id=candidate_id,
        route=route,
        profile_id=profile.profile_id,
        role=features.role,
        source=source,
        candidate_policy_sha256=policy.candidate_policy_sha256,
        preflight_sha256=preflight.preflight_sha256,
        requirements_sha256=requirements.requirements_sha256,
        registry_sha256=registry_sha256,
        registry_verification=spec.verification,
    )
