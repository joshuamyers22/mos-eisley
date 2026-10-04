"""Inert scheduling qualification contracts; no clocks, tasks or dispatch adapters.

The host supplies explicit observations and persists each returned state before
acting on an admission. This module cannot start providers, tools or background
work. It is not connected to terminal commands or session startup.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_goal import GoalStatus, merge_ledger
from mos_eisley.core.models import (
    Contract,
    Digest,
    Identifier,
    Text,
    canonical_bytes,
    digest,
)
from mos_eisley.task_state import ResourceCeiling, ResourceLedger

Time = Annotated[float, Field(ge=0)]
Interval = Annotated[int, Field(ge=1, le=86400)]


class ScheduleBinding(Contract):
    owner_uid: Annotated[int, Field(ge=0)]
    session_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    workspace_sha256: Digest
    revision_sha256: Digest
    policy_sha256: Digest
    goal_id: Identifier
    goal_definition_sha256: Digest
    task_id: Identifier


class InertScheduleSpec(Contract):
    schedule_id: Identifier
    binding: ScheduleBinding
    prompt: Text
    cadence: Literal["fixed", "dynamic"] = "fixed"
    interval_seconds: Interval
    minimum_interval_seconds: Interval
    maximum_interval_seconds: Interval
    expires_at: Time
    maximum_fires: Annotated[int, Field(ge=1, le=16)]
    ceiling: ResourceCeiling
    local_sources: Annotated[tuple[Identifier, ...], Field(max_length=4)] = ()

    @model_validator(mode="after")
    def bounded_spec(self) -> Self:
        if not self.prompt.strip():
            raise ValueError("A schedule requires an explicit nonblank task.")
        if (
            not self.minimum_interval_seconds
            <= self.interval_seconds
            <= self.maximum_interval_seconds
        ):
            raise ValueError("Cadence must be within its frozen bounds.")
        if self.cadence == "fixed" and not (
            self.minimum_interval_seconds
            == self.interval_seconds
            == self.maximum_interval_seconds
        ):
            raise ValueError("Fixed cadence must have equal interval bounds.")
        if len(set(self.local_sources)) != len(self.local_sources):
            raise ValueError("Local fixture source IDs must be unique.")
        if self.maximum_fires > self.ceiling.attempts or self.ceiling.cost_microusd:
            raise ValueError(
                "Inert schedules require bounded attempts and zero paid allowance."
            )
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class LocalWakeupEvent(Contract):
    """Host-owned local fixture metadata, never authenticated external ingress."""

    source_id: Identifier
    event_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    binding: ScheduleBinding
    payload_sha256: Digest
    payload_bytes: Annotated[int, Field(ge=0, le=4096)]
    payload_omitted: Literal[True] = True
    kind: Literal["local_test", "local_child"]


class SourceCursor(Contract):
    source_id: Identifier
    sequence: Annotated[int, Field(ge=0)] = 0
    recent_ids: Annotated[tuple[Identifier, ...], Field(max_length=16)] = ()

    @model_validator(mode="after")
    def unique_events(self) -> Self:
        if len(set(self.recent_ids)) != len(self.recent_ids):
            raise ValueError("Replay cursor IDs must be unique.")
        return self


class WakeupReservation(Contract):
    operation_id: Digest
    schedule_sha256: Digest
    request_sha256: Digest
    ordinal: Annotated[int, Field(ge=1, le=16)]
    reserved: ResourceLedger
    notification_count: Annotated[int, Field(ge=1, le=65)]
    state: Literal["reserved", "completed", "uncertain", "skipped"] = "reserved"
    result_sha256: Digest | None = None
    completion_usage: ResourceLedger | None = None


class InertScheduleState(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["inert_fixture"] = "inert_fixture"
    spec: InertScheduleSpec
    created_at: Time
    last_seen_at: Time
    next_due_at: Time
    effective_interval_seconds: Interval
    cadence_history: Annotated[tuple[Interval, ...], Field(min_length=1, max_length=16)]
    status: Literal[
        "active", "paused", "blocked", "expired", "cancelled", "exhausted", "uncertain"
    ] = "active"
    reason: Annotated[str, Field(min_length=1, max_length=2000)] = (
        "Explicit inert fixture."
    )
    pending_timer: bool = False
    pending_events: Annotated[int, Field(ge=0, le=64)] = 0
    accepted_events: Annotated[int, Field(ge=0, le=64)] = 0
    cursors: Annotated[tuple[SourceCursor, ...], Field(max_length=4)] = ()
    ledger: ResourceLedger = ResourceLedger()
    aggregate_exposure: ResourceLedger = ResourceLedger()
    fires: Annotated[tuple[WakeupReservation, ...], Field(max_length=16)] = ()
    dispatch_authorized: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            not self.created_at < self.spec.expires_at
            or self.last_seen_at < self.created_at
        ):
            raise ValueError("Schedule lifetime is invalid.")
        if (
            not self.spec.minimum_interval_seconds
            <= self.effective_interval_seconds
            <= self.spec.maximum_interval_seconds
        ):
            raise ValueError("Effective cadence exceeds its frozen bounds.")
        if self.cadence_history[-1] != self.effective_interval_seconds:
            raise ValueError("Cadence history does not match its effective interval.")
        if self.next_due_at < self.created_at or any(
            not self.spec.minimum_interval_seconds
            <= interval
            <= self.spec.maximum_interval_seconds
            for interval in self.cadence_history
        ):
            raise ValueError("Retained cadence history or next due time is invalid.")
        if tuple(c.source_id for c in self.cursors) != self.spec.local_sources:
            raise ValueError(
                "Schedule cursor sources differ from its frozen allowlist."
            )
        if self.pending_events > self.accepted_events:
            raise ValueError("Pending events exceed their admitted inventory.")
        if len(self.fires) > self.spec.maximum_fires or tuple(
            f.ordinal for f in self.fires
        ) != tuple(range(1, len(self.fires) + 1)):
            raise ValueError("Wakeup fire inventory is invalid.")
        if len({f.operation_id for f in self.fires}) != len(self.fires) or any(
            f.schedule_sha256 != self.spec.sha256 for f in self.fires
        ):
            raise ValueError("Wakeup operation identities differ from their schedule.")
        if sum(f.state == "reserved" for f in self.fires) > 1:
            raise ValueError("A task cannot have overlapping wakeup reservations.")
        if (
            any(f.state == "uncertain" for f in self.fires)
            and not self.ledger.uncertain_effects
        ):
            raise ValueError("Uncertain wakeups must retain their exposure.")
        floor = ResourceLedger()
        for fire in self.fires:
            if fire.operation_id != digest(
                f"{self.spec.sha256}:{fire.ordinal}:{fire.request_sha256}".encode()
            ):
                raise ValueError(
                    "Wakeup operation ID is not its stable ordinal identity."
                )
            if (
                fire.reserved.attempts != 1
                or fire.reserved.uncertain_effects
                or fire.reserved.cost_microusd
                or fire.reserved.correction_cycles
                or fire.reserved.review_rounds
            ):
                raise ValueError("Wakeup reservation must be one inert unpaid attempt.")
            if (fire.state == "completed") != (
                fire.result_sha256 is not None and fire.completion_usage is not None
            ):
                raise ValueError("Completed wakeups require an exact measured receipt.")
            if fire.completion_usage is not None and (
                fire.completion_usage.attempts != 1
                or fire.completion_usage.cost_microusd
                or fire.completion_usage.uncertain_effects
                or fire.completion_usage.correction_cycles
                or fire.completion_usage.review_rounds
            ):
                raise ValueError(
                    "Fixture completion cannot certify paid or uncertain usage."
                )
            floor = _add(
                floor,
                merge_ledger(fire.reserved, fire.completion_usage or ResourceLedger()),
            )
        if any(
            getattr(self.ledger, key) < getattr(floor, key)
            for key in ResourceLedger.model_fields
        ):
            raise ValueError("Schedule ledger cannot reset retained fire charges.")
        if any(
            getattr(self.aggregate_exposure, key) < getattr(self.ledger, key)
            for key in ResourceCeiling.model_fields
        ):
            raise ValueError("Aggregate exposure cannot erase schedule usage.")
        return self


class WakeupGate(Contract):
    """Current trusted observations; values are not derived from event payloads."""

    binding: ScheduleBinding
    goal_status: GoalStatus
    aggregate_ledger: ResourceLedger
    aggregate_ceiling: ResourceCeiling
    safe_boundary: bool
    user_pending: bool
    task_pending: bool = False
    goal_expires_at: Time


class ScheduleQueueBinding(Contract):
    operation_id: Digest
    message_position: Annotated[int, Field(ge=0, le=15)]


class StoredSchedule(Contract):
    """Session header record; this record and its queue entries commit together."""

    state: InertScheduleState
    queue_bindings: Annotated[
        tuple[ScheduleQueueBinding, ...], Field(max_length=16)
    ] = ()

    @model_validator(mode="after")
    def exact_bindings(self) -> Self:
        if tuple(b.operation_id for b in self.queue_bindings) != tuple(
            f.operation_id for f in self.state.fires
        ):
            raise ValueError("Every retained wakeup must bind exactly one queue entry.")
        if len({b.message_position for b in self.queue_bindings}) != len(
            self.queue_bindings
        ):
            raise ValueError("Schedule queue positions must be unique.")
        return self


def skip_wakeup(
    state: InertScheduleState, operation_id: str, *, reason: str
) -> InertScheduleState:
    """Stop known undispatched work without guessing provider effects."""
    state = _state(state)
    fire = next(f for f in state.fires if f.operation_id == operation_id)
    if fire.state != "reserved":
        raise ValueError("Only a known undispatched reservation can be skipped.")
    status = "paused" if state.status == "active" else state.status
    return _state(
        state,
        status=status,
        reason=reason,
        fires=tuple(
            f.model_copy(update={"state": "skipped"}) if f == fire else f
            for f in state.fires
        ),
    )


def _state(state: InertScheduleState, **updates: object) -> InertScheduleState:
    return InertScheduleState.model_validate_json(
        state.model_copy(update=updates).model_dump_json()
    )


def _time(now: float) -> None:
    if not math.isfinite(now) or now < 0:
        raise ValueError("Fixture clock must be finite and nonnegative.")


def _add(left: ResourceLedger, right: ResourceLedger) -> ResourceLedger:
    return ResourceLedger.model_validate(
        {
            key: getattr(left, key) + getattr(right, key)
            for key in ResourceLedger.model_fields
        }
    )


def create_inert_schedule(spec: InertScheduleSpec, *, now: float) -> InertScheduleState:
    _time(now)
    spec = InertScheduleSpec.model_validate_json(spec.model_dump_json())
    return InertScheduleState(
        spec=spec,
        created_at=now,
        last_seen_at=now,
        next_due_at=now + spec.interval_seconds,
        effective_interval_seconds=spec.interval_seconds,
        cadence_history=(spec.interval_seconds,),
        cursors=tuple(SourceCursor(source_id=s) for s in spec.local_sources),
    )


def observe_timer(state: InertScheduleState, *, now: float) -> InertScheduleState:
    _time(now)
    state = _state(state)
    if state.status in {"cancelled", "expired", "exhausted", "uncertain"}:
        return state
    if now < state.last_seen_at:
        return _state(
            state,
            status="paused",
            reason="Clock moved backwards; explicit revalidation required.",
        )
    if now >= state.spec.expires_at:
        return _state(
            state,
            status="expired",
            pending_timer=False,
            pending_events=0,
            last_seen_at=now,
            reason="Schedule expired.",
        )
    due = state.status == "active" and now >= state.next_due_at
    return _state(
        state,
        last_seen_at=now,
        pending_timer=state.pending_timer or due,
        next_due_at=now + state.effective_interval_seconds
        if due
        else state.next_due_at,
    )


def observe_local_event(
    state: InertScheduleState, event: LocalWakeupEvent, *, now: float
) -> InertScheduleState:
    event = LocalWakeupEvent.model_validate_json(event.model_dump_json())
    state = observe_timer(state, now=now)
    if (
        event.binding != state.spec.binding
        or event.source_id not in state.spec.local_sources
    ):
        raise ValueError(
            "Local event is outside the frozen owner/task/workspace source scope."
        )
    if state.status != "active" or state.accepted_events >= 64:
        return state
    cursor = next(c for c in state.cursors if c.source_id == event.source_id)
    if event.sequence <= cursor.sequence or event.event_id in cursor.recent_ids:
        return state
    updated = cursor.model_copy(
        update={
            "sequence": event.sequence,
            "recent_ids": (*cursor.recent_ids[-15:], event.event_id),
        }
    )
    return _state(
        state,
        accepted_events=state.accepted_events + 1,
        pending_events=state.pending_events + 1,
        cursors=tuple(updated if c == cursor else c for c in state.cursors),
    )


def change_cadence(
    state: InertScheduleState, interval_seconds: int, *, now: float
) -> InertScheduleState:
    state = observe_timer(state, now=now)
    if state.status != "active" or state.spec.cadence != "dynamic":
        raise ValueError("Only an active dynamic fixture can change cadence.")
    if (
        not state.spec.minimum_interval_seconds
        <= interval_seconds
        <= state.spec.maximum_interval_seconds
        or len(state.cadence_history) >= 16
    ):
        raise ValueError("Cadence change exceeds the frozen interval/history bounds.")
    return _state(
        state,
        effective_interval_seconds=interval_seconds,
        next_due_at=now + interval_seconds,
        cadence_history=(*state.cadence_history, interval_seconds),
    )


def cancel_schedule(state: InertScheduleState) -> InertScheduleState:
    state = _state(state)
    uncertain = any(f.state == "reserved" for f in state.fires)
    return _state(
        state,
        status="cancelled",
        reason="Explicit cancellation; retained exposure is not refunded.",
        pending_timer=False,
        pending_events=0,
        fires=tuple(
            f.model_copy(update={"state": "uncertain"}) if f.state == "reserved" else f
            for f in state.fires
        ),
        ledger=state.ledger.model_copy(
            update={
                "uncertain_effects": state.ledger.uncertain_effects + int(uncertain)
            }
        ),
    )


def _binding_matches(state: InertScheduleState, gate: WakeupGate) -> bool:
    return gate.binding == state.spec.binding


def reserve_wakeup(
    state: InertScheduleState,
    gate: WakeupGate,
    requested: ResourceLedger,
    *,
    now: float,
    request_sha256: str,
) -> InertScheduleState:
    """Produce an inert intent that must be persisted before queue admission."""
    gate = WakeupGate.model_validate_json(gate.model_dump_json())
    requested = ResourceLedger.model_validate_json(requested.model_dump_json())
    if (
        requested.attempts != 1
        or requested.uncertain_effects
        or requested.cost_microusd
        or requested.correction_cycles
        or requested.review_rounds
    ):
        raise ValueError("An inert wakeup reserves one unpaid author attempt only.")
    state = observe_timer(state, now=now)
    if state.status != "active":
        return state
    if not _binding_matches(state, gate):
        return _state(
            state,
            status="blocked",
            reason="Owner, session, revision, policy or goal binding changed.",
        )
    if state.aggregate_exposure.uncertain_effects:
        return _state(
            state, status="uncertain", reason="Retained task exposure is uncertain."
        )
    if (
        gate.goal_status != "working"
        or gate.aggregate_ledger.uncertain_effects
        or state.ledger.uncertain_effects
        or now >= gate.goal_expires_at
    ):
        return _state(
            state,
            status="paused",
            reason="Goal is stopped, expired or uncertain; wakeups cannot resume it.",
        )
    if (
        not gate.safe_boundary
        or gate.user_pending
        or gate.task_pending
        or any(f.state == "reserved" for f in state.fires)
    ):
        return state
    if not state.pending_timer and not state.pending_events:
        return state
    ledger = _add(state.ledger, requested)
    aggregate = _add(
        merge_ledger(state.aggregate_exposure, gate.aggregate_ledger), requested
    )
    if (
        len(state.fires) >= state.spec.maximum_fires
        or ledger.exceeds(state.spec.ceiling)
        or aggregate.exceeds(gate.aggregate_ceiling)
    ):
        return _state(
            state,
            status="exhausted",
            pending_timer=False,
            pending_events=0,
            reason="Maximum fires or retained schedule/task allowance exhausted.",
        )
    ordinal = len(state.fires) + 1
    operation_id = digest(f"{state.spec.sha256}:{ordinal}:{request_sha256}".encode())
    fire = WakeupReservation(
        operation_id=operation_id,
        schedule_sha256=state.spec.sha256,
        request_sha256=request_sha256,
        ordinal=ordinal,
        reserved=requested,
        notification_count=int(state.pending_timer) + state.pending_events,
    )
    return _state(
        state,
        fires=(*state.fires, fire),
        ledger=ledger,
        aggregate_exposure=aggregate,
        pending_timer=False,
        pending_events=0,
        reason="Inert intent reserved; explicit host acknowledgement required.",
    )


def complete_wakeup(
    state: InertScheduleState,
    operation_id: str,
    observed: ResourceLedger,
    result_sha256: str,
) -> InertScheduleState:
    """Exact fixture receipt; retain conservative charges and any overages."""
    state = _state(state)
    observed = ResourceLedger.model_validate_json(observed.model_dump_json())
    fire = next((f for f in state.fires if f.operation_id == operation_id), None)
    if (
        fire is None
        or observed.attempts != 1
        or observed.uncertain_effects
        or observed.cost_microusd
        or observed.correction_cycles
        or observed.review_rounds
    ):
        raise ValueError(
            "Completion requires the exact unpaid reserved operation and known usage."
        )
    if (
        fire.state == "completed"
        and fire.result_sha256 == result_sha256
        and fire.completion_usage == observed
    ):
        return state
    if fire.state != "reserved":
        raise ValueError(
            "Uncertain, cancelled or acknowledged wakeups cannot replay "
            "or self-reconcile."
        )
    extra = ResourceLedger(
        input_bytes=max(0, observed.input_bytes - fire.reserved.input_bytes),
        output_bytes=max(0, observed.output_bytes - fire.reserved.output_bytes),
    )
    ledger = _add(state.ledger, extra)
    exhausted = len(state.fires) >= state.spec.maximum_fires or ledger.exceeds(
        state.spec.ceiling
    )
    status = "exhausted" if exhausted and state.status == "active" else state.status
    completed = fire.model_copy(
        update={
            "state": "completed",
            "result_sha256": result_sha256,
            "completion_usage": observed,
        }
    )
    return _state(
        state,
        fires=tuple(completed if f == fire else f for f in state.fires),
        ledger=ledger,
        aggregate_exposure=_add(state.aggregate_exposure, extra),
        status=status,
    )


def recover_schedule(
    state: InertScheduleState, gate: WakeupGate, *, now: float
) -> InertScheduleState:
    """Cold restart never schedules work or guesses whether an admission took effect."""
    state = observe_timer(state, now=now)
    gate = WakeupGate.model_validate_json(gate.model_dump_json())
    held = any(f.state == "reserved" for f in state.fires)
    if held:
        state = _state(
            state,
            status="cancelled" if state.status == "cancelled" else "uncertain",
            fires=tuple(
                f.model_copy(update={"state": "uncertain"})
                if f.state == "reserved"
                else f
                for f in state.fires
            ),
            ledger=state.ledger.model_copy(
                update={"uncertain_effects": state.ledger.uncertain_effects + 1}
            ),
            reason="Restart lost admission acknowledgement; retained without replay.",
        )
    if state.status in {"cancelled", "expired", "exhausted", "uncertain"}:
        return state
    return _state(
        state,
        status="paused" if _binding_matches(state, gate) else "blocked",
        next_due_at=max(state.next_due_at, now + state.effective_interval_seconds),
        aggregate_exposure=merge_ledger(
            state.aggregate_exposure, gate.aggregate_ledger
        ),
        reason="Restart requires explicit current goal/workspace/policy revalidation.",
    )


def resume_schedule(
    state: InertScheduleState, gate: WakeupGate, *, now: float
) -> InertScheduleState:
    state = observe_timer(state, now=now)
    gate = WakeupGate.model_validate_json(gate.model_dump_json())
    if (
        state.status not in {"paused", "active"}
        or not _binding_matches(state, gate)
        or now < state.last_seen_at
    ):
        raise ValueError(
            "Schedule cannot resume with a terminal, stale or backwards-clock identity."
        )
    aggregate = merge_ledger(state.aggregate_exposure, gate.aggregate_ledger)
    if (
        gate.goal_status != "working"
        or aggregate.uncertain_effects
        or state.ledger.uncertain_effects
        or now >= gate.goal_expires_at
        or aggregate.exceeds(gate.aggregate_ceiling)
        or state.ledger.exceeds(state.spec.ceiling)
        or len(state.fires) >= state.spec.maximum_fires
    ):
        raise ValueError(
            "Resume cannot bypass a stopped goal, uncertainty "
            "or retained resource limits."
        )
    if (
        not gate.safe_boundary
        or gate.user_pending
        or gate.task_pending
        or any(f.state == "reserved" for f in state.fires)
    ):
        raise ValueError(
            "Schedule resume requires a safe task boundary after user work."
        )
    return _state(
        state,
        status="active",
        aggregate_exposure=aggregate,
        next_due_at=now + state.effective_interval_seconds,
        pending_timer=False,
        reason="Explicitly revalidated; qualified host owns subsequent admission.",
    )
