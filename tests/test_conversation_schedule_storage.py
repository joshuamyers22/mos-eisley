"""Atomic schedule/queue storage, trusted dispatch and restart race boundaries."""

import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from test_conversation import WaitingClient
from test_conversation_context import CapturingClient
from test_conversation_goal import definition
from test_conversation_schedule import spec

from mos_eisley.conversation import (
    ConversationController,
    RuntimeConversationController,
)
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_schedule import (
    InertScheduleSpec,
    LocalWakeupEvent,
    ScheduleBinding,
)
from mos_eisley.conversation_state import ConversationState, WorkingConversationState
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore

BACKENDS = (ConversationStore, SQLiteConversationStore)


class ScheduleStorageTests(IsolatedAsyncioTestCase):
    def fresh(self, root: Path) -> tuple[ConversationController, list[float]]:
        clock = [100.0]
        cassette = AgentCassette(exchanges=(demo_cassette().exchanges[0],) * 16)
        chat = ConversationController(
            ConversationController.fresh(root, cassette),
            cassette,
            lambda _: None,
            goal_clock=lambda: clock[0],
            schedule_observer=lambda s: s.binding,
        )
        return chat, clock

    def add(self, chat: ConversationController) -> InertScheduleSpec:
        goal = chat.create_goal(definition())
        binding = spec().binding.model_copy(
            update={
                "owner_uid": chat.state.owner_uid,
                "session_id": chat.state.session_id,
                "workspace_sha256": digest(chat.state.workspace.encode()),
                "goal_id": goal.goal_id,
                "goal_definition_sha256": goal.definition.sha256,
            }
        )
        selected = spec().model_copy(
            update={"binding": binding, "ceiling": goal.definition.ceiling}
        )
        chat.add_schedule(selected, expected_revision=chat.state.revision)
        return selected

    @contextmanager
    def session(
        self, kind: type[ConversationStore] | type[SQLiteConversationStore]
    ) -> Generator[
        tuple[
            ConversationController,
            list[float],
            ConversationStore | SQLiteConversationStore,
        ]
    ]:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat, clock = self.fresh(root)
            with kind(root / "sessions", chat.state.session_id, root) as store:
                store.save(chat.state)
                chat.save = store.save
                self.add(chat)
                yield chat, clock, store

    def admit(
        self, chat: RuntimeConversationController, clock: list[float]
    ) -> str | None:
        clock[0] = 110.0
        return chat.admit_schedule("schedule", expected_revision=chat.state.revision)

    async def test_atomic_binding_roundtrip_and_measured_completion(self) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, clock, store):
                before = chat.state.revision
                operation = self.admit(chat, clock)
                self.assertIsNotNone(operation)
                self.assertEqual(chat.state.revision, before + 1)
                loaded = store.load()
                record = loaded.schedules[0]
                self.assertEqual(record.queue_bindings[0].operation_id, operation)
                self.assertEqual(record.queue_bindings[0].message_position, 0)
                self.assertEqual(loaded.entries[0].status, "queued")
                self.assertEqual(record.state.ledger.attempts, 1)
                client = CapturingClient()
                self.assertTrue(await chat.step(client))
                loaded = store.load()
                fire = loaded.schedules[0].state.fires[0]
                self.assertEqual(fire.state, "completed")
                self.assertEqual(
                    fire.request_sha256, digest(canonical_bytes(client.requests[0]))
                )
                self.assertEqual(loaded.goals[0].ledger.attempts, 1)

    async def test_late_user_input_atomically_supersedes_queued_wakeup(self) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, clock, store):
                self.admit(chat, clock)
                charge = chat.state.schedules[0].state.ledger
                chat.submit("User steering after schedule admission")
                loaded = store.load()
                self.assertEqual(
                    [e.status for e in loaded.entries], ["cancelled", "queued"]
                )
                self.assertEqual(loaded.schedules[0].state.fires[0].state, "skipped")
                self.assertEqual(loaded.schedules[0].state.ledger, charge)
                client = CapturingClient()
                await chat.step(client)
                self.assertIn(
                    "User steering after schedule admission", str(client.requests)
                )
                self.assertNotIn("Inspect committed CI fixture", str(client.requests))
                self.assertEqual(chat.state.exchanges_consumed, 1)

    async def test_dispatch_revalidates_workspace_policy_expiry_and_exact_request(
        self,
    ) -> None:
        for change in ("revision_sha256", "policy_sha256", "expiry", "memory"):
            for kind in BACKENDS:
                with self.session(kind) as (chat, clock, store):
                    self.admit(chat, clock)
                    if change == "expiry":
                        clock[0] = 1000.0
                    elif change == "memory":
                        chat.set_interaction_mode("plan")
                        # Changed base context must invalidate the pinned request.
                        from mos_eisley.conversation_memory import ConversationMemory

                        chat.refresh_memory(ConversationMemory(), chat.cassette)
                    else:

                        def observe(
                            s: InertScheduleSpec, key: str = change
                        ) -> ScheduleBinding:
                            return s.binding.model_copy(update={key: "f" * 64})

                        chat.schedule_observer = observe
                    client = CapturingClient()
                    self.assertFalse(await chat.step(client))
                    self.assertEqual(client.requests, [])
                    self.assertEqual(store.load().entries[0].status, "cancelled")
                    self.assertEqual(chat.state.exchanges_consumed, 0)

    async def test_cancel_after_running_reservation_stops_before_provider_call(
        self,
    ) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, clock, store):
                self.admit(chat, clock)
                client = CapturingClient()

                def cancel() -> None:
                    chat.cancel_schedule(
                        "schedule", expected_revision=chat.state.revision
                    )

                with self.assertRaises(ValueError):
                    await chat.step(client, on_started=cancel)
                self.assertEqual(client.requests, [])
                loaded = store.load()
                self.assertEqual(loaded.schedules[0].state.status, "cancelled")
                self.assertEqual(loaded.schedules[0].state.fires[0].state, "uncertain")
                self.assertEqual(loaded.goals[0].ledger.uncertain_effects, 1)

    async def test_cancellation_during_provider_keeps_late_result_and_stops_followups(
        self,
    ) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, clock, store):
                self.admit(chat, clock)
                client = WaitingClient()
                running = asyncio.create_task(chat.step(client))
                await client.started.wait()
                chat.cancel_schedule("schedule", expected_revision=chat.state.revision)
                client.release.set()
                await running
                self.assertEqual(store.load().entries[0].status, "completed")
                self.assertEqual(chat.state.schedules[0].state.status, "cancelled")
                clock[0] = 120.0
                self.assertIsNone(
                    chat.admit_schedule(
                        "schedule", expected_revision=chat.state.revision
                    )
                )
                self.assertEqual(len(chat.state.entries), 1)

    async def test_restart_running_work_retains_uncertainty_and_never_replays(
        self,
    ) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, clock, store):
                self.admit(chat, clock)
                client = WaitingClient()
                task = asyncio.create_task(chat.step(client))
                await client.started.wait()
                frozen = store.load()

                def discard(_state: ConversationState) -> None:
                    return None

                chat.save = discard
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                clock[0] = 120.0
                resumed = ConversationController(
                    frozen,
                    chat.cassette,
                    store.save,
                    goal_clock=lambda: clock[0],
                    schedule_observer=lambda s: s.binding,
                )
                state = store.load()
                self.assertEqual(state.entries[0].status, "interrupted")
                self.assertEqual(state.schedules[0].state.ledger.uncertain_effects, 1)
                self.assertEqual(state.goals[0].ledger.uncertain_effects, 1)
                charge = state.schedules[0].state.ledger
                again = ConversationController(
                    state,
                    chat.cassette,
                    store.save,
                    goal_clock=lambda: clock[0],
                    schedule_observer=lambda s: s.binding,
                )
                self.assertEqual(again.state.schedules[0].state.ledger, charge)
                self.assertFalse(await resumed.step(CapturingClient()))
                with self.assertRaises(ValueError):
                    again.resume_schedule(
                        "schedule", expected_revision=again.state.revision
                    )

    async def test_lost_save_ack_has_both_intent_and_queue_or_neither(self) -> None:
        for committed in (False, True):
            for kind in BACKENDS:
                with self.session(kind) as (chat, clock, store):
                    before = store.load()

                    def lose_ack(
                        state: ConversationState, did_commit: bool = committed
                    ) -> None:
                        if did_commit:
                            store.save(state)
                        raise OSError("Admission acknowledgement lost")

                    chat.save = lose_ack
                    with self.assertRaises(OSError):
                        self.admit(chat, clock)
                    saved = store.load()
                    self.assertEqual(len(saved.entries), int(committed))
                    self.assertEqual(
                        len(saved.schedules[0].state.fires), int(committed)
                    )
                    if not committed:
                        self.assertEqual(saved, before)
                    resumed = ConversationController(
                        saved,
                        chat.cassette,
                        store.save,
                        goal_clock=lambda: clock[0],
                        schedule_observer=lambda s: s.binding,
                    )
                    self.assertFalse(await resumed.step(CapturingClient()))
                    if committed:
                        self.assertEqual(resumed.state.entries[0].status, "cancelled")
                        self.assertEqual(
                            resumed.state.schedules[0].state.fires[0].state, "skipped"
                        )
                        self.assertEqual(
                            resumed.state.schedules[0].state.ledger.attempts, 1
                        )

    async def test_same_owner_concurrent_admissions_have_one_winner(self) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            self.add(chat)
            clock[0] = 110.0
            revision = chat.state.revision
            outcomes = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        chat.admit_schedule, "schedule", expected_revision=revision
                    )
                    for _ in range(2)
                ),
                return_exceptions=True,
            )
            self.assertEqual(sum(isinstance(o, str) for o in outcomes), 1)
            self.assertEqual(sum(isinstance(o, ValueError) for o in outcomes), 1)
            self.assertEqual(len(chat.state.entries), 1)
            self.assertEqual(chat.state.schedules[0].state.ledger.attempts, 1)

    async def test_concurrent_cancellation_and_admission_cannot_leave_runnable_work(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            self.add(chat)
            clock[0] = 110.0
            revision = chat.state.revision
            outcomes = await asyncio.gather(
                asyncio.to_thread(
                    chat.admit_schedule, "schedule", expected_revision=revision
                ),
                asyncio.to_thread(
                    chat.cancel_schedule, "schedule", expected_revision=revision
                ),
                return_exceptions=True,
            )
            self.assertEqual(sum(isinstance(o, ValueError) for o in outcomes), 1)
            if chat.state.schedules[0].state.status != "cancelled":
                chat.cancel_schedule("schedule", expected_revision=chat.state.revision)
            self.assertFalse(await chat.step(CapturingClient()))
            self.assertTrue(all(e.status == "cancelled" for e in chat.state.entries))

    async def test_lost_running_ack_preserves_goal_and_schedule_exposure_without_call(
        self,
    ) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, clock, store):
                self.admit(chat, clock)

                def lose_started_ack(state: ConversationState) -> None:
                    store.save(state)
                    if state.entries[0].status == "running":
                        raise OSError("Running acknowledgement lost")

                chat.save = lose_started_ack
                client = CapturingClient()
                with self.assertRaises(OSError):
                    await chat.step(client)
                self.assertEqual(client.requests, [])
                stored = store.load()
                self.assertEqual(stored.entries[0].status, "running")
                resumed = ConversationController(
                    stored,
                    chat.cassette,
                    store.save,
                    goal_clock=lambda: clock[0],
                    schedule_observer=lambda s: s.binding,
                )
                self.assertEqual(resumed.state.goals[0].ledger.uncertain_effects, 1)
                self.assertEqual(
                    resumed.state.schedules[0].state.ledger.uncertain_effects, 1
                )
                self.assertFalse(await resumed.step(client))

    def test_local_events_require_committed_source_validation_and_coalesce_while_busy(
        self,
    ) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, _clock, store):
                chat.submit("User work awaiting dispatch")
                binding = chat.state.schedules[0].state.spec.binding
                notification = LocalWakeupEvent(
                    source_id="tests",
                    event_id="result-1",
                    sequence=1,
                    binding=binding,
                    payload_sha256="f" * 64,
                    payload_bytes=20,
                    kind="local_test",
                )
                before = store.load()
                with self.assertRaises(ValueError):
                    chat.admit_schedule(
                        "schedule",
                        expected_revision=chat.state.revision,
                        event=notification,
                    )
                self.assertEqual(store.load(), before)

                def validate(event: LocalWakeupEvent) -> None:
                    if event.payload_sha256 != "f" * 64:
                        raise ValueError("Result is not committed")

                chat.schedule_event_validator = validate
                for _ in range(2):
                    self.assertIsNone(
                        chat.admit_schedule(
                            "schedule",
                            expected_revision=chat.state.revision,
                            event=notification,
                        )
                    )
                state = store.load().schedules[0].state
                self.assertEqual(state.pending_events, 1)
                self.assertEqual(state.accepted_events, 1)
                self.assertEqual(state.fires, ())
                with self.assertRaises(ValueError):
                    chat.admit_schedule(
                        "schedule",
                        expected_revision=chat.state.revision,
                        event=notification.model_copy(
                            update={"payload_sha256": "a" * 64}
                        ),
                    )

    def test_missing_scope_port_cross_owner_and_stale_sources_fail_before_creation(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat, _clock = self.fresh(Path(directory))
            selected = self.add(chat).model_copy(update={"schedule_id": "second"})
            before = chat.state

            def foreign_owner(s: InertScheduleSpec) -> ScheduleBinding:
                return s.binding.model_copy(
                    update={"owner_uid": s.binding.owner_uid + 1}
                )

            for observer in (
                None,
                foreign_owner,
            ):
                chat.schedule_observer = observer
                with self.assertRaises(ValueError):
                    chat.add_schedule(selected, expected_revision=chat.state.revision)
                self.assertEqual(chat.state, before)
            chat.schedule_observer = lambda s: s.binding
            with self.assertRaises(ValueError):
                chat.admit_schedule(
                    "schedule", expected_revision=chat.state.revision - 1
                )

    def test_cancelled_queue_restart_keeps_charges_without_new_uncertainty(
        self,
    ) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, clock, store):
                self.admit(chat, clock)
                chat.cancel_schedule("schedule", expected_revision=chat.state.revision)
                saved = store.load()
                resumed = ConversationController(
                    saved,
                    chat.cassette,
                    store.save,
                    goal_clock=lambda: clock[0],
                    schedule_observer=lambda s: s.binding,
                )
                self.assertEqual(resumed.state, saved)
                self.assertEqual(saved.schedules[0].state.ledger.attempts, 1)
                self.assertEqual(saved.schedules[0].state.ledger.uncertain_effects, 0)

    def test_revalidated_resume_cannot_erase_retained_queue_charges(self) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, clock, store):
                self.admit(chat, clock)
                charge = chat.state.schedules[0].state.ledger
                saved = store.load()
                resumed = ConversationController(
                    saved,
                    chat.cassette,
                    store.save,
                    goal_clock=lambda: clock[0],
                    schedule_observer=lambda s: s.binding,
                )
                self.assertEqual(resumed.state.schedules[0].state.ledger, charge)
                resumed.goal_control("pause")
                with self.assertRaises(ValueError):
                    resumed.resume_schedule(
                        "schedule", expected_revision=resumed.state.revision
                    )
                resumed.goal_control("resume")
                resumed.resume_schedule(
                    "schedule", expected_revision=resumed.state.revision
                )
                clock[0] = 120.0
                operation = resumed.admit_schedule(
                    "schedule", expected_revision=resumed.state.revision
                )
                self.assertIsNotNone(operation)
                self.assertEqual(resumed.state.schedules[0].state.ledger.attempts, 2)
                self.assertEqual(
                    resumed.state.schedules[0].queue_bindings[-1].message_position, 1
                )

    def test_store_lock_denies_competing_admission_and_restart_owners(self) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, clock, store):
                self.admit(chat, clock)
                with self.assertRaises(BlockingIOError):
                    kind(
                        Path(store.workspace).parent
                        / Path(store.workspace).name
                        / "sessions",
                        chat.state.session_id,
                        Path(chat.state.workspace),
                    )

    def test_tampered_duplicate_or_missing_queue_bindings_fail_closed(self) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, clock, _store):
                self.admit(chat, clock)
                record = chat.state.schedules[0]
                for updates in (
                    {"entries": ()},
                    {"schedules": (record, record)},
                    {
                        "entries": (
                            chat.state.entries[0].model_copy(
                                update={"text": "Other task"}
                            ),
                        )
                    },
                    {"schedules": (record.model_copy(update={"queue_bindings": ()}),)},
                ):
                    invalid = chat.state.model_copy(update=updates)
                    with self.assertRaises(ValueError):
                        ConversationState.model_validate_json(invalid.model_dump_json())

    async def test_sqlite_working_state_keeps_archived_history_and_schedule_binding(
        self,
    ) -> None:
        with self.session(SQLiteConversationStore) as (chat, clock, store):
            assert isinstance(store, SQLiteConversationStore)
            chat.submit("Earlier work")
            await chat.step(CapturingClient())
            working = store.load_working()
            assert isinstance(working, WorkingConversationState)
            runtime = ConversationController(
                working,
                chat.cassette,
                store.save_working,
                load_entry=store.load_working_entry,
                goal_clock=lambda: clock[0],
                schedule_observer=lambda s: s.binding,
            )
            runtime.resume_schedule(
                "schedule", expected_revision=runtime.state.revision
            )
            self.admit(runtime, clock)
            await runtime.step(CapturingClient())
            loaded = store.load_working()
            self.assertEqual(loaded.schedules[0].queue_bindings[0].message_position, 1)
            self.assertEqual(loaded.schedules[0].state.fires[0].state, "completed")
