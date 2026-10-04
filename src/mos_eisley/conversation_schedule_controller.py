"""Durable recorded scheduling admission through the existing session owner."""

from collections.abc import Callable
from threading import RLock

from mos_eisley.conversation_branch_controller import ConversationBranchController
from mos_eisley.conversation_goal_controller import StateT
from mos_eisley.conversation_pending import PendingTextLimits
from mos_eisley.conversation_schedule import (
    InertScheduleSpec,
    LocalWakeupEvent,
    ScheduleBinding,
    ScheduleQueueBinding,
    StoredSchedule,
    WakeupGate,
    change_cadence,
    complete_wakeup,
    create_inert_schedule,
    observe_local_event,
    observe_timer,
    recover_schedule,
    reserve_wakeup,
    resume_schedule,
    skip_wakeup,
)
from mos_eisley.conversation_schedule_handlers import ScheduleReads
from mos_eisley.conversation_schedule_sources import (
    LocalResultAuthorization,
    LocalResultBatch,
    LocalResultSource,
)
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    ConversationEntry,
    RuntimeConversationState,
    validate_runtime_state,
)
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.task_state import ResourceCeiling, ResourceLedger


def _with_schedule_holds(
    state: RuntimeConversationState,
    ledger: ResourceLedger,
    *,
    goal_id: str | None = None,
    exclude_position: int | None = None,
) -> ResourceLedger:
    totals = {key: getattr(ledger, key) for key in ResourceLedger.model_fields}
    for record in state.schedules:
        if goal_id is not None and record.state.spec.binding.goal_id != goal_id:
            continue
        for fire, link in zip(record.state.fires, record.queue_bindings, strict=True):
            if link.message_position == exclude_position:
                continue
            if fire.state == "skipped" or (
                fire.state == "reserved"
                and state.entries[link.message_position].status == "queued"
            ):
                for key in totals:
                    totals[key] += getattr(fire.reserved, key)
    return ResourceLedger.model_validate(totals)


def scheduled_goal_exposure(
    state: RuntimeConversationState,
    goal_id: str,
    *,
    exclude_position: int | None = None,
) -> ResourceLedger:
    """Add known undispatched holds which never entered the goal's author ledger."""
    goal = next(g for g in state.goals if g.goal_id == goal_id)
    return _with_schedule_holds(
        state, goal.ledger, goal_id=goal_id, exclude_position=exclude_position
    )


def scheduled_branch_exposure(
    state: RuntimeConversationState, *, exclude_position: int | None = None
) -> ResourceLedger:
    if state.branch_budget is None:
        raise ValueError("No branch allowance is retained.")
    return _with_schedule_holds(
        state, state.branch_budget.ledger, exclude_position=exclude_position
    )


class ConversationScheduleController(ConversationBranchController[StateT]):
    schedule_reads: ScheduleReads
    schedule_sources: dict[tuple[str, str], LocalResultSource]
    schedule_observer: Callable[[InertScheduleSpec], ScheduleBinding] | None
    schedule_event_validator: Callable[[LocalWakeupEvent], None] | None
    _schedule_timer_owner: object | None
    schedule_timer_active: bool
    _schedule_lock: RLock
    pending_limits: PendingTextLimits | None

    def claim_schedule_timers(self, owner: object) -> None:
        """One terminal owns timer wakeups; this claim grants no live execution."""
        with self._schedule_lock:
            if self._schedule_timer_owner is not None:
                raise ValueError("This controller already has an active timer owner.")
            self._schedule_timer_owner = owner
            self.schedule_timer_active = (
                self.schedule_observer is not None and self.task_scope is None
            )

    def owns_schedule_timers(self, owner: object) -> bool:
        return self._schedule_timer_owner is owner and self.schedule_timer_active

    def release_schedule_timers(self, owner: object) -> bool:
        """Pause under the ownership lock before permitting a replacement driver."""
        with self._schedule_lock:
            if self._schedule_timer_owner is not owner:
                return False
            driving = self.schedule_timer_active
            self.schedule_timer_active = False
            self.schedule_reads.cancel()
            try:
                if driving and not self._broken:
                    for record in self.state.schedules:
                        if record.state.status == "active":
                            self.pause_schedule(
                                record.state.spec.schedule_id,
                                expected_revision=self.state.revision,
                                reason=(
                                    "Active session closed; "
                                    "explicit loop resume required."
                                ),
                            )
            finally:
                self._schedule_timer_owner = None
            return True

    @property
    def schedule_timer_idle(self) -> bool:
        goal = self.current_goal
        return (
            not self._busy
            and not self._side_busy
            and not any(e.status in {"queued", "running"} for e in self.state.entries)
            and (goal is None or not goal.reservations and not goal.evaluating_sha256)
        )

    def read_schedule_binding(self, spec: InertScheduleSpec) -> ScheduleBinding:
        observer = self.schedule_observer
        if observer is None:
            raise ValueError("No trusted schedule observer.")

        def read() -> ScheduleBinding:
            return ScheduleBinding.model_validate_json(canonical_bytes(observer(spec)))

        return self.schedule_reads.call(read)

    def reset_schedule_handlers(self) -> None:
        if not self.schedule_timer_idle:
            raise ValueError("Handler reset requires an idle controller.")
        self.schedule_reads.reset()

    def _qualified_source(
        self, record: StoredSchedule, source: LocalResultSource
    ) -> LocalResultAuthorization:
        auth = LocalResultAuthorization.model_validate_json(
            canonical_bytes(source.authorization)
        )
        if (
            auth.binding != record.state.spec.binding
            or auth.pin not in record.state.spec.local_source_pins
        ):
            raise ValueError("Local source differs from its frozen authorization.")
        return auth

    def register_schedule_source(
        self,
        schedule_id: str,
        source: LocalResultSource,
        *,
        expected_revision: int,
    ) -> None:
        """Trusted host registration only; restore exact pins after restart."""
        with self._schedule_lock, self.schedule_reads.operation():
            record = self._schedule_record(schedule_id)
            auth = self.schedule_reads.call(
                lambda: self._qualified_source(record, source)
            )
            if (
                self.state.revision != expected_revision
                or self._schedule_gate(record).binding != record.state.spec.binding
            ):
                raise ValueError("Local source registration scope/revision changed.")
            self.schedule_reads.check()
            if self.state.revision != expected_revision:
                raise ValueError("Local registration raced with parent mutation.")
            self.schedule_sources[(schedule_id, auth.source_id)] = source

    def _validate_schedule_sources(self, record: StoredSchedule) -> None:
        for pin in record.state.spec.local_source_pins:
            source = self.schedule_sources.get(
                (record.state.spec.schedule_id, pin.source_id)
            )
            if source is None:
                raise ValueError("Frozen source requires trusted host registration.")
            self.schedule_reads.call(
                lambda source=source: self._qualified_source(record, source)
            )

    def poll_schedule_sources(
        self, schedule_id: str, *, expected_revision: int
    ) -> bool:
        """One bounded metadata notification per safe owner turn, without dispatch."""
        with self._schedule_lock, self.schedule_reads.operation():
            if self.state.revision != expected_revision:
                raise ValueError("Local source polling revision is stale.")
            record = self._schedule_record(schedule_id)
            if (
                record.state.status != "active"
                or record.state.accepted_events >= 64
                or not self.schedule_timer_idle
            ):
                return False
            gate = self._schedule_gate(record)
            if gate.binding != record.state.spec.binding or gate.goal_status not in {
                "working",
                "waiting",
            }:
                raise ValueError("Local result polling requires the frozen goal scope.")
            for pin in record.state.spec.local_source_pins:
                source = self.schedule_sources.get((schedule_id, pin.source_id))
                if source is None:
                    raise ValueError(
                        "Frozen source requires trusted host registration."
                    )
                cursor = next(
                    c for c in record.state.cursors if c.source_id == pin.source_id
                )

                def read(
                    source: LocalResultSource = source,
                    after_sequence: int = cursor.sequence,
                ) -> LocalResultBatch:
                    self._qualified_source(record, source)
                    raw = canonical_bytes(source.events(after_sequence))
                    if len(raw) > 32_000:
                        raise ValueError("Local result batch exceeds its byte limit.")
                    batch = LocalResultBatch.model_validate_json(raw)
                    self._qualified_source(record, source)
                    return batch

                batch = self.schedule_reads.call(read)
                for event in batch.events:
                    if (
                        event.source_id != pin.source_id
                        or event.kind != pin.kind
                        or event.binding != record.state.spec.binding
                    ):
                        raise ValueError(
                            "Local result batch escapes its frozen source."
                        )
                for event in sorted(batch.events, key=lambda e: e.sequence):
                    if (
                        event.sequence <= cursor.sequence
                        or event.event_id in cursor.recent_ids
                    ):
                        continue
                    self.admit_schedule(
                        schedule_id,
                        expected_revision=expected_revision,
                        event=event,
                        allow_dispatch=False,
                    )
                    return True
            self.schedule_reads.check()
            if self.state.revision != expected_revision:
                raise ValueError("Local result inspection raced with parent mutation.")
            return False

    def _schedule_record(self, schedule_id: str) -> StoredSchedule:
        record = next(
            (
                s
                for s in self.state.schedules
                if s.state.spec.schedule_id == schedule_id
            ),
            None,
        )
        if record is None:
            raise ValueError("Schedule is not retained in this session.")
        return record

    def _schedule_gate(
        self, record: StoredSchedule, *, recovery: bool = False
    ) -> WakeupGate:
        spec = record.state.spec
        goal = self.current_goal
        if recovery:
            binding = spec.binding
        else:
            if self.schedule_observer is None or self.task_scope is not None:
                raise ValueError(
                    "Recorded scheduling requires a trusted scope observer; "
                    "live task scheduling remains gated."
                )
            binding = ScheduleBinding.model_validate_json(
                self.read_schedule_binding(spec).model_dump_json()
            )
            if (
                binding.owner_uid != self.state.owner_uid
                or binding.session_id != self.state.session_id
                or binding.workspace_sha256 != digest(self.state.workspace.encode())
                or goal is None
                or binding.goal_id != goal.goal_id
                or binding.goal_definition_sha256 != goal.definition.sha256
            ):
                raise ValueError(
                    "Current schedule owner/session/workspace/goal differs."
                )
        return WakeupGate(
            binding=binding,
            goal_status="paused" if goal is None else goal.status,
            aggregate_ledger=(
                ResourceLedger()
                if goal is None
                else scheduled_goal_exposure(self.state, goal.goal_id)
            ),
            aggregate_ceiling=spec.ceiling if goal is None else goal.definition.ceiling,
            safe_boundary=not self._busy
            and not self._side_busy
            and not any(e.status == "running" for e in self.state.entries)
            and (goal is None or not goal.reservations and not goal.evaluating_sha256),
            user_pending=any(e.status == "queued" for e in self.state.entries),
            task_pending=any(e.status == "queued" for e in self.state.entries),
            goal_expires_at=0.0
            if goal is None
            else goal.started_at + goal.definition.max_seconds,
        )

    def _schedule_commit(
        self,
        records: tuple[StoredSchedule, ...],
        *,
        expected_revision: int,
        entries: tuple[ConversationEntry | ArchivedConversationEntry, ...]
        | None = None,
    ) -> None:
        self.schedule_reads.check()
        if self.state.revision != expected_revision:
            raise ValueError("Schedule admission raced with a session revision change.")
        self._commit(
            validate_runtime_state(
                self.state.model_copy(
                    update={
                        "schedules": records,
                        "entries": self.state.entries if entries is None else entries,
                        "revision": expected_revision + 1,
                    }
                )
            )
        )

    def add_schedule(
        self, spec: InertScheduleSpec, *, expected_revision: int
    ) -> StoredSchedule:
        with self._schedule_lock, self.schedule_reads.operation():
            spec = InertScheduleSpec.model_validate_json(spec.model_dump_json())
            if (
                self.state.revision != expected_revision
                or len(self.state.schedules) >= 8
                or any(
                    s.state.spec.schedule_id == spec.schedule_id
                    for s in self.state.schedules
                )
            ):
                raise ValueError(
                    "Schedule capacity, identity or source revision is invalid."
                )
            record = StoredSchedule(
                state=create_inert_schedule(spec, now=self.goal_clock())
            )
            gate = self._schedule_gate(record)
            if (
                gate.binding != spec.binding
                or gate.goal_status != "working"
                or gate.aggregate_ledger.uncertain_effects
            ):
                raise ValueError(
                    "Schedule requires a current working goal and trusted binding."
                )
            if spec.expires_at > gate.goal_expires_at or any(
                getattr(spec.ceiling, key) > getattr(gate.aggregate_ceiling, key)
                for key in ResourceCeiling.model_fields
            ):
                raise ValueError(
                    "Schedule cannot enlarge the goal lifetime or resource ceilings."
                )
            record = record.model_copy(
                update={
                    "state": record.state.model_copy(
                        update={"aggregate_exposure": gate.aggregate_ledger}
                    )
                }
            )
            if self._schedule_gate(record).binding != gate.binding:
                raise ValueError("Schedule inputs changed during creation.")
            self._schedule_commit(
                (*self.state.schedules, record), expected_revision=expected_revision
            )
            return record

    def admit_schedule(
        self,
        schedule_id: str,
        *,
        expected_revision: int,
        event: LocalWakeupEvent | None = None,
        allow_dispatch: bool = True,
    ) -> str | None:
        """Explicit host tick only. One commit contains both intent and queue entry."""
        from mos_eisley.conversation_context_preview import preview_context

        with self._schedule_lock, self.schedule_reads.operation():
            if self.state.revision != expected_revision:
                raise ValueError("Schedule admission source revision is stale.")
            record = self._schedule_record(schedule_id)
            gate = self._schedule_gate(record)
            if allow_dispatch:
                self._validate_schedule_sources(record)
            now = self.goal_clock()
            observed = observe_timer(record.state, now=now)
            if gate.binding != record.state.spec.binding:
                observed = observed.model_copy(
                    update={
                        "status": "blocked",
                        "reason": "Current revision/policy differs from the schedule.",
                    }
                )
            if event is not None:
                event = LocalWakeupEvent.model_validate_json(event.model_dump_json())
                spec = record.state.spec
                if (
                    event.binding != spec.binding
                    or event.source_id not in spec.local_sources
                ):
                    raise ValueError("Local event escapes the frozen source scope.")
                cursor = next(
                    c for c in observed.cursors if c.source_id == event.source_id
                )
                duplicate = (
                    event.sequence <= cursor.sequence
                    or event.event_id in cursor.recent_ids
                )
                if not spec.local_source_pins:
                    validator = self.schedule_event_validator
                    if validator is None:
                        raise ValueError("No trusted committed-result validator.")
                    self.schedule_reads.call(lambda: validator(event))
                if (
                    not duplicate
                    and observed.status == "active"
                    and observed.accepted_events < 64
                ):
                    source = self.schedule_sources.get((schedule_id, event.source_id))
                    if spec.local_source_pins:
                        if source is None:
                            raise ValueError("Frozen source is not registered.")

                        def validate() -> None:
                            auth = self._qualified_source(record, source)
                            if event.kind != auth.kind:
                                raise ValueError("Local source kind differs.")
                            source.validate(event)
                            self._qualified_source(record, source)

                        self.schedule_reads.call(validate)
                observed = observe_local_event(observed, event, now=now)
            reserved = observed
            entries = self.state.entries
            operation = None
            if (
                observed.status == "active"
                and allow_dispatch
                and gate.safe_boundary
                and not gate.user_pending
                and not gate.task_pending
                and (observed.pending_timer or observed.pending_events)
            ):
                entry = ConversationEntry(
                    text=observed.spec.prompt,
                    goal_id=observed.spec.binding.goal_id,
                    goal_definition_sha256=observed.spec.binding.goal_definition_sha256,
                    interaction_mode=self.state.interaction_mode,
                )
                candidate = self.state.model_copy(update={"entries": (*entries, entry)})
                candidate = validate_runtime_state(candidate)
                preview = preview_context(candidate)
                if (
                    not preview.within_context_budget
                    or not preview.request.within_budget
                ):
                    raise ValueError(
                        "Scheduled request exceeds its exact context/input limit."
                    )
                if self.pending_limits is not None:
                    self.pending_limits.admit(entries, entry.text)
                if self.state.branch_budget is not None:
                    from mos_eisley.conversation_branch import BranchReservation
                    from mos_eisley.conversation_branch_controller import reserve

                    reserve(
                        self.state.branch_budget.model_copy(
                            update={"ledger": scheduled_branch_exposure(self.state)}
                        ),
                        BranchReservation(
                            operation_id=f"author-{len(entries)}",
                            input_bytes=preview.request.bytes,
                            output_bytes=preview.request.output_reserve_bytes,
                        ),
                    )
                reserved = reserve_wakeup(
                    observed,
                    gate,
                    ResourceLedger(
                        input_bytes=preview.request.bytes,
                        output_bytes=preview.request.output_reserve_bytes,
                        attempts=1,
                    ),
                    now=now,
                    request_sha256=preview.request.sha256,
                )
                if len(reserved.fires) > len(record.state.fires):
                    operation = reserved.fires[-1].operation_id
                    entries = (*entries, entry)
            if self._schedule_gate(record).binding != gate.binding:
                raise ValueError("Schedule inputs changed during admission.")
            links = (
                record.queue_bindings
                if operation is None
                else (
                    *record.queue_bindings,
                    ScheduleQueueBinding(
                        operation_id=operation, message_position=len(entries) - 1
                    ),
                )
            )
            updated = StoredSchedule(state=reserved, queue_bindings=links)
            # Expiry/revision changes also retire any still-undispatched old intent.
            if updated.state.status != "active":
                updated, entries = self._retire_queued_schedule(
                    updated, entries, "Schedule stopped before dispatch."
                )
            if updated == record and entries == self.state.entries:
                self.schedule_reads.check()
                if self.state.revision != expected_revision:
                    raise ValueError("Schedule admission revision changed.")
                return operation
            self._schedule_commit(
                tuple(updated if s == record else s for s in self.state.schedules),
                expected_revision=expected_revision,
                entries=entries,
            )
            return operation

    def _retire_queued_schedule(
        self,
        record: StoredSchedule,
        entries: tuple[ConversationEntry | ArchivedConversationEntry, ...],
        reason: str,
    ) -> tuple[
        StoredSchedule, tuple[ConversationEntry | ArchivedConversationEntry, ...]
    ]:
        values = list(entries)
        state = record.state
        for link in record.queue_bindings:
            if values[link.message_position].status == "queued":
                state = skip_wakeup(state, link.operation_id, reason=reason)
                values[link.message_position] = values[
                    link.message_position
                ].model_copy(update={"status": "cancelled"})
        return record.model_copy(update={"state": state}), tuple(values)

    def cancel_schedule(self, schedule_id: str, *, expected_revision: int) -> None:
        with self._schedule_lock:
            record = self._schedule_record(schedule_id)
            updated = record.model_copy(
                update={
                    "state": record.state.model_copy(
                        update={
                            "status": "cancelled",
                            "pending_timer": False,
                            "pending_events": 0,
                            "reason": "Cancelled; existing exposure retained.",
                        }
                    )
                }
            )
            updated, entries = self._retire_queued_schedule(
                updated, self.state.entries, "Cancelled before dispatch."
            )
            self._schedule_commit(
                tuple(updated if s == record else s for s in self.state.schedules),
                expected_revision=expected_revision,
                entries=entries,
            )

    def set_schedule_cadence(
        self, schedule_id: str, interval_seconds: int, *, expected_revision: int
    ) -> None:
        """Trusted host changes only a frozen dynamic schedule's bounded cadence."""
        with self._schedule_lock, self.schedule_reads.operation():
            record = self._schedule_record(schedule_id)
            gate = self._schedule_gate(record)
            if (
                gate.binding != record.state.spec.binding
                or gate.goal_status != "working"
                or gate.aggregate_ledger.uncertain_effects
            ):
                raise ValueError("Cadence change requires the current working scope.")
            updated = record.model_copy(
                update={
                    "state": change_cadence(
                        record.state, interval_seconds, now=self.goal_clock()
                    )
                }
            )
            if self._schedule_gate(record).binding != gate.binding:
                raise ValueError("Schedule inputs changed during cadence adjustment.")
            self._schedule_commit(
                tuple(updated if s == record else s for s in self.state.schedules),
                expected_revision=expected_revision,
            )

    def pause_schedule(
        self, schedule_id: str, *, expected_revision: int, reason: str
    ) -> None:
        """Host suspension retains running/uncertain work and all exposure."""
        with self._schedule_lock:
            if self.state.revision != expected_revision:
                raise ValueError("Schedule suspension source revision is stale.")
            record = self._schedule_record(schedule_id)
            if record.state.status != "active":
                return
            updated = record.model_copy(
                update={
                    "state": record.state.model_copy(
                        update={"status": "paused", "reason": reason}
                    )
                }
            )
            updated, entries = self._retire_queued_schedule(
                updated, self.state.entries, reason
            )
            self._schedule_commit(
                tuple(updated if s == record else s for s in self.state.schedules),
                expected_revision=expected_revision,
                entries=entries,
            )

    def resume_schedule(self, schedule_id: str, *, expected_revision: int) -> None:
        if self.schedule_reads.blocked:
            self.reset_schedule_handlers()
        with self._schedule_lock, self.schedule_reads.operation():
            record = self._schedule_record(schedule_id)
            self._validate_schedule_sources(record)
            updated = record.model_copy(
                update={
                    "state": resume_schedule(
                        record.state, self._schedule_gate(record), now=self.goal_clock()
                    )
                }
            )
            self._schedule_commit(
                tuple(updated if s == record else s for s in self.state.schedules),
                expected_revision=expected_revision,
            )

    def schedule_for_position(self, position: int) -> StoredSchedule | None:
        return next(
            (
                s
                for s in self.state.schedules
                if any(b.message_position == position for b in s.queue_bindings)
            ),
            None,
        )

    def _schedule_transitions(
        self, entries: tuple[ConversationEntry | ArchivedConversationEntry, ...]
    ) -> tuple[
        tuple[StoredSchedule, ...],
        tuple[ConversationEntry | ArchivedConversationEntry, ...],
    ]:
        records = list(self.state.schedules)
        # Later user input invalidates earlier wakeup context atomically with admission.
        user_added = len(entries) > len(self.state.entries)
        for i, record in enumerate(records):
            if user_added:
                record, entries = self._retire_queued_schedule(
                    record,
                    entries,
                    "User input superseded the wakeup; revalidation required.",
                )
            state = record.state
            for link in record.queue_bindings:
                position = link.message_position
                old, entry = self.state.entries[position], entries[position]
                if (
                    old.status == "queued"
                    and entry.status == "cancelled"
                    and not user_added
                ):
                    state = skip_wakeup(
                        state,
                        link.operation_id,
                        reason="Undispatched queue work cancelled.",
                    )
                elif old.status == "running" and entry.status in {
                    "completed",
                    "failed",
                    "cancelled",
                    "interrupted",
                }:
                    if (
                        entry.status == "completed"
                        and entry.usage is not None
                        and entry.usage.unit == "bytes"
                    ):
                        state = complete_wakeup(
                            state,
                            link.operation_id,
                            ResourceLedger(
                                input_bytes=entry.usage.billed_input,
                                output_bytes=entry.usage.billed_output,
                                attempts=1,
                            ),
                            digest((entry.answer or "").encode()),
                        )
                    else:
                        state = recover_schedule(
                            state,
                            self._schedule_gate(record, recovery=True),
                            now=self.goal_clock(),
                        )
            records[i] = record.model_copy(update={"state": state})
        return tuple(records), entries

    def recover_schedules(self) -> None:
        if not self.state.schedules:
            return
        records: list[StoredSchedule] = []
        entries = self.state.entries
        for record in self.state.schedules:
            record, entries = self._retire_queued_schedule(
                record, entries, "Restart stopped known undispatched wakeup; no replay."
            )
            record = record.model_copy(
                update={
                    "state": recover_schedule(
                        record.state,
                        self._schedule_gate(record, recovery=True),
                        now=self.goal_clock(),
                    )
                }
            )
            records.append(record)
        if tuple(records) != self.state.schedules or entries != self.state.entries:
            self._schedule_commit(
                tuple(records), entries=entries, expected_revision=self.state.revision
            )

    def revalidate_schedule_dispatch(
        self, position: int, request_sha256: str | None = None
    ) -> bool:
        record = self.schedule_for_position(position)
        if record is None:
            return True
        revision = self.state.revision
        valid = False
        try:
            with self.schedule_reads.operation():
                gate = self._schedule_gate(record)
                self._validate_schedule_sources(record)
                link = next(
                    b for b in record.queue_bindings if b.message_position == position
                )
                fire = next(
                    f for f in record.state.fires if f.operation_id == link.operation_id
                )
                valid = (
                    self.state.revision == revision
                    and record.state.status == "active"
                    and fire.state == "reserved"
                    and gate.binding == record.state.spec.binding
                    and gate.goal_status == "working"
                    and not gate.aggregate_ledger.uncertain_effects
                    and self.goal_clock()
                    < min(record.state.spec.expires_at, gate.goal_expires_at)
                    and (
                        request_sha256 is None or request_sha256 == fire.request_sha256
                    )
                )
                self.schedule_reads.check()
        except (ValueError, OSError):
            valid = False
        if not valid and self.state.entries[position].status == "queued":
            updated, entries = self._retire_queued_schedule(
                record,
                self.state.entries,
                "Dispatch rejected stale inputs, stopped goal or expired schedule.",
            )
            self._schedule_commit(
                tuple(updated if s == record else s for s in self.state.schedules),
                expected_revision=self.state.revision,
                entries=entries,
            )
        return valid

    def can_dispatch(
        self, entry: ConversationEntry | ArchivedConversationEntry
    ) -> bool:
        if not super().can_dispatch(entry):
            return False
        position = next(
            (i for i, e in enumerate(self.state.entries) if e is entry), None
        )
        record = None if position is None else self.schedule_for_position(position)
        if record is None:
            return True
        return record.state.status == "active" and not any(
            e.status == "queued" and self.schedule_for_position(i) is None
            for i, e in enumerate(self.state.entries)
        )
