"""Read-only G6-06 R1 shadow decisions for synthetic enrolled cohorts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.registry import ModelRegistry
from mos_eisley.evaluation.models import SweepPlan
from mos_eisley.evaluation.routing_policy import FrozenCandidateRoutingPolicy
from mos_eisley.evaluation.routing_protocol import (
    ObservablePromptFeatures,
    SealedRoutingStudy,
)
from mos_eisley.run.exact_route import (
    ExactRouteDenial,
    ExactRouteRequirements,
    SelectionSource,
    resolve_exact_route,
)
from mos_eisley.run.routing_preflight import RoutingRuntimePreflight
from mos_eisley.run.routing_transaction import (
    SyntheticExactRouteProbe,
    SyntheticRoutingMonitor,
)
from mos_eisley.run.store import private_write
from mos_eisley.run.witnessed_admission import (
    SyntheticWitnessedAdmission,
    TaskSessionBinding,
)

ShadowDenial = Literal[
    "release_inactive",
    "control_blocked",
    "policy_mismatch",
    "monitor_unavailable",
    "resolver_denied",
    "route_unavailable",
]


class OfflineShadowDecision(Contract):
    schema_version: Literal[1] = 1
    owner_id: Identifier
    cohort_id: Identifier
    task_session_sha256: Digest
    manifest_sha256: Digest
    release_sha256: Digest
    candidate_policy_sha256: Digest
    witness_generation: Annotated[int, Field(ge=0)]
    checked_at: datetime
    route_observation_sha256: Digest
    route_observed_at: datetime
    route_valid_until: datetime
    status: Literal["selected", "denied"]
    denial: ShadowDenial | None = None
    selected_candidate_id: Digest | None = None
    selection_source: SelectionSource | None = None
    assignment_authorized: Literal[False] = False
    claim_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False

    @model_validator(mode="after")
    def valid_shape(self) -> Self:
        for value in (self.checked_at, self.route_observed_at, self.route_valid_until):
            if value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ValueError("shadow decision time must use explicit UTC")
        if self.status == "selected" and (
            self.denial is not None
            or self.selected_candidate_id is None
            or self.selection_source is None
        ):
            raise ValueError("selected shadow decision lacks an exact route")
        if self.status == "denied" and self.denial is None:
            raise ValueError("denied shadow decision lacks a reason")
        return self


class OfflineShadowDecisionBatch(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    release_sha256: Digest
    candidate_policy_sha256: Digest
    decisions: Annotated[
        tuple[OfflineShadowDecision, ...], Field(min_length=1, max_length=1000)
    ]
    assignment_authorized: Literal[False] = False
    claim_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False

    @model_validator(mode="after")
    def same_frozen_scope(self) -> Self:
        if any(
            item.manifest_sha256 != self.manifest_sha256
            or item.release_sha256 != self.release_sha256
            or item.candidate_policy_sha256 != self.candidate_policy_sha256
            for item in self.decisions
        ):
            raise ValueError("shadow decision batch mixed cohort releases")
        return self


def write_offline_shadow_batch(path: Path, batch: OfflineShadowDecisionBatch) -> None:
    """Write one new private metadata-only batch; never append task content."""
    private_write(path, (batch.model_dump_json() + "\n").encode())


def evaluate_offline_shadow_route(
    *,
    admission: SyntheticWitnessedAdmission,
    owner_id: str,
    cohort_id: str,
    task_id: str,
    session_id: str,
    stage_id: str,
    plan: SweepPlan,
    sealed_study: SealedRoutingStudy,
    policy: FrozenCandidateRoutingPolicy,
    preflight: RoutingRuntimePreflight,
    features: ObservablePromptFeatures,
    requirements: ExactRouteRequirements,
    registry: ModelRegistry,
    installed_backend: str,
    installed_client_version: str,
    route_probe: SyntheticExactRouteProbe,
    monitor: SyntheticRoutingMonitor,
    now: datetime,
) -> OfflineShadowDecision:
    """Resolve one exact route without an assignment, claim or send path."""
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("shadow decision time must use explicit UTC")
    if (
        type(route_probe) is not SyntheticExactRouteProbe
        or type(monitor) is not SyntheticRoutingMonitor
    ):
        raise ValueError("shadow decision requires inert observation fixtures")
    state = admission.read_current()
    cohort = state.cohort
    if cohort is None or cohort.signed_release.release.phase != "shadow_only":
        raise ValueError("synthetic cohort has no shadow-only release")
    manifest = cohort.manifest
    release = cohort.signed_release.release
    if (
        owner_id != manifest.owner_id
        or cohort_id != manifest.cohort_id
        or TaskSessionBinding(task_id=task_id, session_id=session_id)
        not in manifest.tasks
        or stage_id not in manifest.stages
    ):
        raise ValueError("synthetic shadow task is outside the enrolled scope")
    observation = route_probe.current
    values = dict(
        owner_id=owner_id,
        cohort_id=cohort_id,
        task_session_sha256=digest(
            json.dumps(
                [owner_id, cohort_id, task_id, session_id, stage_id],
                separators=(",", ":"),
            ).encode()
        ),
        manifest_sha256=manifest.manifest_sha256,
        release_sha256=release.release_sha256,
        candidate_policy_sha256=manifest.candidate_policy_sha256,
        witness_generation=state.generation,
        checked_at=now,
        route_observation_sha256=digest(canonical_bytes(observation)),
        route_observed_at=observation.observed_at,
        route_valid_until=observation.valid_until,
    )

    def deny(
        reason: ShadowDenial,
        *,
        candidate: str | None = None,
        source: SelectionSource | None = None,
    ) -> OfflineShadowDecision:
        return OfflineShadowDecision.model_validate(
            {
                **values,
                "status": "denied",
                "denial": reason,
                "selected_candidate_id": candidate,
                "selection_source": source,
            }
        )

    control = state.control.signed_control.control
    if (
        not manifest.valid_from <= now < manifest.valid_until
        or not release.issued_at <= now < release.valid_until
    ):
        return deny("release_inactive")
    if (
        control.emergency_stop
        or not control.issued_at <= now < control.valid_until
        or manifest.candidate_policy_sha256 in control.revoked_candidate_policy_sha256
        or preflight.anchored_control_entry_sha256 != state.control.anchor_entry_sha256
        or preflight.control_anchor_policy_sha256
        != admission.anchor_policy.policy_sha256
    ):
        return deny("control_blocked")
    if (
        policy.candidate_policy_sha256 != manifest.candidate_policy_sha256
        or preflight.candidate_policy_sha256 != manifest.candidate_policy_sha256
        or preflight.promotion_receipt_sha256 != manifest.promotion_receipt_sha256
    ):
        return deny("policy_mismatch")
    try:
        monitor.check()
    except ValueError:
        return deny("monitor_unavailable")
    selected = resolve_exact_route(
        plan=plan,
        sealed_study=sealed_study,
        policy=policy,
        preflight=preflight,
        features=features,
        requirements=requirements,
        registry=registry,
        installed_backend=installed_backend,
        installed_client_version=installed_client_version,
        now=now,
    )
    if isinstance(selected, ExactRouteDenial):
        return deny("resolver_denied")
    try:
        route_probe.check(selected, now)
    except ValueError:
        return deny(
            "route_unavailable",
            candidate=selected.candidate_id,
            source=selected.source,
        )
    return OfflineShadowDecision.model_validate(
        {
            **values,
            "status": "selected",
            "selected_candidate_id": selected.candidate_id,
            "selection_source": selected.source,
        }
    )
