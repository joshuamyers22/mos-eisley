"""Read-only G6-06 R5 synthetic close and follow-up handoff validation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.cohort_closeout import (
    CohortCloseoutPacket,
    FrozenCloseoutProtocol,
    validate_offline_cohort_closeout,
)
from mos_eisley.run.cohort_surveillance import (
    FrozenR4SurveillanceAnchor,
    OfflineR4SurveillancePacket,
    OfflineR4SurveillanceResult,
    inspect_offline_r4_surveillance,
)
from mos_eisley.run.exact_route import ExactRouteSelection
from mos_eisley.run.routing_preflight import RoutingRuntimePreflight
from mos_eisley.run.routing_transaction import (
    FrozenCohortRecoveryAnchor,
    InertRoutingTransport,
    OfflineTransactionStore,
    SyntheticCohortAuditSink,
    SyntheticExactRouteProbe,
    SyntheticRequiredAlertChannel,
    SyntheticRoutingMonitor,
    inspect_offline_cohort_recovery,
)
from mos_eisley.run.witnessed_admission import (
    SyntheticWitnessedAdmission,
    WitnessedState,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("R5 close time must use explicit UTC")
    return value


class FrozenR5CloseAnchor(Contract):
    """External trigger and prior-state references, never inferred from closeout."""

    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    closeout_protocol_sha256: Digest
    preclose_state_sha256: Digest
    closed_release_sha256: Digest
    r4_packet_sha256: Digest
    r4_result_sha256: Digest
    trigger: Literal["r4_hard_stop", "registered_cutoff"]
    triggered_at: datetime
    max_close_latency_seconds: Annotated[int, Field(gt=0, le=86_400)]
    valid_until: datetime

    @field_validator("triggered_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class OfflineR5CloseResult(Contract):
    status: Literal["blocked", "pending_followup", "reviewable"]
    reasons: tuple[str, ...]
    closeout_reasons: tuple[str, ...]
    assignment_count: Annotated[int, Field(ge=0)]
    claim_count: Annotated[int, Field(ge=0)]
    conservative_exposure_microusd: Annotated[int, Field(ge=0)]
    followup_unknown_count: Annotated[int, Field(ge=0)]
    close_authorized: Literal[False] = False
    reentry_authorized: Literal[False] = False
    assessment_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False


class OfflineR4TriggerReproduction(Contract):
    """Read-only pre-close reproduction; a digest needs an external freeze."""

    schema_version: Literal[1] = 1
    status: Literal["blocked", "reproduced"]
    reasons: tuple[str, ...]
    r4_anchor_sha256: Digest
    r4_packet_sha256: Digest
    r4_result_sha256: Digest
    preclose_state_sha256: Digest
    recovery_anchor_sha256: Digest
    reproduced_at: datetime
    close_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False

    @field_validator("reproduced_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        if (
            (self.status == "reproduced") == bool(self.reasons)
            or self.reasons != tuple(sorted(set(self.reasons)))
        ):
            raise ValueError("R4 trigger reproduction status and reasons conflict")
        return self


def reproduce_offline_r4_trigger(
    *,
    protocol: FrozenCloseoutProtocol,
    close_anchor: FrozenR5CloseAnchor,
    r4_anchor: FrozenR4SurveillanceAnchor,
    expected_r4_anchor_sha256: Digest,
    r4_packet: OfflineR4SurveillancePacket,
    r4_result: OfflineR4SurveillanceResult,
    preclose_state: WitnessedState,
    selection: ExactRouteSelection,
    preflight: RoutingRuntimePreflight,
    admission: SyntheticWitnessedAdmission,
    store: OfflineTransactionStore,
    audit: SyntheticCohortAuditSink,
    recovery_anchor: FrozenCohortRecoveryAnchor,
    route_probe: SyntheticExactRouteProbe,
    monitor: SyntheticRoutingMonitor,
    alerts: SyntheticRequiredAlertChannel,
    transport: InertRoutingTransport,
    now: datetime,
) -> OfflineR4TriggerReproduction:
    """Rerun R4 against current synthetic sources before applying close."""
    _utc(now)
    reasons: set[str] = set()
    r4_anchor_sha256 = digest(canonical_bytes(r4_anchor))
    r4_packet_sha256 = digest(canonical_bytes(r4_packet))
    r4_result_sha256 = digest(canonical_bytes(r4_result))
    recovery_anchor_sha256 = digest(canonical_bytes(recovery_anchor))
    if r4_anchor_sha256 != expected_r4_anchor_sha256:
        reasons.add("r4_anchor_mismatch")
    if now >= close_anchor.valid_until:
        reasons.add("trigger_anchor_expired")
    if (
        close_anchor.manifest_sha256 != protocol.manifest_sha256
        or close_anchor.closeout_protocol_sha256 != digest(canonical_bytes(protocol))
        or close_anchor.preclose_state_sha256 != preclose_state.state_sha256
        or close_anchor.r4_packet_sha256 != r4_packet_sha256
        or close_anchor.r4_result_sha256 != r4_result_sha256
        or r4_anchor.manifest_sha256 != close_anchor.manifest_sha256
        or r4_packet.manifest_sha256 != close_anchor.manifest_sha256
        or r4_anchor.release_sha256 != r4_packet.release_sha256
        or close_anchor.triggered_at != r4_packet.observed_at
        or now != r4_packet.observed_at
    ):
        reasons.add("r4_trigger_binding_mismatch")
    if close_anchor.trigger == "r4_hard_stop":
        if r4_result.status != "hard_stop" or not r4_result.stop_required:
            reasons.add("r4_hard_stop_missing")
    elif close_anchor.triggered_at != protocol.cutoff_at:
        reasons.add("cutoff_trigger_mismatch")
    try:
        current = admission.read_current()
        checkpoint = admission.checkpoint.read_current()
        if (
            current != preclose_state
            or checkpoint.state_sha256 != preclose_state.state_sha256
            or checkpoint.epoch_id != preclose_state.epoch_id
            or checkpoint.generation != preclose_state.generation
            or recovery_anchor.checkpoint.state_sha256 != preclose_state.state_sha256
        ):
            reasons.add("preclose_source_changed")
    except Exception:
        reasons.add("preclose_source_unavailable")
    try:
        repeated = inspect_offline_r4_surveillance(
            r4_packet,
            anchor=r4_anchor,
            selection=selection,
            preflight=preflight,
            admission=admission,
            store=store,
            audit=audit,
            recovery_anchor=recovery_anchor,
            route_probe=route_probe,
            monitor=monitor,
            alerts=alerts,
            transport=transport,
            now=now,
        )
        if repeated != r4_result:
            reasons.add("r4_result_not_reproduced")
    except Exception:
        reasons.add("r4_reproduction_unavailable")
    return OfflineR4TriggerReproduction(
        status="blocked" if reasons else "reproduced",
        reasons=tuple(sorted(reasons)),
        r4_anchor_sha256=r4_anchor_sha256,
        r4_packet_sha256=r4_packet_sha256,
        r4_result_sha256=r4_result_sha256,
        preclose_state_sha256=preclose_state.state_sha256,
        recovery_anchor_sha256=recovery_anchor_sha256,
        reproduced_at=now,
    )


def validate_offline_r5_close_handoff(
    packet: CohortCloseoutPacket,
    *,
    protocol: FrozenCloseoutProtocol,
    anchor: FrozenR5CloseAnchor,
    r4_packet: OfflineR4SurveillancePacket,
    r4_result: OfflineR4SurveillanceResult,
    preclose_state: WitnessedState,
    admission: SyntheticWitnessedAdmission,
    store: OfflineTransactionStore,
    audit: SyntheticCohortAuditSink,
    recovery_anchor: FrozenCohortRecoveryAnchor,
    now: datetime,
) -> OfflineR5CloseResult:
    """Join frozen trigger, signed close and follow-up without outcome-store reads."""
    _utc(now)
    reasons: set[str] = set()
    assignments = 0
    claims = 0
    exposure = 0
    if now >= anchor.valid_until:
        reasons.add("handoff_anchor_expired")
    if (
        anchor.manifest_sha256 != protocol.manifest_sha256
        or anchor.closeout_protocol_sha256 != digest(canonical_bytes(protocol))
        or anchor.preclose_state_sha256 != preclose_state.state_sha256
        or anchor.r4_packet_sha256 != digest(canonical_bytes(r4_packet))
        or anchor.r4_result_sha256 != digest(canonical_bytes(r4_result))
        or anchor.triggered_at != r4_packet.observed_at
        or anchor.triggered_at > now
    ):
        reasons.add("trigger_binding_mismatch")
    if anchor.trigger == "r4_hard_stop":
        if r4_result.status != "hard_stop" or not r4_result.stop_required:
            reasons.add("r4_hard_stop_missing")
    elif anchor.triggered_at != protocol.cutoff_at:
        reasons.add("cutoff_trigger_mismatch")

    prior = preclose_state.cohort
    if (
        prior is None
        or prior.signed_release.release.phase != "bounded_live"
        or prior.manifest.manifest_sha256 != anchor.manifest_sha256
        or r4_packet.manifest_sha256 != anchor.manifest_sha256
        or r4_packet.release_sha256 != prior.signed_release.release.release_sha256
        or recovery_anchor.checkpoint.state_sha256 != preclose_state.state_sha256
        or recovery_anchor.assignment_task_ids
        != tuple(item.task_id for item in prior.assignments)
        or recovery_anchor.claim_ids
        != tuple(sorted(item.claim_id for item in preclose_state.attempts))
        or r4_result.assignment_count != len(prior.assignments)
        or r4_result.claim_count != len(preclose_state.attempts)
        or any(item.assigned_at > anchor.triggered_at for item in prior.assignments)
    ):
        reasons.add("preclose_snapshot_mismatch")

    try:
        state = admission.read_current()
        checkpoint = admission.checkpoint.read_current()
    except Exception:
        state = None
        checkpoint = None
        reasons.add("witness_unavailable")
    if state is not None and checkpoint is not None:
        cohort = state.cohort
        assignments = 0 if cohort is None else len(cohort.assignments)
        claims = len(state.attempts)
        if (
            checkpoint.epoch_id != state.epoch_id
            or checkpoint.generation != state.generation
            or checkpoint.state_sha256 != state.state_sha256
        ):
            reasons.add("checkpoint_mismatch")
        if cohort is None or prior is None:
            reasons.add("closed_cohort_missing")
        else:
            closed = cohort.signed_release.release
            if (
                closed.phase != "closed"
                or closed.release_sha256 != anchor.closed_release_sha256
                or closed.sequence != prior.signed_release.release.sequence + 1
                or closed.manifest_sha256 != anchor.manifest_sha256
                or not anchor.triggered_at
                <= closed.issued_at
                <= anchor.triggered_at
                + timedelta(seconds=anchor.max_close_latency_seconds)
                or packet.prepared_at < closed.issued_at
            ):
                reasons.add("closed_release_invalid")
            if cohort.assignments != prior.assignments:
                reasons.add("assignment_roster_changed")
            if tuple(
                (row.attempt.attempt_key, row.claim_id) for row in state.attempts
            ) != tuple(
                (row.attempt.attempt_key, row.claim_id)
                for row in preclose_state.attempts
            ):
                reasons.add("claim_roster_changed")
        if packet.release_sha256 != anchor.closed_release_sha256:
            reasons.add("closeout_release_mismatch")

    try:
        audit.check()
        recovery = inspect_offline_cohort_recovery(
            admission, store, audit, anchor=recovery_anchor
        )
        if recovery.status != "consistent":
            reasons.add("recovery_mismatch")
        if state is not None:
            settled = sum(
                row.charged_microusd
                for row in state.attempts
                if row.status == "settled"
            )
            exposure = settled + recovery.conservative_exposure_microusd
            witnessed_unresolved = sum(
                row.charged_microusd
                for row in state.attempts
                if row.status != "settled"
            )
            if recovery.conservative_exposure_microusd > witnessed_unresolved:
                reasons.add("retained_exposure_unreconciled")
    except Exception:
        reasons.add("recovery_unavailable")
    try:
        intents = {item.attempt_key: item for item in store.list_intents()}
        for link in packet.attempt_links:
            intent = intents.get(link.attempt_key)
            expected = None if intent is None else intent.intent_sha256
            if link.intent_sha256 != expected:
                reasons.add("packet_intent_mismatch")
    except Exception:
        reasons.add("intent_store_unavailable")

    closeout_reasons: tuple[str, ...] = ()
    followup_unknown = 0
    closeout_status: Literal["blocked", "provisional", "reviewable"] = "blocked"
    if state is not None and checkpoint is not None:
        try:
            closeout = validate_offline_cohort_closeout(
                packet,
                protocol=protocol,
                witness=state,
                checkpoint=checkpoint,
                now=now,
            )
            closeout_reasons = closeout.reasons
            closeout_status = closeout.status
            followup_unknown = closeout.followup_unknown_count
            if closeout.status == "blocked":
                reasons.add("closeout_blocked")
        except Exception:
            reasons.add("closeout_unavailable")
    status: Literal["blocked", "pending_followup", "reviewable"] = (
        "blocked"
        if reasons
        else "pending_followup"
        if closeout_status == "provisional"
        else "reviewable"
    )
    return OfflineR5CloseResult(
        status=status,
        reasons=tuple(sorted(reasons)),
        closeout_reasons=closeout_reasons,
        assignment_count=assignments,
        claim_count=claims,
        conservative_exposure_microusd=exposure,
        followup_unknown_count=followup_unknown,
    )


def validate_reproduced_offline_r5_close_handoff(
    packet: CohortCloseoutPacket,
    *,
    protocol: FrozenCloseoutProtocol,
    anchor: FrozenR5CloseAnchor,
    r4_packet: OfflineR4SurveillancePacket,
    r4_result: OfflineR4SurveillanceResult,
    preclose_state: WitnessedState,
    admission: SyntheticWitnessedAdmission,
    store: OfflineTransactionStore,
    audit: SyntheticCohortAuditSink,
    recovery_anchor: FrozenCohortRecoveryAnchor,
    reproduction: OfflineR4TriggerReproduction,
    expected_reproduction_sha256: Digest,
    now: datetime,
) -> OfflineR5CloseResult:
    """Join a previously reproduced R4 trigger to the later R5 close screen."""
    base = validate_offline_r5_close_handoff(
        packet,
        protocol=protocol,
        anchor=anchor,
        r4_packet=r4_packet,
        r4_result=r4_result,
        preclose_state=preclose_state,
        admission=admission,
        store=store,
        audit=audit,
        recovery_anchor=recovery_anchor,
        now=now,
    )
    reasons = set(base.reasons)
    if (
        reproduction.status != "reproduced"
        or digest(canonical_bytes(reproduction)) != expected_reproduction_sha256
        or reproduction.r4_packet_sha256 != anchor.r4_packet_sha256
        or reproduction.r4_result_sha256 != anchor.r4_result_sha256
        or reproduction.preclose_state_sha256 != anchor.preclose_state_sha256
        or reproduction.recovery_anchor_sha256
        != digest(canonical_bytes(recovery_anchor))
        or reproduction.reproduced_at != anchor.triggered_at
    ):
        reasons.add("r4_trigger_reproduction_invalid")
    return OfflineR5CloseResult(
        status="blocked" if reasons else base.status,
        reasons=tuple(sorted(reasons)),
        closeout_reasons=base.closeout_reasons,
        assignment_count=base.assignment_count,
        claim_count=base.claim_count,
        conservative_exposure_microusd=base.conservative_exposure_microusd,
        followup_unknown_count=base.followup_unknown_count,
    )
