"""Explicit clocks/events and existing queue integration, without live scheduling."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from test_conversation import WaitingClient
from test_conversation_context import CapturingClient
from test_conversation_goal import definition

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.conversation_schedule import (
    InertScheduleSpec,
    InertScheduleState,
    LocalWakeupEvent,
    ScheduleBinding,
    WakeupGate,
    cancel_schedule,
    change_cadence,
    complete_wakeup,
    create_inert_schedule,
    observe_local_event,
    observe_timer,
    recover_schedule,
    reserve_wakeup,
    resume_schedule,
)
from mos_eisley.conversation_state import ConversationState
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.task_state import ResourceCeiling, ResourceLedger


def binding() -> ScheduleBinding:
    return ScheduleBinding(
        owner_uid=1,
        session_id="a" * 32,
        workspace_sha256="b" * 64,
        revision_sha256="c" * 64,
        policy_sha256="d" * 64,
        goal_id="goal",
        goal_definition_sha256="e" * 64,
        task_id="task",
    )


def spec() -> InertScheduleSpec:
    return InertScheduleSpec(
        schedule_id="schedule",
        binding=binding(),
        prompt="Inspect committed CI fixture",
        interval_seconds=10,
        minimum_interval_seconds=10,
        maximum_interval_seconds=10,
        expires_at=1000.0,
        maximum_fires=3,
        ceiling=ResourceCeiling(
            input_bytes=500000,
            output_bytes=64000,
            cost_microusd=0,
            attempts=3,
            correction_cycles=0,
            review_rounds=0,
        ),
        local_sources=("tests", "children"),
    )


def gate(state: InertScheduleState) -> WakeupGate:
    return WakeupGate(
        binding=state.spec.binding,
        goal_status="working",
        aggregate_ledger=ResourceLedger(),
        aggregate_ceiling=state.spec.ceiling,
        safe_boundary=True,
        user_pending=False,
        goal_expires_at=2000.0,
    )


REQUESTED = ResourceLedger(input_bytes=100, output_bytes=100, attempts=1)


def event(state: InertScheduleState, sequence: int = 1) -> LocalWakeupEvent:
    return LocalWakeupEvent(
        source_id="tests",
        event_id=f"event-{sequence}",
        sequence=sequence,
        binding=state.spec.binding,
        payload_sha256="f" * 64,
        payload_bytes=4000,
        kind="local_test",
    )


class QueueFixture:
    """Test-only host bridge; never a runtime dispatcher or independent work queue."""

    def __init__(self, chat: ConversationController, state: InertScheduleState):
        self.chat, self.state = chat, state
        self.persisted = canonical_bytes(state)

    def current_gate(self) -> WakeupGate:
        goal = self.chat.current_goal
        assert goal is not None
        current = self.state.spec.binding.model_copy(
            update={
                "owner_uid": self.chat.state.owner_uid,
                "session_id": self.chat.state.session_id,
                "workspace_sha256": digest(self.chat.state.workspace.encode()),
                "goal_id": goal.goal_id,
                "goal_definition_sha256": goal.definition.sha256,
            }
        )
        return WakeupGate(
            binding=current,
            goal_status=goal.status,
            aggregate_ledger=goal.ledger,
            aggregate_ceiling=goal.definition.ceiling,
            safe_boundary=not any(
                e.status == "running" for e in self.chat.state.entries
            )
            and not any(s.state == "running" for s in self.chat.state.sides)
            and not goal.reservations
            and not goal.evaluating_sha256,
            user_pending=any(e.status == "queued" for e in self.chat.state.entries),
            task_pending=self.chat.active_chat_index is not None,
            goal_expires_at=goal.started_at + goal.definition.max_seconds,
        )

    def persist(self, state: InertScheduleState) -> None:
        self.persisted = canonical_bytes(state)
        self.state = InertScheduleState.model_validate_json(self.persisted)

    def admit(self, now: float) -> str | None:
        current = self.current_gate()
        # Prospective request measurement uses only a copied fixture controller.
        if (
            current.safe_boundary
            and not current.user_pending
            and not current.task_pending
        ):
            candidate = ConversationController(
                self.chat.state,
                self.chat.cassette,
                lambda _: None,
                goal_clock=lambda: now,
            )
            candidate.submit(self.state.spec.prompt)
            preview = preview_context(candidate.state)
            requested = ResourceLedger(
                input_bytes=preview.request.bytes,
                output_bytes=preview.request.output_reserve_bytes,
                attempts=1,
            )
            request_sha256 = preview.request.sha256
        else:
            requested = REQUESTED
            request_sha256 = "1" * 64
        reserved = reserve_wakeup(
            self.state, current, requested, now=now, request_sha256=request_sha256
        )
        previous = len(self.state.fires)
        self.persist(reserved)  # Mandatory before enqueue: lost ack remains uncertain.
        if len(reserved.fires) == previous:
            return None
        self.chat.submit(reserved.spec.prompt)
        return reserved.fires[-1].operation_id


class InertScheduleTests(IsolatedAsyncioTestCase):
    def fresh(self) -> InertScheduleState:
        return create_inert_schedule(spec(), now=100.0)

    def reserve(
        self, state: InertScheduleState, now: float = 110.0
    ) -> InertScheduleState:
        return reserve_wakeup(
            state, gate(state), REQUESTED, now=now, request_sha256="1" * 64
        )

    def complete(self, state: InertScheduleState) -> InertScheduleState:
        return complete_wakeup(state, state.fires[-1].operation_id, REQUESTED, "a" * 64)

    def test_creation_is_inert_and_requires_bounded_explicit_scope(self) -> None:
        state = self.fresh()
        self.assertFalse(state.dispatch_authorized)
        self.assertEqual(state.ledger, ResourceLedger())
        self.assertEqual(state.fires, ())
        for updates in (
            {"prompt": " "},
            {"maximum_fires": 4},
            {"expires_at": 100.0},
            {"minimum_interval_seconds": 9},
            {"local_sources": ("tests", "tests")},
            {"ceiling": spec().ceiling.model_copy(update={"cost_microusd": 1})},
        ):
            with self.assertRaises(ValueError):
                create_inert_schedule(spec().model_copy(update=updates), now=100.0)

    def test_fixed_cadence_coalesces_missed_intervals_without_catchup(self) -> None:
        state = observe_timer(self.fresh(), now=109.0)
        self.assertFalse(state.pending_timer)
        state = observe_timer(state, now=900.0)
        self.assertTrue(state.pending_timer)
        self.assertEqual(state.next_due_at, 910.0)
        reserved = self.reserve(state, now=900.0)
        self.assertEqual(len(reserved.fires), 1)
        self.assertEqual(reserved.fires[0].notification_count, 1)
        self.assertEqual(self.reserve(reserved, now=900.0), reserved)

    def test_dynamic_intervals_disclose_changes_and_respect_bounds(self) -> None:
        dynamic = spec().model_copy(
            update={
                "cadence": "dynamic",
                "minimum_interval_seconds": 5,
                "maximum_interval_seconds": 30,
            }
        )
        state = create_inert_schedule(dynamic, now=100.0)
        state = change_cadence(state, 20, now=101.0)
        self.assertEqual(state.cadence_history, (10, 20))
        self.assertEqual(state.next_due_at, 121.0)
        self.assertFalse(observe_timer(state, now=120.0).pending_timer)
        self.assertTrue(observe_timer(state, now=121.0).pending_timer)
        for interval in (0, 4, 31):
            with self.assertRaises(ValueError):
                change_cadence(state, interval, now=102.0)
        with self.assertRaises(ValueError):
            change_cadence(self.fresh(), 10, now=100.0)

    def test_expiry_and_cancellation_never_fire(self) -> None:
        for state in (
            observe_timer(self.fresh(), now=1000.0),
            cancel_schedule(self.fresh()),
        ):
            later = reserve_wakeup(
                state, gate(state), REQUESTED, now=1100.0, request_sha256="1" * 64
            )
            self.assertEqual(later.fires, ())
            with self.assertRaises(ValueError):
                resume_schedule(later, gate(state), now=1100.0)

    def test_maximum_fires_and_schedule_resource_limits(self) -> None:
        state = self.fresh()
        for now in (110.0, 120.0, 130.0):
            state = self.complete(self.reserve(state, now))
        self.assertEqual(state.status, "exhausted")
        self.assertEqual(len(self.reserve(state, 140.0).fires), 3)
        small = spec().model_copy(
            update={"ceiling": spec().ceiling.model_copy(update={"input_bytes": 99})}
        )
        state = self.reserve(create_inert_schedule(small, now=100.0))
        self.assertEqual(state.status, "exhausted")
        self.assertEqual(state.ledger.attempts, 0)

    def test_task_budget_and_retained_exposure_survive_false_reset(self) -> None:
        state = self.reserve(self.fresh())
        state = self.complete(state)
        current = gate(state).model_copy(
            update={
                "aggregate_ceiling": spec().ceiling.model_copy(
                    update={"input_bytes": 150}
                )
            }
        )
        exhausted = reserve_wakeup(
            state, current, REQUESTED, now=120.0, request_sha256="1" * 64
        )
        self.assertEqual(exhausted.status, "exhausted")
        self.assertEqual(exhausted.ledger.input_bytes, 100)
        reset = state.model_copy(
            update={"ledger": ResourceLedger(), "aggregate_exposure": ResourceLedger()}
        )
        with self.assertRaisesRegex(ValueError, "reset"):
            observe_timer(reset, now=120.0)

    def test_safe_boundary_user_priority_and_no_overlap(self) -> None:
        state = observe_timer(self.fresh(), now=110.0)
        for update in (
            {"safe_boundary": False},
            {"user_pending": True},
            {"task_pending": True},
        ):
            delayed = reserve_wakeup(
                state,
                gate(state).model_copy(update=update),
                REQUESTED,
                now=110.0,
                request_sha256="1" * 64,
            )
            self.assertTrue(delayed.pending_timer)
            self.assertEqual(delayed.fires, ())
        reserved = self.reserve(state)
        delayed = self.reserve(reserved, 120.0)
        self.assertEqual(len(delayed.fires), 1)
        self.assertTrue(delayed.pending_timer)

    def test_stopped_or_uncertain_goal_cannot_be_resumed_by_wakeup(self) -> None:
        state = self.fresh()
        for status in (
            "paused",
            "cancelled",
            "completed",
            "blocked",
            "waiting",
            "stalled",
            "budget_exhausted",
        ):
            current = gate(state).model_copy(update={"goal_status": status})
            result = reserve_wakeup(
                state, current, REQUESTED, now=110.0, request_sha256="1" * 64
            )
            self.assertEqual(result.fires, ())
            with self.assertRaises(ValueError):
                resume_schedule(result, current, now=110.0)
        current = gate(state).model_copy(
            update={"aggregate_ledger": ResourceLedger(uncertain_effects=1)}
        )
        self.assertEqual(
            reserve_wakeup(
                state, current, REQUESTED, now=110.0, request_sha256="1" * 64
            ).status,
            "paused",
        )

    def test_cross_owner_scope_stale_revision_policy_and_goal_fail_closed(self) -> None:
        state = self.fresh()
        for update in (
            {"owner_uid": 2},
            {"session_id": "f" * 32},
            {"workspace_sha256": "f" * 64},
            {"revision_sha256": "f" * 64},
            {"policy_sha256": "f" * 64},
            {"goal_id": "other"},
            {"goal_definition_sha256": "f" * 64},
            {"task_id": "other"},
        ):
            foreign = state.spec.binding.model_copy(update=update)
            current = gate(state).model_copy(update={"binding": foreign})
            result = reserve_wakeup(
                state, current, REQUESTED, now=110.0, request_sha256="1" * 64
            )
            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.fires, ())
            with self.assertRaises(ValueError):
                observe_local_event(
                    state,
                    event(state).model_copy(update={"binding": foreign}),
                    now=101.0,
                )

    def test_duplicate_and_out_of_order_events_coalesce_without_payload_steering(
        self,
    ) -> None:
        state = observe_local_event(self.fresh(), event(self.fresh(), 2), now=101.0)
        before = canonical_bytes(state)
        for notification in (
            event(state, 2),
            event(state, 1),
            event(state, 3).model_copy(update={"event_id": "event-2"}),
        ):
            self.assertEqual(
                canonical_bytes(observe_local_event(state, notification, now=101.0)),
                before,
            )
        state = observe_local_event(state, event(state, 3), now=101.0)
        reserved = self.reserve(state, 110.0)
        self.assertEqual(reserved.fires[0].notification_count, 3)
        self.assertEqual(len(reserved.fires), 1)
        self.assertEqual(reserved.spec.prompt, spec().prompt)
        self.assertNotIn(b"payload_sha256", canonical_bytes(reserved))

    def test_event_flood_and_bounded_replay_window_survive_restart(self) -> None:
        state = self.fresh()
        for sequence in range(1, 1000):
            state = observe_local_event(state, event(state, sequence), now=101.0)
        self.assertEqual(state.accepted_events, 64)
        self.assertEqual(state.pending_events, 64)
        self.assertEqual(len(state.cursors[0].recent_ids), 16)
        self.assertEqual(state.cursors[0].sequence, 64)
        state = InertScheduleState.model_validate_json(canonical_bytes(state))
        self.assertEqual(observe_local_event(state, event(state, 1), now=101.0), state)
        self.assertLess(len(canonical_bytes(state)), 12000)
        with self.assertRaises(ValueError):
            observe_local_event(
                state,
                event(state).model_copy(update={"source_id": "external"}),
                now=101.0,
            )
        with self.assertRaises(ValueError):
            observe_local_event(
                state,
                event(state).model_copy(update={"payload_bytes": 4097}),
                now=101.0,
            )

    def test_backwards_and_nonfinite_clocks_fail_closed(self) -> None:
        state = observe_timer(self.fresh(), now=120.0)
        backwards = observe_timer(state, now=110.0)
        self.assertEqual(backwards.status, "paused")
        self.assertEqual(backwards.last_seen_at, 120.0)
        with self.assertRaises(ValueError):
            resume_schedule(backwards, gate(state), now=119.0)
        resumed = resume_schedule(backwards, gate(state), now=120.0)
        self.assertEqual(resumed.next_due_at, 130.0)
        for now in (float("nan"), float("inf"), -1.0):
            with self.assertRaises(ValueError):
                observe_timer(state, now=now)

    def test_restart_requires_revalidation_without_automatic_catchup(self) -> None:
        state = self.complete(self.reserve(self.fresh()))
        restored = recover_schedule(
            InertScheduleState.model_validate_json(canonical_bytes(state)),
            gate(state),
            now=500.0,
        )
        self.assertEqual(restored.status, "paused")
        self.assertEqual(restored.ledger, state.ledger)
        self.assertEqual(restored.next_due_at, 510.0)
        self.assertEqual(len(self.reserve(restored, 500.0).fires), 1)
        resumed = resume_schedule(restored, gate(state), now=500.0)
        self.assertFalse(resumed.pending_timer)
        self.assertEqual(len(self.reserve(resumed, 500.0).fires), 1)
        self.assertEqual(resumed.ledger, state.ledger)
        self.assertEqual(
            len(self.reserve(resumed, 510.0).fires), 2
        )  # One future interval, never a restart backlog.

    def test_lost_ack_and_cancelled_inflight_never_replay_or_refund(self) -> None:
        state = self.reserve(self.fresh())
        restored = recover_schedule(state, gate(state), now=120.0)
        self.assertEqual(restored.status, "uncertain")
        self.assertEqual(restored.ledger.attempts, 1)
        self.assertEqual(restored.ledger.input_bytes, 100)
        self.assertEqual(restored.ledger.uncertain_effects, 1)
        self.assertEqual(recover_schedule(restored, gate(state), now=130.0), restored)
        self.assertEqual(self.reserve(restored, 140.0).fires, restored.fires)
        with self.assertRaises(ValueError):
            resume_schedule(restored, gate(state), now=140.0)
        with self.assertRaises(ValueError):
            self.complete(restored)
        cancelled = cancel_schedule(state)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(cancelled.ledger, restored.ledger)
        self.assertEqual(cancel_schedule(cancelled), cancelled)

    def test_exact_acknowledgement_is_idempotent_and_overages_are_retained(
        self,
    ) -> None:
        state = self.reserve(self.fresh())
        completed = self.complete(state)
        self.assertEqual(self.complete(completed), completed)
        with self.assertRaises(ValueError):
            complete_wakeup(
                completed,
                completed.fires[-1].operation_id,
                REQUESTED.model_copy(update={"input_bytes": 101}),
                "a" * 64,
            )
        with self.assertRaises(ValueError):
            complete_wakeup(state, "f" * 64, REQUESTED, "a" * 64)
        overage = complete_wakeup(
            state,
            state.fires[-1].operation_id,
            REQUESTED.model_copy(update={"output_bytes": 70000}),
            "a" * 64,
        )
        self.assertEqual(overage.status, "exhausted")
        self.assertEqual(overage.ledger.output_bytes, 70000)

    def chat(
        self, root: Path, *, initialize_goal: bool = True
    ) -> ConversationController:
        cassette = AgentCassette(exchanges=(demo_cassette().exchanges[0],) * 16)
        chat = ConversationController(
            ConversationController.fresh(root, cassette),
            cassette,
            lambda _: None,
            goal_clock=lambda: 100.0,
        )
        if initialize_goal:
            chat.create_goal(definition())
        return chat

    def fixture(self, chat: ConversationController) -> QueueFixture:
        goal = chat.current_goal
        assert goal is not None
        current = binding().model_copy(
            update={
                "owner_uid": chat.state.owner_uid,
                "session_id": chat.state.session_id,
                "workspace_sha256": digest(chat.state.workspace.encode()),
                "goal_id": goal.goal_id,
                "goal_definition_sha256": goal.definition.sha256,
            }
        )
        selected = spec().model_copy(
            update={"binding": current, "ceiling": goal.definition.ceiling}
        )
        return QueueFixture(chat, create_inert_schedule(selected, now=100.0))

    async def test_existing_queue_prioritizes_user_steering_before_inert_wakeup(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            fixture = self.fixture(chat)
            chat.submit("Main user work")
            client = WaitingClient()
            task = asyncio.create_task(chat.step(client))
            await client.started.wait()
            try:
                chat.steer("User steering takes priority")
                self.assertIsNone(fixture.admit(110.0))
                self.assertEqual(len(chat.state.entries), 2)
                self.assertEqual(fixture.state.fires, ())
            finally:
                client.release.set()
                await task
            self.assertIsNone(fixture.admit(110.0))
            await chat.step(CapturingClient())
            operation = fixture.admit(110.0)
            self.assertIsNotNone(operation)
            self.assertEqual(chat.state.entries[-1].text, fixture.state.spec.prompt)
            self.assertEqual(chat.state.entries[-1].status, "queued")
            self.assertIsNone(fixture.admit(120.0))
            await chat.step(CapturingClient())
            usage = chat.state.entries[-1].usage
            admission = chat.state.entries[-1].request_admission
            assert admission is not None
            self.assertEqual(
                admission.request.sha256, fixture.state.fires[-1].request_sha256
            )
            assert usage is not None and operation is not None
            fixture.persist(
                complete_wakeup(
                    fixture.state,
                    operation,
                    ResourceLedger(
                        input_bytes=usage.billed_input,
                        output_bytes=usage.billed_output,
                        attempts=1,
                    ),
                    "a" * 64,
                )
            )
            self.assertEqual(chat.state.exchanges_consumed, 3)
            goal = chat.current_goal
            assert goal is not None
            self.assertEqual(goal.ledger.attempts, 3)

    async def test_storage_restart_retains_goal_and_schedule_uncertainty(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for kind in (ConversationStore, SQLiteConversationStore):
                chat = self.chat(root, initialize_goal=False)
                with kind(root / kind.__name__, chat.state.session_id, root) as store:
                    store.save(chat.state)
                    chat.save = store.save
                    chat.create_goal(definition())
                    fixture = self.fixture(chat)
                    operation = fixture.admit(110.0)
                    client = WaitingClient()
                    task = asyncio.create_task(chat.step(client))
                    await client.started.wait()
                    frozen = store.load()

                    # Simulate process loss before cancellation can be persisted.
                    def discard_save(_state: ConversationState) -> None:
                        return None

                    chat.save = discard_save
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    resumed = ConversationController(
                        frozen, chat.cassette, store.save, goal_clock=lambda: 120.0
                    )
                    self.assertEqual(resumed.state.entries[-1].status, "interrupted")
                    goal = resumed.current_goal
                    assert goal is not None
                    self.assertEqual(goal.ledger.attempts, 1)
                    self.assertEqual(goal.ledger.uncertain_effects, 1)
                    recovered = QueueFixture(
                        resumed,
                        InertScheduleState.model_validate_json(fixture.persisted),
                    )
                    recovered.persist(
                        recover_schedule(
                            recovered.state, recovered.current_gate(), now=120.0
                        )
                    )
                    self.assertEqual(recovered.state.fires[-1].operation_id, operation)
                    self.assertEqual(recovered.state.status, "uncertain")
                    before = canonical_bytes(resumed.state)
                    self.assertIsNone(recovered.admit(130.0))
                    self.assertEqual(canonical_bytes(resumed.state), before)
                    self.assertEqual(recovered.state.ledger.attempts, 1)

    def test_two_schedules_for_same_task_share_existing_queue_exclusion(self) -> None:
        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            first, second = self.fixture(chat), self.fixture(chat)
            second.persist(
                create_inert_schedule(
                    second.state.spec.model_copy(update={"schedule_id": "second"}),
                    now=100.0,
                )
            )
            self.assertIsNotNone(first.admit(110.0))
            self.assertIsNone(second.admit(110.0))
            self.assertEqual(len(chat.state.entries), 1)

    def test_persistence_failure_before_or_during_queue_admission_does_not_retry(
        self,
    ) -> None:
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            chat = self.chat(Path(directory))
            fixture = self.fixture(chat)
            with (
                patch.object(
                    fixture,
                    "persist",
                    side_effect=OSError("Fixture persistence failed"),
                ),
                self.assertRaises(OSError),
            ):
                fixture.admit(110.0)
            self.assertEqual(chat.state.entries, ())
            self.assertEqual(fixture.state.fires, ())

            def fail_save(_state: object) -> None:
                raise OSError("Queue acknowledgement lost")

            chat.save = fail_save
            with self.assertRaises(OSError):
                fixture.admit(110.0)
            self.assertEqual(len(fixture.state.fires), 1)
            self.assertEqual(chat.state.entries, ())
            self.assertTrue(chat.persistence_broken)
            restored = recover_schedule(
                InertScheduleState.model_validate_json(fixture.persisted),
                fixture.current_gate(),
                now=120.0,
            )
            self.assertEqual(restored.status, "uncertain")
            self.assertEqual(restored.ledger.attempts, 1)
            self.assertEqual(len(self.reserve(restored, 130.0).fires), 1)

    def test_no_paid_tool_or_review_allowance_can_enter_inert_admission(self) -> None:
        for updates in (
            {"attempts": 2},
            {"cost_microusd": 1},
            {"uncertain_effects": 1},
            {"correction_cycles": 1},
            {"review_rounds": 1},
        ):
            with self.assertRaises(ValueError):
                reserve_wakeup(
                    self.fresh(),
                    gate(self.fresh()),
                    REQUESTED.model_copy(update=updates),
                    now=110.0,
                    request_sha256="1" * 64,
                )
