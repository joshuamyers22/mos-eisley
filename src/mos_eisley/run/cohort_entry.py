"""Read-only synthetic G6-06 R2 bounded-live entry packet validation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.exact_route import ExactRouteSelection
from mos_eisley.run.routing_decision_readiness import (
    G605DecisionReadinessPacket,
    validate_g605_decision_readiness,
)
from mos_eisley.run.routing_host_drills import HostDrillEvidenceIndex, HostDrillProtocol
from mos_eisley.run.routing_owner_decision import (
    FrozenG605OwnerDecisionAnchor,
    G605OwnerDecisionTrust,
    SignedG605OwnerDecision,
    validate_offline_g605_owner_decision,
)
from mos_eisley.run.routing_preflight import RoutingRuntimePreflight
from mos_eisley.run.routing_qualification import (
    OfflineQualificationEvidence,
    OfflineQualificationPacket,
    OfflineQualificationReviewTrust,
    SignedOfflineQualificationReview,
)
from mos_eisley.run.routing_source_handoff import G605SourceEvidenceHandoff
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
    TaskSessionBinding,
    verify_synthetic_cohort_release,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("R2 entry time must use explicit UTC")
    return value


def task_enrollment_sha256(tasks: tuple[TaskSessionBinding, ...]) -> str:
    """Bind the exact ordered cohort task/session roster as content-free metadata."""
    encoded = json.dumps(
        [item.model_dump(mode="json") for item in tasks],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return digest(b"g605-task-enrollment-v1\0" + encoded)


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
    signed_owner_decision_checked: bool = False
    readiness_checked: bool = False
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


def validate_joined_offline_r2_entry(
    packet: OfflineR2EntryPacket,
    *,
    anchor: FrozenR2EntryAnchor,
    owner_decision: SignedG605OwnerDecision | None,
    owner_trust: G605OwnerDecisionTrust,
    owner_anchor: FrozenG605OwnerDecisionAnchor,
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
    """Join the synthetic R2 entry screen to a signed G6-05 owner record."""
    base = validate_offline_r2_entry(
        packet,
        anchor=anchor,
        signed_release=signed_release,
        selection=selection,
        preflight=preflight,
        admission=admission,
        store=store,
        audit=audit,
        recovery_anchor=recovery_anchor,
        route_probe=route_probe,
        monitor=monitor,
        alerts=alerts,
        now=now,
    )
    reasons = set(base.reasons)
    if owner_decision is None:
        reasons.add("g6_05_owner_decision_missing")
        return OfflineR2EntryResult(
            status="blocked",
            reasons=tuple(sorted(reasons)),
            assignment_count=base.assignment_count,
            claim_count=base.claim_count,
            remaining_cohort_microusd=base.remaining_cohort_microusd,
        )
    owner_result = validate_offline_g605_owner_decision(
        signed=owner_decision,
        trust=owner_trust,
        anchor=owner_anchor,
        now=now,
    )
    if not owner_result.go_reference_reviewable:
        reasons.add("g6_05_owner_decision_invalid")
    decision = owner_decision.decision
    go = packet.g6_05
    if (
        owner_decision.decision_sha256 != anchor.g6_05_go_sha256
        or go.decision_sha256 != owner_decision.decision_sha256
        or go.packet_sha256 != owner_anchor.qualification_packet_sha256
        or anchor.g6_05_packet_sha256 != owner_anchor.qualification_packet_sha256
        or go.status != decision.status
        or go.owner_id != decision.owner_id
        or go.cohort_id != decision.cohort_id
        or go.candidate_policy_sha256 != decision.candidate_policy_sha256
        or go.selected_candidate_id != decision.selected_candidate_id
        or go.broker_build_sha256 != decision.broker_build_sha256
        or go.target_host_id != decision.target_host_id
        or go.witness_epoch_id != decision.witness_epoch_id
        or go.issued_at != decision.issued_at
        or go.valid_until > decision.valid_until
        or signed_release.release.g6_05_go_sha256 != owner_decision.decision_sha256
        or signed_release.release.valid_until > decision.valid_until
        or signed_release.release.issued_at < decision.issued_at
    ):
        reasons.add("g6_05_signed_go_binding_mismatch")
    try:
        state = admission.read_current()
    except Exception:
        reasons.add("g6_05_scope_unavailable")
        state = None
    if state is not None:
        cohort = state.cohort
        manifest = None if cohort is None else cohort.manifest
        budget = admission.budget_policy
        if manifest is None:
            reasons.add("g6_05_scope_unavailable")
        elif (
            decision.owner_id != manifest.owner_id
            or decision.cohort_id != manifest.cohort_id
            or decision.candidate_policy_sha256 != manifest.candidate_policy_sha256
            or decision.broker_build_sha256 != manifest.broker_build_sha256
            or decision.target_host_id != manifest.target_host_id
            or decision.witness_epoch_id != manifest.witness_epoch_id
            or decision.selected_candidate_id != selection.candidate_id
            or not set(manifest.stages).issubset(decision.approved_stages)
            or manifest.max_assignments > decision.max_assignments
            or manifest.max_concurrent > decision.max_concurrent
            or budget.task_ceiling_microusd > decision.task_ceiling_microusd
            or budget.session_ceiling_microusd > decision.session_ceiling_microusd
            or budget.cohort_ceiling_microusd > decision.cohort_ceiling_microusd
            or budget.request_maximum_microusd > decision.request_maximum_microusd
        ):
            reasons.add("g6_05_operating_envelope_mismatch")
    return OfflineR2EntryResult(
        status="blocked" if reasons else "reviewable",
        reasons=tuple(sorted(reasons)),
        signed_owner_decision_checked=True,
        assignment_count=base.assignment_count,
        claim_count=base.claim_count,
        remaining_cohort_microusd=base.remaining_cohort_microusd,
    )


def validate_end_to_end_offline_r2_entry(
    packet: OfflineR2EntryPacket,
    *,
    anchor: FrozenR2EntryAnchor,
    owner_decision: SignedG605OwnerDecision | None,
    owner_trust: G605OwnerDecisionTrust,
    owner_anchor: FrozenG605OwnerDecisionAnchor,
    qualification_packet: OfflineQualificationPacket,
    qualification_evidence: OfflineQualificationEvidence,
    drill_protocol: HostDrillProtocol,
    drill_index: HostDrillEvidenceIndex,
    source_handoff: G605SourceEvidenceHandoff,
    readiness: G605DecisionReadinessPacket,
    review_trust: OfflineQualificationReviewTrust,
    reviews: tuple[SignedOfflineQualificationReview, ...],
    expected_inspection_protocol_sha256: Digest,
    expected_reviewer_roster_sha256: Digest,
    expected_review_trust_sha256: Digest,
    expected_technical_review_sha256: Digest,
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
    """Recheck G605-06 and its signed owner decision at the synthetic R2 gate."""
    joined = validate_joined_offline_r2_entry(
        packet,
        anchor=anchor,
        owner_decision=owner_decision,
        owner_trust=owner_trust,
        owner_anchor=owner_anchor,
        signed_release=signed_release,
        selection=selection,
        preflight=preflight,
        admission=admission,
        store=store,
        audit=audit,
        recovery_anchor=recovery_anchor,
        route_probe=route_probe,
        monitor=monitor,
        alerts=alerts,
        now=now,
    )
    readiness_result = validate_g605_decision_readiness(
        readiness=readiness,
        packet=qualification_packet,
        evidence=qualification_evidence,
        drill_protocol=drill_protocol,
        drill_index=drill_index,
        handoff=source_handoff,
        trust=review_trust,
        reviews=reviews,
        expected_inspection_protocol_sha256=expected_inspection_protocol_sha256,
        expected_reviewer_roster_sha256=expected_reviewer_roster_sha256,
        expected_review_trust_sha256=expected_review_trust_sha256,
        expected_technical_review_sha256=expected_technical_review_sha256,
        now=now,
    )
    reasons = set(joined.reasons)
    if not readiness_result.ready_for_owner_decision:
        reasons.add("g6_05_readiness_invalid")
    if (
        qualification_packet.packet_sha256 != owner_anchor.qualification_packet_sha256
        or qualification_evidence.evidence_sha256
        != owner_anchor.qualification_evidence_sha256
        or source_handoff.handoff_sha256 != owner_anchor.source_handoff_sha256
        or readiness.readiness_sha256 != owner_anchor.decision_readiness_sha256
        or expected_technical_review_sha256 != owner_anchor.technical_review_sha256
        or qualification_packet.candidate.g5_claim_sha256
        != owner_anchor.g5_claim_sha256
    ):
        reasons.add("g6_05_readiness_owner_binding_mismatch")
    if owner_decision is not None:
        decision = owner_decision.decision
        scope = qualification_packet.scope
        candidate = qualification_packet.candidate
        selected = {
            route.identity.candidate_id
            for route in candidate.routes
            if route.purpose in ("selected", "both")
        }
        fallbacks = {
            route.identity.candidate_id
            for route in candidate.routes
            if route.purpose in ("fallback", "both")
            and route.identity.candidate_id != decision.selected_candidate_id
        }
        if (
            decision.issued_at < readiness.assembled_at
            or decision.valid_until > readiness.valid_until
            or decision.valid_until > qualification_packet.decision_deadline
            or decision.valid_until > scope.valid_until
        ):
            reasons.add("g6_05_decision_readiness_window_mismatch")
        if (
            decision.owner_id != scope.owner_id
            or decision.cohort_id != scope.cohort_id
            or decision.candidate_policy_sha256 != candidate.candidate_policy_sha256
            or decision.selected_candidate_id not in selected
            or set(decision.fallback_candidate_ids) != fallbacks
            or decision.broker_build_sha256
            != qualification_packet.runtime.broker_build_sha256
            or decision.target_host_id != qualification_packet.runtime.target_host_id
            or decision.witness_epoch_id != qualification_packet.witness.epoch_id
            or not set(decision.approved_task_types).issubset(scope.task_types)
            or not set(decision.approved_stages).issubset(scope.stages)
            or decision.max_assignments > scope.max_tasks
            or decision.task_ceiling_microusd > scope.task_ceiling_microusd
            or decision.session_ceiling_microusd > scope.session_ceiling_microusd
            or decision.cohort_ceiling_microusd > scope.cohort_ceiling_microusd
            or decision.request_maximum_microusd > scope.request_maximum_microusd
            or decision.max_stop_latency_ms
            > qualification_packet.verification.max_stop_latency_ms
        ):
            reasons.add("g6_05_qualified_scope_mismatch")
    try:
        state = admission.read_current()
    except Exception:
        state = None
    cohort = None if state is None else state.cohort
    if cohort is None:
        reasons.add("g6_05_qualified_cohort_unavailable")
    else:
        manifest = cohort.manifest
        if (
            qualification_packet.scope.task_enrollment_sha256
            != task_enrollment_sha256(manifest.tasks)
            or qualification_packet.witness.enrollment_sha256
            != manifest.witness_enrollment_sha256
            or qualification_packet.witness.budget_policy_sha256
            != manifest.budget_policy_sha256
            or qualification_packet.authority.promotion_receipt_sha256
            != manifest.promotion_receipt_sha256
            or qualification_packet.authority.preflight_sha256
            != preflight.preflight_sha256
            or not set(manifest.stages).issubset(qualification_packet.scope.stages)
            or manifest.max_assignments > qualification_packet.scope.max_tasks
        ):
            reasons.add("g6_05_qualified_cohort_mismatch")
    return OfflineR2EntryResult(
        status="blocked" if reasons else "reviewable",
        reasons=tuple(sorted(reasons)),
        signed_owner_decision_checked=joined.signed_owner_decision_checked,
        readiness_checked=True,
        assignment_count=joined.assignment_count,
        claim_count=joined.claim_count,
        remaining_cohort_microusd=joined.remaining_cohort_microusd,
    )
