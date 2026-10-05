"""Read-only G6-06 R4 surveillance over synthetic cohort metadata."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import Field, field_validator

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
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
    inspect_offline_cohort_audit,
    inspect_offline_cohort_recovery,
)
from mos_eisley.run.witnessed_admission import SyntheticWitnessedAdmission


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("R4 surveillance time must use explicit UTC")
    return value


class FrozenR4SurveillanceAnchor(Contract):
    """Thresholds and expected digests supplied outside the observation packet."""

    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    release_sha256: Digest
    selection_sha256: Digest
    safety_evidence_sha256: Digest
    safety_signal: Literal["clear", "hard_stop", "unavailable"]
    safety_reviewed_at: datetime
    safety_valid_until: datetime
    max_route_age_seconds: Annotated[int, Field(gt=0, le=604_800)]
    max_observation_age_seconds: Annotated[int, Field(gt=0, le=604_800)]
    stop_ack_deadline_seconds: Annotated[int, Field(gt=0, le=86_400)]
    warning_remaining_cohort_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000)]
    hard_stop_exposure_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    valid_until: datetime
    stop_requested_at: datetime | None = None

    @field_validator(
        "valid_until", "stop_requested_at", "safety_reviewed_at", "safety_valid_until"
    )
    @classmethod
    def utc_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)


class OfflineR4TransportEntryReference(Contract):
    """Synthetic per-attempt receipt for one inert transport entry."""

    entry_index: Annotated[int, Field(ge=0)]
    attempt_key: Digest
    request_sha256: Digest
    intent_sha256: Digest
    claim_id: Digest
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class OfflineR4SurveillancePacket(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    release_sha256: Digest
    selection_sha256: Digest
    route_observation_sha256: Digest
    control_entry_sha256: Digest
    safety_signal: Literal["clear", "hard_stop", "unavailable"]
    safety_evidence_sha256: Digest
    safety_reviewed_at: datetime
    safety_valid_until: datetime
    observed_at: datetime
    stop_requested_at: datetime | None = None
    entries: tuple[OfflineR4TransportEntryReference, ...] = ()

    @field_validator(
        "safety_reviewed_at", "safety_valid_until", "observed_at", "stop_requested_at"
    )
    @classmethod
    def utc_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)


class OfflineR4SurveillanceResult(Contract):
    status: Literal["healthy", "warning", "hard_stop", "stopped"]
    reasons: tuple[str, ...]
    assignment_count: Annotated[int, Field(ge=0)]
    claim_count: Annotated[int, Field(ge=0)]
    unresolved_claim_count: Annotated[int, Field(ge=0)]
    uncertain_claim_count: Annotated[int, Field(ge=0)]
    intent_count: Annotated[int, Field(ge=0)]
    audit_count: Annotated[int, Field(ge=0)]
    transport_entry_count: Annotated[int, Field(ge=0)]
    conservative_exposure_microusd: Annotated[int, Field(ge=0)]
    remaining_cohort_microusd: Annotated[int, Field(ge=0)]
    stop_acknowledged: bool
    stop_required: bool
    new_admission_authorized: Literal[False] = False
    stop_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False


def inspect_offline_r4_surveillance(
    packet: OfflineR4SurveillancePacket,
    *,
    anchor: FrozenR4SurveillanceAnchor,
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
) -> OfflineR4SurveillanceResult:
    """Inspect synthetic facts; never advance control, claim, send or read outcomes."""
    _utc(now)
    hard: set[str] = set()
    warning: set[str] = set()
    assignments = 0
    claims = 0
    unresolved_claims = 0
    uncertain_claims = 0
    intents = ()
    events = ()
    exposure = 0
    remaining = 0
    stopped = False
    if type(transport) is not InertRoutingTransport:
        raise ValueError("R4 surveillance requires exact inert transport")
    entries = tuple(transport.entries)
    if (
        now >= anchor.valid_until
        or packet.observed_at > now
        or (now - packet.observed_at).total_seconds()
        > anchor.max_observation_age_seconds
    ):
        hard.add("observation_stale")
    if (
        packet.manifest_sha256 != anchor.manifest_sha256
        or packet.release_sha256 != anchor.release_sha256
        or packet.selection_sha256 != anchor.selection_sha256
        or packet.selection_sha256 != digest(canonical_bytes(selection))
        or selection.preflight_sha256 != preflight.preflight_sha256
        or selection.candidate_id not in preflight.eligible_candidate_ids
        or selection.source != "calibrated_route"
    ):
        hard.add("source_binding_mismatch")
    if (
        packet.safety_evidence_sha256 != anchor.safety_evidence_sha256
        or packet.safety_signal != anchor.safety_signal
        or packet.safety_reviewed_at != anchor.safety_reviewed_at
        or packet.safety_valid_until != anchor.safety_valid_until
        or not packet.safety_reviewed_at <= now < packet.safety_valid_until
        or packet.safety_signal == "unavailable"
    ):
        hard.add("safety_signal_unavailable")
    if packet.safety_signal == "hard_stop" or anchor.safety_signal == "hard_stop":
        hard.add("safety_hard_stop")
    if packet.stop_requested_at != anchor.stop_requested_at:
        hard.add("stop_request_mismatch")
    if anchor.stop_requested_at is not None and anchor.stop_requested_at > now:
        hard.add("stop_request_time_invalid")

    try:
        state = admission.read_current()
    except Exception:
        state = None
        hard.add("witness_unavailable")
    if state is not None:
        cohort = state.cohort
        assignments = 0 if cohort is None else len(cohort.assignments)
        claims = len(state.attempts)
        unresolved_claims = sum(item.status != "settled" for item in state.attempts)
        uncertain_claims = sum(item.status == "uncertain" for item in state.attempts)
        if unresolved_claims:
            warning.add("unresolved_exposure")
        control = state.control.signed_control.control
        stopped = control.emergency_stop
        if packet.control_entry_sha256 != state.control.anchor_entry_sha256:
            hard.add("control_binding_mismatch")
        if (
            not stopped
            and preflight.anchored_control_entry_sha256
            != state.control.anchor_entry_sha256
        ):
            hard.add("control_binding_mismatch")
        if not control.issued_at <= now < control.valid_until:
            hard.add("control_stale")
        if cohort is None:
            hard.add("cohort_missing")
        else:
            release = cohort.signed_release.release
            if (
                cohort.manifest.manifest_sha256 != anchor.manifest_sha256
                or release.release_sha256 != anchor.release_sha256
                or release.phase != "bounded_live"
                or not cohort.manifest.valid_from <= now < cohort.manifest.valid_until
                or not release.issued_at <= now < release.valid_until
                or selection.candidate_policy_sha256
                != cohort.manifest.candidate_policy_sha256
                or preflight.candidate_policy_sha256
                != cohort.manifest.candidate_policy_sha256
            ):
                hard.add("cohort_release_invalid")
            assigned = {item.task_id: item for item in cohort.assignments}
            for claim in state.attempts:
                attempt = claim.attempt
                row = assigned.get(attempt.task_id)
                if (
                    row is None
                    or row.session_id != attempt.session_id
                    or row.stage_id != attempt.stage_id
                    or row.release_sha256 != release.release_sha256
                    or row.assigned_generation >= claim.admitted_generation
                ):
                    hard.add("claim_assignment_mismatch")
        budget = admission.budget_policy
        settled = sum(
            item.charged_microusd for item in state.attempts if item.status == "settled"
        )
        unresolved = sum(
            item.charged_microusd for item in state.attempts if item.status != "settled"
        )
        exposure = settled + unresolved
        task_totals: dict[str, int] = {}
        session_totals: dict[str, int] = {}
        for row in state.attempts:
            task_id = row.attempt.task_id
            session_id = row.attempt.session_id
            task_totals[task_id] = task_totals.get(task_id, 0) + row.charged_microusd
            session_totals[session_id] = (
                session_totals.get(session_id, 0) + row.charged_microusd
            )
        if any(
            amount > budget.task_ceiling_microusd for amount in task_totals.values()
        ) or any(
            amount > budget.session_ceiling_microusd
            for amount in session_totals.values()
        ):
            hard.add("budget_scope_violation")
        if any(item.status == "violation" for item in state.attempts):
            hard.add("budget_violation")
        if claims > budget.max_attempts:
            hard.add("attempt_count_violation")
        remaining = max(0, budget.cohort_ceiling_microusd - exposure)
        if exposure > budget.cohort_ceiling_microusd:
            hard.add("budget_scope_violation")

    try:
        preflight.check_current(now)
    except Exception:
        hard.add("preflight_unavailable")
    try:
        if packet.route_observation_sha256 != digest(
            canonical_bytes(route_probe.current)
        ):
            hard.add("route_observation_mismatch")
        route_probe.check(selection, now)
        if (
            now - route_probe.current.observed_at
        ).total_seconds() > anchor.max_route_age_seconds:
            hard.add("route_observation_stale")
    except Exception:
        hard.add("route_unavailable")
    for source, reason in (
        (monitor, "monitor_unavailable"),
        (alerts, "alert_unavailable"),
        (audit, "audit_unavailable"),
    ):
        try:
            source.check()
        except Exception:
            hard.add(reason)
    try:
        intents = store.list_intents()
        events = audit.read_current()
        if not inspect_offline_cohort_audit(admission, store, audit).complete:
            hard.add("audit_join_incomplete")
    except Exception:
        hard.add("audit_join_unavailable")
    try:
        recovery = inspect_offline_cohort_recovery(
            admission, store, audit, anchor=recovery_anchor
        )
        if recovery.status != "consistent":
            hard.add("recovery_mismatch")
        elif state is not None:
            exposure = (
                sum(
                    item.charged_microusd
                    for item in state.attempts
                    if item.status == "settled"
                )
                + recovery.conservative_exposure_microusd
            )
            remaining = max(
                0, admission.budget_policy.cohort_ceiling_microusd - exposure
            )
    except Exception:
        hard.add("recovery_unavailable")

    if state is not None:
        claim_index = {row.attempt.attempt_key: row for row in state.attempts}
        intent_index = {row.attempt_key: row for row in intents}
        audit_index = {row.attempt_key: row for row in events}
        for claim in state.attempts:
            if claim.attempt.attempt_key not in intent_index:
                hard.add("claim_intent_missing")
        for intent in intents:
            claim = claim_index.get(intent.attempt_key)
            event = audit_index.get(intent.attempt_key)
            if claim is None or claim.claim_id != intent.claim_id:
                hard.add("intent_claim_mismatch")
            if event is None or event.intent_sha256 != intent.intent_sha256:
                hard.add("intent_audit_missing")
        referenced_indexes: set[int] = set()
        referenced_attempts: set[str] = set()
        if len(packet.entries) != len(entries):
            hard.add("transport_entry_unjoined")
        for ref in packet.entries:
            if (
                ref.entry_index in referenced_indexes
                or ref.attempt_key in referenced_attempts
                or ref.entry_index >= len(entries)
                or ref.observed_at > now
            ):
                hard.add("transport_entry_invalid")
                continue
            referenced_indexes.add(ref.entry_index)
            referenced_attempts.add(ref.attempt_key)
            claim = claim_index.get(ref.attempt_key)
            intent = intent_index.get(ref.attempt_key)
            event = audit_index.get(ref.attempt_key)
            if (
                entries[ref.entry_index] != ref.request_sha256
                or claim is None
                or intent is None
                or event is None
                or claim.claim_id != ref.claim_id
                or claim.attempt.request_sha256 != ref.request_sha256
                or intent.claim_id != ref.claim_id
                or intent.intent_sha256 != ref.intent_sha256
                or event.intent_sha256 != ref.intent_sha256
                or ref.observed_at < intent.recorded_at
                or ref.observed_at < event.recorded_at
            ):
                hard.add("transport_entry_unjoined")
        for claim in state.attempts:
            if claim.status in ("settled", "uncertain", "violation") and (
                claim.attempt.attempt_key not in referenced_attempts
            ):
                hard.add("terminal_claim_without_entry")
        if exposure >= admission.budget_policy.cohort_ceiling_microusd:
            hard.add("cohort_budget_exhausted")
        if exposure >= anchor.hard_stop_exposure_microusd:
            hard.add("exposure_hard_stop")
        if remaining <= anchor.warning_remaining_cohort_microusd:
            warning.add("cohort_headroom_warning")

    stop_ack_valid = stopped
    if anchor.stop_requested_at is not None:
        if not stopped:
            hard.add("stop_ack_missing")
        elif state is not None:
            latency = (
                state.control.signed_control.control.issued_at
                - anchor.stop_requested_at
            ).total_seconds()
            if latency < 0:
                hard.add("stop_ack_invalid")
                stop_ack_valid = False
            elif latency > anchor.stop_ack_deadline_seconds:
                hard.add("stop_ack_late")
                stop_ack_valid = False
    if stopped:
        hard.add("witness_stopped")
    status: Literal["healthy", "warning", "hard_stop", "stopped"] = (
        "stopped"
        if stopped
        else "hard_stop"
        if hard
        else "warning"
        if warning
        else "healthy"
    )
    return OfflineR4SurveillanceResult(
        status=status,
        reasons=tuple(sorted(hard | warning)),
        assignment_count=assignments,
        claim_count=claims,
        unresolved_claim_count=unresolved_claims,
        uncertain_claim_count=uncertain_claims,
        intent_count=len(intents),
        audit_count=len(events),
        transport_entry_count=len(entries),
        conservative_exposure_microusd=exposure,
        remaining_cohort_microusd=remaining,
        stop_acknowledged=stop_ack_valid,
        stop_required=bool(hard) and not stopped,
    )
