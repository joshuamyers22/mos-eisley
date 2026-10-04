"""Authorized committed sources, event bounds and durable failure boundaries."""

import json
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest import IsolatedAsyncioTestCase

from test_conversation_agents import RetainedChildren
from test_conversation_context import CapturingClient
from test_conversation_goal import definition
from test_conversation_schedule import spec

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_agents import AgentInspectionScope, AgentReportReference
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_goal import GoalJob, GoalTestReceipt
from mos_eisley.conversation_schedule import InertScheduleSpec
from mos_eisley.conversation_schedule_driver import ActiveSessionTimers
from mos_eisley.conversation_schedule_handlers import ScheduleHandlerError
from mos_eisley.conversation_schedule_sources import (
    CommittedChildResults,
    CommittedTestResults,
    LocalResultAuthorization,
    LocalResultBatch,
    notification,
)
from mos_eisley.conversation_state import ConversationState
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore

BACKENDS = (ConversationStore, SQLiteConversationStore)


class SourceTests(IsolatedAsyncioTestCase):
    def fresh(self, root: Path, *, goal: bool = True) -> ConversationController:
        cassette = demo_cassette()
        chat = ConversationController(
            ConversationController.fresh(root, cassette),
            cassette,
            lambda _: None,
            goal_clock=lambda: 100.0,
            schedule_observer=lambda s: s.binding,
            schedule_handler_timeout=0.1,
        )
        if goal:
            chat.create_goal(definition())
        return chat

    def selected(self, chat: ConversationController) -> InertScheduleSpec:
        goal = chat.current_goal
        assert goal is not None
        binding = spec().binding.model_copy(
            update={
                "owner_uid": chat.state.owner_uid,
                "session_id": chat.state.session_id,
                "workspace_sha256": digest(chat.state.workspace.encode()),
                "goal_id": goal.goal_id,
                "goal_definition_sha256": goal.definition.sha256,
            }
        )
        return spec().model_copy(
            update={"binding": binding, "ceiling": goal.definition.ceiling}
        )

    def child(
        self, chat: ConversationController
    ) -> tuple[CommittedChildResults, RetainedChildren]:
        selected = self.selected(chat)
        binding = selected.binding
        retained = RetainedChildren(
            AgentInspectionScope(
                owner_uid=binding.owner_uid,
                parent_session_id=binding.session_id,
                workspace_sha256=binding.workspace_sha256,
            )
        )
        row = retained.view.children[0]
        assert row.assignment is not None
        assignment = row.assignment.model_copy(
            update={
                "workspace": chat.state.workspace,
                "parent_task_id": binding.task_id,
            }
        )
        retained.output = retained.output.model_copy(
            update={"assignment_sha256": assignment.sha256}
        )
        retained.reference = AgentReportReference(
            report_id=retained.output.report_id,
            assignment_sha256=assignment.sha256,
            sha256=digest(canonical_bytes(retained.output)),
            availability="available",
        )
        retained.view = retained.view.model_copy(
            update={
                "children": (
                    row.model_copy(
                        update={"assignment": assignment, "report": retained.reference}
                    ),
                    retained.view.children[1],
                )
            }
        )
        auth = LocalResultAuthorization(
            source_id="children",
            kind="local_child",
            binding=binding,
            child_id="child-1",
            child_assignment_sha256=assignment.sha256,
        )
        source = CommittedChildResults(auth, retained)
        selected = selected.model_copy(
            update={
                "local_sources": (auth.source_id,),
                "local_source_pins": (auth.pin,),
            }
        )
        chat.add_schedule(selected, expected_revision=chat.state.revision)
        chat.register_schedule_source(
            "schedule", source, expected_revision=chat.state.revision
        )
        return source, retained

    @contextmanager
    def session(
        self, kind: type[ConversationStore] | type[SQLiteConversationStore]
    ) -> Generator[
        tuple[
            ConversationController,
            CommittedChildResults,
            RetainedChildren,
            ConversationStore | SQLiteConversationStore,
        ]
    ]:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = self.fresh(root, goal=False)
            with kind(root / "sessions", chat.state.session_id, root) as store:
                store.save(chat.state)
                chat.save = store.save
                chat.create_goal(definition())
                source, retained = self.child(chat)
                yield chat, source, retained, store

    async def test_committed_child_wakes_owner_before_timer_and_late_user_wins(
        self,
    ) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, source, retained, store):
                before = chat.state
                self.assertEqual(len(source.events(0).events), 1)
                self.assertEqual(chat.state, before)
                timers = ActiveSessionTimers(chat, lambda _: None)
                timers.open()
                try:
                    self.assertEqual(len(timers.tick()), 1)
                    saved = store.load()
                    self.assertEqual(saved.schedules[0].state.accepted_events, 1)
                    self.assertEqual(saved.schedules[0].state.ledger.attempts, 1)
                    self.assertEqual(saved.entries[0].status, "queued")
                    chat.submit("User steering wins")
                    self.assertEqual(chat.state.entries[0].status, "cancelled")
                    client = CapturingClient()
                    await chat.step(client)
                    self.assertIn("User steering wins", str(client.requests))
                    self.assertNotIn(
                        "Inspect committed CI fixture", str(client.requests)
                    )
                    self.assertEqual(chat.state.schedules[0].state.ledger.attempts, 1)
                    self.assertGreater(retained.reads, 0)
                finally:
                    timers.close()

    async def test_child_boundaries_reject_without_reading_sealed_or_other_tasks(
        self,
    ) -> None:
        for change in (
            "sealed",
            "task",
            "workspace",
            "stale",
            "reassigned",
            "race",
            "digest",
            "partial",
        ):
            with TemporaryDirectory() as directory:
                chat = self.fresh(Path(directory))
                source, retained = self.child(chat)
                row = retained.view.children[0]
                assert row.assignment is not None
                if change == "sealed":
                    source.authorization = source.authorization.model_copy(
                        update={"child_id": "review-1"}
                    )
                elif change in {"task", "workspace", "reassigned"}:
                    key = {
                        "task": "parent_task_id",
                        "workspace": "workspace",
                        "reassigned": "objective",
                    }[change]
                    row = row.model_copy(
                        update={
                            "assignment": row.assignment.model_copy(
                                update={key: "different"}
                            )
                        }
                    )
                elif change == "stale":
                    row = row.model_copy(update={"assignment_current": False})
                elif change == "race":
                    retained.race = True
                elif change == "digest":
                    retained.output = retained.output.model_copy(
                        update={"summary": "Changed artifact"}
                    )
                else:
                    row = row.model_copy(
                        update={
                            "report": retained.reference.model_copy(
                                update={"availability": "partial"}
                            )
                        }
                    )
                    assert row.report is not None
                    retained.reference = row.report
                retained.view = retained.view.model_copy(
                    update={"children": (row, retained.view.children[1])}
                )
                before = chat.state
                if change == "partial":
                    self.assertEqual(source.events(0).events, ())
                else:
                    with self.assertRaises(ValueError):
                        source.events(0)
                if change in {"sealed", "task", "workspace", "stale", "reassigned"}:
                    self.assertEqual(retained.reads, 0)
                self.assertEqual(chat.state, before)

    async def test_failed_and_cancelled_children_are_notifications_not_success(
        self,
    ) -> None:
        for status in ("failed", "cancelled"):
            with TemporaryDirectory() as directory:
                chat = self.fresh(Path(directory))
                source, retained = self.child(chat)
                row = retained.view.children[0].model_copy(
                    update={"state": status, "verification": "failed"}
                )
                retained.view = retained.view.model_copy(update={"children": (row,)})
                event = source.events(0).events[0]
                self.assertTrue(event.payload_omitted)
                chat.admit_schedule(
                    "schedule",
                    event=event,
                    allow_dispatch=False,
                    expected_revision=chat.state.revision,
                )
                self.assertEqual(chat.state.schedules[0].state.pending_events, 1)
                goal = chat.current_goal
                assert goal is not None
                self.assertEqual(goal.completed_work, ())

    async def test_duplicates_out_of_order_and_source_change_do_not_charge_or_read(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.fresh(Path(directory))
            source, retained = self.child(chat)
            event = source.events(0).events[0]
            chat.admit_schedule(
                "schedule",
                event=event,
                allow_dispatch=False,
                expected_revision=chat.state.revision,
            )
            before, reads = chat.state, retained.reads
            for _ in range(20):
                chat.admit_schedule(
                    "schedule",
                    event=event,
                    allow_dispatch=False,
                    expected_revision=chat.state.revision,
                )
            self.assertEqual(chat.state, before)
            self.assertEqual(retained.reads, reads)
            # A new controller revision with identical output is not a new result.
            retained.view = retained.view.model_copy(update={"revision": 2})
            self.assertFalse(
                chat.poll_schedule_sources(
                    "schedule", expected_revision=chat.state.revision
                )
            )
            self.assertEqual(chat.state, before)
            source.authorization = source.authorization.model_copy(
                update={"child_assignment_sha256": "f" * 64}
            )
            with self.assertRaises(ValueError):
                chat.poll_schedule_sources(
                    "schedule", expected_revision=chat.state.revision
                )
            self.assertEqual(chat.state, before)

    async def test_hung_observer_validator_and_source_never_admit_late_results(
        self,
    ) -> None:
        for handler in ("observer", "validator", "source"):
            for kind in BACKENDS:
                with self.session(kind) as (chat, source, _retained, store):
                    release, done = Event(), Event()
                    original_events = source.events
                    event = source.events(0).events[0]
                    before = store.load()

                    def hung(release: Event = release, done: Event = done) -> None:
                        release.wait(2)
                        done.set()

                    if handler == "observer":
                        chat.schedule_observer = lambda s: (hung(), s.binding)[1]
                    elif handler == "validator":
                        source.validate = lambda event: hung()
                    else:
                        source.events = (
                            lambda after_sequence, original_events=original_events: (
                                hung(),
                                original_events(after_sequence),
                            )[1]
                        )
                    try:
                        with self.assertRaises(ScheduleHandlerError):
                            if handler == "source":
                                chat.poll_schedule_sources(
                                    "schedule", expected_revision=chat.state.revision
                                )
                            else:
                                chat.admit_schedule(
                                    "schedule",
                                    event=event,
                                    expected_revision=chat.state.revision,
                                )
                        self.assertEqual(store.load(), before)
                        with self.assertRaises(ScheduleHandlerError):
                            chat.reset_schedule_handlers()
                        chat.cancel_schedule(
                            "schedule", expected_revision=chat.state.revision
                        )
                        cancelled = store.load()
                    finally:
                        release.set()
                    self.assertTrue(done.wait(1))
                    self.assertEqual(store.load(), cancelled)
                    self.assertEqual(chat.state.entries, ())
                    self.assertEqual(chat.state.schedules[0].state.ledger.attempts, 0)

    async def test_cancellation_interrupts_handler_and_late_results_cannot_commit(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.fresh(Path(directory))
            source, _retained = self.child(chat)
            entered, release, ended = Event(), Event(), Event()
            errors: list[Exception] = []
            before = chat.state

            def hung(after_sequence: int) -> LocalResultBatch:
                entered.set()
                release.wait(2)
                return LocalResultBatch()

            source.events = hung

            def owner() -> None:
                try:
                    chat.poll_schedule_sources(
                        "schedule", expected_revision=chat.state.revision
                    )
                except Exception as error:
                    errors.append(error)
                finally:
                    ended.set()

            worker = Thread(target=owner)
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                chat.schedule_reads.cancel()
                self.assertTrue(ended.wait(0.5))
                self.assertIsInstance(errors[0], ScheduleHandlerError)
                self.assertEqual(chat.state, before)
            finally:
                release.set()
                worker.join(1)

    async def test_flood_is_bounded_and_oversized_batch_rejected_before_any_commit(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.fresh(Path(directory))
            source, _retained = self.child(chat)
            auth = source.authorization
            source.validate = lambda event: None
            for index in range(1, 81):
                event = notification(
                    auth, f"result-{index}", index, f"result {index}".encode()
                )
                chat.admit_schedule(
                    "schedule",
                    event=event,
                    allow_dispatch=False,
                    expected_revision=chat.state.revision,
                )
            state = chat.state.schedules[0].state
            self.assertEqual(state.accepted_events, 64)
            self.assertEqual(state.pending_events, 64)
            self.assertEqual(len(state.cursors[0].recent_ids), 16)
            self.assertEqual(state.fires, ())
        with TemporaryDirectory() as directory:
            chat = self.fresh(Path(directory))
            source, _retained = self.child(chat)
            source.events = lambda after_sequence: LocalResultBatch.model_construct(
                events=tuple(
                    notification(
                        source.authorization, f"result-{index}", index, b"result"
                    )
                    for index in range(1, 18)
                )
            )
            before = chat.state
            with self.assertRaises(ValueError):
                chat.poll_schedule_sources(
                    "schedule", expected_revision=chat.state.revision
                )
            self.assertEqual(chat.state, before)

    async def test_lost_event_and_queue_ack_restart_preserves_cursors_and_exposure(
        self,
    ) -> None:
        for phase in ("notification", "queue"):
            for kind in BACKENDS:
                with self.session(kind) as (chat, source, retained, store):
                    if phase == "queue":
                        chat.poll_schedule_sources(
                            "schedule", expected_revision=chat.state.revision
                        )

                    def lose_ack(state: ConversationState) -> None:
                        store.save(state)
                        raise OSError("lost acknowledgement")

                    chat.save = lose_ack
                    with self.assertRaises(OSError):
                        if phase == "notification":
                            chat.poll_schedule_sources(
                                "schedule", expected_revision=chat.state.revision
                            )
                        else:
                            chat.admit_schedule(
                                "schedule", expected_revision=chat.state.revision
                            )
                    loaded = store.load()
                    self.assertTrue(chat.persistence_broken)
                    self.assertEqual(loaded.schedules[0].state.accepted_events, 1)
                    charge = loaded.schedules[0].state.ledger
                    resumed = ConversationController(
                        loaded,
                        chat.cassette,
                        store.save,
                        goal_clock=lambda: 100,
                        schedule_observer=lambda s: s.binding,
                    )
                    self.assertEqual(resumed.state.schedules[0].state.status, "paused")
                    resumed.goal_control("resume")
                    resumed.register_schedule_source(
                        "schedule", source, expected_revision=resumed.state.revision
                    )
                    resumed.resume_schedule(
                        "schedule", expected_revision=resumed.state.revision
                    )
                    before = resumed.state
                    self.assertFalse(
                        resumed.poll_schedule_sources(
                            "schedule", expected_revision=resumed.state.revision
                        )
                    )
                    self.assertEqual(resumed.state, before)
                    self.assertEqual(resumed.state.schedules[0].state.ledger, charge)
                    self.assertFalse(await resumed.step(CapturingClient()))
                    if phase == "queue":
                        self.assertEqual(
                            resumed.state.schedules[0].state.fires[0].state, "skipped"
                        )
                        self.assertEqual(charge.attempts, 1)
                    self.assertGreater(retained.reads, 0)

    async def test_test_receipts_require_identity_and_acknowledged_job(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.fresh(Path(directory))
            selected = self.selected(chat)
            auth = LocalResultAuthorization(
                source_id="tests",
                kind="local_test",
                binding=selected.binding,
                operation_ids=("build",),
                test_workspace_sha256="a" * 64,
                test_inputs_sha256="b" * 64,
            )
            selected = selected.model_copy(
                update={"local_sources": ("tests",), "local_source_pins": (auth.pin,)}
            )
            chat.add_schedule(selected, expected_revision=chat.state.revision)
            goal = chat.current_goal
            assert goal is not None
            chat.register_goal_job(
                GoalJob(operation_id="build"),
                expected_definition=goal.definition.sha256,
            )
            receipt = GoalTestReceipt(
                operation_id="build",
                workspace_sha256="a" * 64,
                inputs_sha256="b" * 64,
                executed_tests=2,
                failed_tests=0,
            )
            raw = canonical_bytes(receipt)
            artifacts = {digest(raw): raw}
            source = CommittedTestResults(
                auth, lambda: chat.state, artifacts.__getitem__
            )
            chat.register_schedule_source(
                "schedule", source, expected_revision=chat.state.revision
            )
            self.assertEqual(source.events(0).events, ())
            timers = ActiveSessionTimers(chat, lambda _: None)
            timers.open()
            try:
                self.assertEqual(timers.tick(), ())
                self.assertEqual(chat.state.schedules[0].state.status, "active")
                self.assertGreater(timers.delay() or 0, 0)
                current = chat.current_goal
                assert current is not None
                report = current.jobs[0].model_copy(
                    update={"state": "passed", "result_sha256": digest(raw)}
                )
                revision = chat.state.revision + 1
                chat.report_goal_job(
                    goal.goal_id, report, expected_definition=goal.definition.sha256
                )
                current = chat.current_goal
                assert current is not None
                self.assertEqual(current.jobs[0].committed_revision, revision)
                self.assertEqual(source.events(0).events[0].sequence, revision)
                self.assertEqual(len(timers.tick()), 1)
                with self.assertRaises(ValueError):
                    chat.report_goal_job(
                        goal.goal_id,
                        report.model_copy(update={"committed_revision": revision + 1}),
                        expected_definition=goal.definition.sha256,
                    )
                artifacts[digest(raw)] = b"forged"
                with self.assertRaises(ValueError):
                    source.events(0)
            finally:
                timers.close()

    async def test_source_pins_missing_registration_and_stale_policy_fail_closed(
        self,
    ) -> None:
        for change in ("missing", "policy", "kind", "owner"):
            with TemporaryDirectory() as directory:
                chat = self.fresh(Path(directory))
                source, retained = self.child(chat)
                if change == "missing":
                    chat.schedule_sources.clear()
                elif change == "policy":
                    chat.schedule_observer = lambda s: s.binding.model_copy(
                        update={"policy_sha256": "f" * 64}
                    )
                else:
                    source.authorization = source.authorization.model_copy(
                        update={
                            "kind": "local_test" if change == "kind" else "local_child",
                            "binding": source.authorization.binding.model_copy(
                                update={
                                    "owner_uid": chat.state.owner_uid
                                    + (change == "owner")
                                }
                            ),
                        }
                    )
                before, reads = chat.state, retained.reads
                timers = ActiveSessionTimers(chat, lambda _: None)
                timers.open()
                try:
                    self.assertEqual(timers.tick(), ())
                    self.assertEqual(chat.state.schedules[0].state.status, "paused")
                    self.assertEqual(chat.state.entries, ())
                    self.assertEqual(
                        chat.state.schedules[0].state.ledger,
                        before.schedules[0].state.ledger,
                    )
                    self.assertEqual(retained.reads, reads)
                    with self.assertRaises(ValueError):
                        chat.resume_schedule(
                            "schedule", expected_revision=chat.state.revision
                        )
                finally:
                    timers.close()

    async def test_stale_parent_revision_during_validation_preserves_user_steering(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.fresh(Path(directory))
            source, _retained = self.child(chat)
            event = source.events(0).events[0]
            # Simulate concurrent steering while the read is active.
            source.validate = lambda event: chat.submit("New steering")
            with self.assertRaises(ValueError):
                chat.admit_schedule(
                    "schedule", event=event, expected_revision=chat.state.revision
                )
            self.assertEqual([e.text for e in chat.state.entries], ["New steering"])
            self.assertEqual(chat.state.schedules[0].state.fires, ())
            self.assertEqual(chat.state.schedules[0].state.accepted_events, 0)

    async def test_dispatch_timeout_skips_retained_intent_without_call_or_refund(
        self,
    ) -> None:
        for kind in BACKENDS:
            with self.session(kind) as (chat, source, _retained, store):
                event = source.events(0).events[0]
                chat.admit_schedule(
                    "schedule", event=event, expected_revision=chat.state.revision
                )
                charge = chat.state.schedules[0].state.ledger
                release = Event()
                chat.schedule_observer = lambda s, release=release: (
                    release.wait(2),
                    s.binding,
                )[1]
                client = CapturingClient()
                try:
                    self.assertFalse(await chat.step(client))
                    self.assertEqual(client.requests, [])
                    saved = store.load()
                    self.assertEqual(saved.schedules[0].state.fires[0].state, "skipped")
                    self.assertEqual(saved.schedules[0].state.ledger, charge)
                    self.assertEqual(saved.entries[0].status, "cancelled")
                finally:
                    release.set()

    async def test_cancellation_after_dispatch_guard_cannot_leave_a_true_verdict(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.fresh(Path(directory))
            source, _retained = self.child(chat)
            chat.admit_schedule(
                "schedule",
                event=source.events(0).events[0],
                expected_revision=chat.state.revision,
            )
            charge = chat.state.schedules[0].state.ledger

            def clock() -> float:
                chat.schedule_reads.cancel()
                return 100

            chat.goal_clock = clock
            self.assertFalse(chat.revalidate_schedule_dispatch(0))
            self.assertEqual(chat.state.entries[0].status, "cancelled")
            self.assertEqual(chat.state.schedules[0].state.ledger, charge)

    async def test_concurrent_poll_admission_and_cancellation_have_no_duplicate_intent(
        self,
    ) -> None:
        for action in ("poll", "cancel"):
            for kind in BACKENDS:
                with self.session(kind) as (chat, _source, _retained, store):
                    revision = chat.state.revision

                    entered, attempting = Event(), Event()
                    original = _source.events

                    def read(
                        after_sequence: int,
                        original: Callable[[int], LocalResultBatch] = original,
                        entered: Event = entered,
                        attempting: Event = attempting,
                    ) -> LocalResultBatch:
                        entered.set()
                        if not attempting.wait(1):
                            raise ValueError("Contender did not enter")
                        return original(after_sequence)

                    _source.events = read

                    def second(
                        action: str = action,
                        revision: int = revision,
                        entered: Event = entered,
                        attempting: Event = attempting,
                    ) -> bool:
                        if not entered.wait(1):
                            raise ValueError("Owner did not enter")
                        attempting.set()
                        try:
                            if action == "poll":
                                return chat.poll_schedule_sources(
                                    "schedule", expected_revision=revision
                                )
                            chat.cancel_schedule("schedule", expected_revision=revision)
                            return True
                        except ValueError:
                            return False

                    # SQLite writes stay on its connection's owning terminal thread.
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        contender = pool.submit(second)
                        self.assertTrue(
                            chat.poll_schedule_sources(
                                "schedule", expected_revision=revision
                            )
                        )
                        self.assertFalse(contender.result())
                    saved = store.load()
                    self.assertEqual(saved.revision, revision + 1)
                    self.assertLessEqual(saved.schedules[0].state.accepted_events, 1)
                    self.assertEqual(saved.entries, ())
                    self.assertEqual(saved.schedules[0].state.ledger.attempts, 0)

    async def test_invalid_test_receipts_and_unstamped_legacy_jobs_emit_nothing(
        self,
    ) -> None:
        for change in (
            "empty",
            "inputs",
            "workspace",
            "operation",
            "failures",
            "legacy",
        ):
            with TemporaryDirectory() as directory:
                chat = self.fresh(Path(directory))
                selected = self.selected(chat)
                goal = chat.current_goal
                assert goal is not None
                chat.register_goal_job(
                    GoalJob(operation_id="build", required=False),
                    expected_definition=goal.definition.sha256,
                )
                values = {
                    "operation_id": "build",
                    "workspace_sha256": "a" * 64,
                    "inputs_sha256": "b" * 64,
                    "executed_tests": 2,
                    "failed_tests": 0,
                }
                if change == "empty":
                    values["executed_tests"] = 0
                elif change in {"inputs", "workspace"}:
                    values[f"{change}_sha256"] = "f" * 64
                elif change == "operation":
                    values["operation_id"] = "other"
                elif change == "failures":
                    values["failed_tests"] = 1
                raw = json.dumps(values).encode()
                current = chat.current_goal
                assert current is not None
                job = current.jobs[0].model_copy(
                    update={"state": "passed", "result_sha256": digest(raw)}
                )
                chat.report_goal_job(
                    goal.goal_id, job, expected_definition=goal.definition.sha256
                )
                if change == "legacy":
                    current = chat.current_goal
                    assert current is not None
                    legacy = current.model_copy(
                        update={
                            "jobs": (
                                current.jobs[0].model_copy(
                                    update={"committed_revision": None}
                                ),
                            )
                        }
                    )
                    chat.state = chat.state.model_copy(update={"goals": (legacy,)})
                source = CommittedTestResults(
                    LocalResultAuthorization(
                        source_id="tests",
                        kind="local_test",
                        binding=selected.binding,
                        operation_ids=("build",),
                        test_workspace_sha256="a" * 64,
                        test_inputs_sha256="b" * 64,
                    ),
                    lambda chat=chat: chat.state,
                    lambda _, raw=raw: raw,
                )
                before = chat.state
                if change == "legacy":
                    self.assertEqual(source.events(0).events, ())
                else:
                    with self.assertRaises(ValueError):
                        source.events(0)
                self.assertEqual(chat.state, before)

    async def test_failed_test_result_is_committed_once_and_cannot_be_replaced(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat = self.fresh(Path(directory))
            selected = self.selected(chat)
            goal = chat.current_goal
            assert goal is not None
            chat.register_goal_job(
                GoalJob(operation_id="build", required=False),
                expected_definition=goal.definition.sha256,
            )
            raw = canonical_bytes(
                GoalTestReceipt(
                    operation_id="build",
                    workspace_sha256="a" * 64,
                    inputs_sha256="b" * 64,
                    executed_tests=2,
                    failed_tests=1,
                )
            )
            current = chat.current_goal
            assert current is not None
            report = current.jobs[0].model_copy(
                update={"state": "failed", "result_sha256": digest(raw)}
            )
            chat.report_goal_job(
                goal.goal_id, report, expected_definition=goal.definition.sha256
            )
            before = chat.state
            chat.report_goal_job(
                goal.goal_id, report, expected_definition=goal.definition.sha256
            )
            self.assertEqual(chat.state, before)
            source = CommittedTestResults(
                LocalResultAuthorization(
                    source_id="tests",
                    kind="local_test",
                    binding=selected.binding,
                    operation_ids=("build",),
                    test_workspace_sha256="a" * 64,
                    test_inputs_sha256="b" * 64,
                ),
                lambda: chat.state,
                lambda _: raw,
            )
            self.assertEqual(len(source.events(0).events), 1)
            with self.assertRaises(ValueError):
                chat.report_goal_job(
                    goal.goal_id,
                    report.model_copy(update={"result_sha256": "f" * 64}),
                    expected_definition=goal.definition.sha256,
                )

    def test_serialization_of_legacy_specs_and_jobs_preserves_frozen_hashes(
        self,
    ) -> None:
        selected = spec()
        raw = json.loads(selected.model_dump_json())
        self.assertNotIn("local_source_pins", raw)
        self.assertEqual(
            selected.sha256,
            digest(
                json.dumps(
                    raw, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                ).encode()
            ),
        )
        self.assertEqual(
            InertScheduleSpec.model_validate_json(json.dumps(raw)).sha256,
            selected.sha256,
        )
        self.assertNotIn("committed_revision", GoalJob(operation_id="old").model_dump())
        raw["local_source_pins"] = [
            {
                "source_id": "unknown",
                "kind": "local_child",
                "authorization_sha256": "a" * 64,
            }
        ]
        with self.assertRaises(ValueError):
            InertScheduleSpec.model_validate_json(json.dumps(raw))
