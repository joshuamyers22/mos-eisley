"""Read-only synthetic G6-06 R2 bounded-live entry packet validation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.exact_route import ExactRouteSelection
from mos_eisley.run.routing_preflight import RoutingRuntimePreflight
from mos_eisley.run.routing_transaction import (
    FrozenCohortRecoveryAnchor,
    OfflineTransactionStore,
    SyntheticCohortAuditSink,
    SyntheticExactRouteProbe,
    SyntheticRequiredAlertChannel,
    SyntheticRoutingMonitor,
    inspect_offline_cohort_audit,
    inspect_offline_cohort_recovery,
)
from mos_eisley.run.witnessed_admission import (
    SignedCohortRelease,
    SyntheticWitnessedAdmission,
    verify_synthetic_cohort_release,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("R2 entry time must use explicit UTC")
    return value


class FrozenR2EntryAnchor(Contract):
    """Expected digests supplied outside the candidate entry packet."""

    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    g6_05_go_sha256: Digest
    g6_05_packet_sha256: Digest
    r0_review_sha256: Digest
    r1_review_sha256: Digest
    oncall_evidence_sha256: Digest
    full_request_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    max_route_age_seconds: Annotated[int, Field(gt=0, le=604_800)]
    valid_until: datetime

    @field_validator("valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class R2GoReference(Contract):
    decision_sha256: Digest
    packet_sha256: Digest
    status: Literal["go", "no_go", "unavailable"]
    owner_id: Identifier
    cohort_id: Identifier
    candidate_policy_sha256: Digest
    selected_candidate_id: Digest
    broker_build_sha256: Digest
    target_host_id: Identifier
    witness_epoch_id: Digest
    issued_at: datetime
    valid_until: datetime

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def ordered_time(self) -> Self:
        if self.valid_until <= self.issued_at:
            raise ValueError("R2 go reference window is invalid")
        return self


class R2ReviewReference(Contract):
    phase: Literal["R0", "R1"]
    status: Literal["accepted", "rejected", "unavailable"]
    evidence_sha256: Digest
    manifest_sha256: Digest
    broker_build_sha256: Digest
    reviewer_id: Identifier
    reviewed_at: datetime
    valid_until: datetime

    @field_validator("reviewed_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def ordered_time(self) -> Self:
        if self.valid_until <= self.reviewed_at:
            raise ValueError("R2 review window is invalid")
        return self


class OfflineR2EntryPacket(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    signed_release_sha256: Digest
    route_observation_sha256: Digest
    g6_05: R2GoReference
    r0: R2ReviewReference
    r1: R2ReviewReference
    oncall_ready: bool
    oncall_evidence_sha256: Digest
    proposed_at: datetime

    @field_validator("proposed_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def ordered_reviews(self) -> Self:
        if self.r0.phase != "R0" or self.r1.phase != "R1":
            raise ValueError("R2 packet review phases are invalid")
        return self


class OfflineR2EntryResult(Contract):
    status: Literal["blocked", "reviewable"]
    reasons: tuple[str, ...]
    assignment_count: Annotated[int, Field(ge=0)]
    claim_count: Annotated[int, Field(ge=0)]
    remaining_cohort_microusd: Annotated[int, Field(ge=0)]
    owner_release_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False


def validate_offline_r2_entry(
    packet: OfflineR2EntryPacket,
    *,
    anchor: FrozenR2EntryAnchor,
    signed_release: SignedCohortRelease,
    selection: ExactRouteSelection,
    preflight: RoutingRuntimePreflight,
    admission: SyntheticWitnessedAdmission,
    store: OfflineTransactionStore,
    audit: SyntheticCohortAuditSink,
    recovery_anchor: FrozenCohortRecoveryAnchor,
    route_probe: SyntheticExactRouteProbe,
    monitor: SyntheticRoutingMonitor,
    alerts: SyntheticRequiredAlertChannel,
    now: datetime,
) -> OfflineR2EntryResult:
    """Inspect a proposed transition without issuing it or a broker grant."""
    _utc(now)
    reasons: set[str] = set()
    assignments = 0
    claims = 0
    remaining = 0
    if packet.proposed_at != now or now >= anchor.valid_until:
        reasons.add("entry_time_invalid")
    if packet.manifest_sha256 != anchor.manifest_sha256:
        reasons.add("manifest_binding_mismatch")
    if packet.signed_release_sha256 != digest(canonical_bytes(signed_release)):
        reasons.add("release_binding_mismatch")
    if packet.route_observation_sha256 != digest(canonical_bytes(route_probe.current)):
        reasons.add("route_observation_mismatch")
    if (
        packet.oncall_evidence_sha256 != anchor.oncall_evidence_sha256
        or not packet.oncall_ready
    ):
        reasons.add("oncall_not_ready")
    go = packet.g6_05
    if (
        go.status != "go"
        or go.decision_sha256 != anchor.g6_05_go_sha256
        or go.packet_sha256 != anchor.g6_05_packet_sha256
        or not go.issued_at <= now < go.valid_until
        or go.selected_candidate_id != selection.candidate_id
    ):
        reasons.add("g6_05_go_invalid")
    for review, expected in (
        (packet.r0, anchor.r0_review_sha256),
        (packet.r1, anchor.r1_review_sha256),
    ):
        if (
            review.status != "accepted"
            or review.evidence_sha256 != expected
            or not review.reviewed_at <= now < review.valid_until
        ):
            reasons.add(f"{review.phase.lower()}_review_invalid")
    try:
        state = admission.read_current()
    except Exception:
        reasons.add("witness_unavailable")
        state = None
    if state is not None:
        cohort = state.cohort
        assignments = 0 if cohort is None else len(cohort.assignments)
        claims = len(state.attempts)
        budget = admission.budget_policy
        spent = sum(item.charged_microusd for item in state.attempts)
        remaining = max(0, budget.cohort_ceiling_microusd - spent)
        if cohort is None or cohort.signed_release.release.phase != "shadow_only":
            reasons.add("shadow_phase_missing")
        else:
            manifest = cohort.manifest
            prior = cohort.signed_release.release
            proposed = signed_release.release
            try:
                verify_synthetic_cohort_release(signed_release, cohort.trust, manifest)
            except ValueError:
                reasons.add("release_signature_invalid")
            if (
                proposed.phase != "bounded_live"
                or proposed.sequence != prior.sequence + 1
                or proposed.issued_at <= prior.issued_at
                or not proposed.issued_at <= now < proposed.valid_until
                or not manifest.valid_from <= now < manifest.valid_until
                or state.control.signed_control.control.emergency_stop
                or not state.control.signed_control.control.issued_at
                <= now
                < state.control.signed_control.control.valid_until
                or manifest.candidate_policy_sha256
                in state.control.signed_control.control.revoked_candidate_policy_sha256
            ):
                reasons.add("release_transition_invalid")
            if (
                manifest.manifest_sha256 != anchor.manifest_sha256
                or proposed.g6_05_go_sha256 != anchor.g6_05_go_sha256
                or go.owner_id != manifest.owner_id
                or go.cohort_id != manifest.cohort_id
                or go.candidate_policy_sha256 != manifest.candidate_policy_sha256
                or go.broker_build_sha256 != manifest.broker_build_sha256
                or go.target_host_id != manifest.target_host_id
                or go.witness_epoch_id != manifest.witness_epoch_id
                or selection.candidate_policy_sha256 != manifest.candidate_policy_sha256
                or preflight.candidate_policy_sha256 != manifest.candidate_policy_sha256
                or preflight.promotion_receipt_sha256
                != manifest.promotion_receipt_sha256
                or preflight.anchored_control_entry_sha256
                != state.control.anchor_entry_sha256
                or selection.preflight_sha256 != preflight.preflight_sha256
            ):
                reasons.add("source_binding_mismatch")
            for review in (packet.r0, packet.r1):
                if (
                    review.manifest_sha256 != manifest.manifest_sha256
                    or review.broker_build_sha256 != manifest.broker_build_sha256
                    or review.reviewer_id
                    in (cohort.trust.owner_signer_id, cohort.trust.operator_signer_id)
                ):
                    reasons.add(f"{review.phase.lower()}_review_invalid")
        if (
            assignments
            or claims
            or anchor.full_request_microusd != budget.request_maximum_microusd
            or anchor.full_request_microusd
            > min(
                budget.task_ceiling_microusd,
                budget.session_ceiling_microusd,
                remaining,
            )
            or len(state.attempts) >= budget.max_attempts
        ):
            reasons.add("budget_headroom_invalid")
    try:
        preflight.check_current(now)
    except ValueError:
        reasons.add("preflight_expired")
    try:
        route_probe.check(selection, now)
        if (
            now - route_probe.current.observed_at
        ).total_seconds() > anchor.max_route_age_seconds:
            reasons.add("route_observation_stale")
    except ValueError:
        reasons.add("route_unavailable")
    try:
        monitor.check()
        alerts.check()
        audit.check()
        if not inspect_offline_cohort_audit(admission, store, audit).complete:
            reasons.add("audit_join_incomplete")
        recovery = inspect_offline_cohort_recovery(
            admission, store, audit, anchor=recovery_anchor
        )
        if recovery.status != "consistent":
            reasons.add("recovery_mismatch")
        elif state is not None:
            remaining = max(
                0,
                admission.budget_policy.cohort_ceiling_microusd
                - recovery.conservative_exposure_microusd,
            )
            if anchor.full_request_microusd > remaining:
                reasons.add("budget_headroom_invalid")
    except Exception:
        reasons.add("required_path_unavailable")
    return OfflineR2EntryResult(
        status="blocked" if reasons else "reviewable",
        reasons=tuple(sorted(reasons)),
        assignment_count=assignments,
        claim_count=claims,
        remaining_cohort_microusd=remaining,
    )
