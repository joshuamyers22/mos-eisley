"""Active timer ownership, input priority, qualification and durable shutdown."""

import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from test_conversation import WaitingClient
from test_conversation_context import CapturingClient
from test_conversation_goal import definition
from test_conversation_loop import create
from test_conversation_tui import until

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_branch import BranchBudget
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.conversation_input import ConversationInput
from mos_eisley.conversation_loop_commands import loop_command, recorded_loop_observer
from mos_eisley.conversation_schedule import InertScheduleSpec, ScheduleBinding
from mos_eisley.conversation_schedule_driver import ActiveSessionTimers
from mos_eisley.conversation_state import ConversationEntry, ConversationState
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.ports import ModelClient
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.task_state import ResourceLedger


class TimerTests(IsolatedAsyncioTestCase):
    def fresh(
        self, root: Path, **limits: object
    ) -> tuple[ConversationController, list[float]]:
        clock = [100.0]
        cassette = demo_cassette()
        chat = ConversationController(
            ConversationController.fresh(root, cassette),
            cassette,
            lambda _: None,
            goal_clock=lambda: clock[0],
        )
        chat.schedule_observer = recorded_loop_observer(chat)
        chat.create_goal(definition())
        self.assertEqual(
            loop_command(chat, create(**limits), lambda _: None), "accepted"
        )
        return chat, clock

    def driver(self, chat: ConversationController) -> ActiveSessionTimers:
        timers = ActiveSessionTimers(chat, lambda _: None)
        timers.open()
        self.addCleanup(timers.close)
        return timers

    def use_client(self, chat: ConversationController, client: ModelClient) -> None:
        original = chat.step

        async def step(*, on_started: Callable[[], None] | None = None) -> bool:
            return await original(client, on_started=on_started)

        self.enterContext(patch.object(chat, "step", step))

    async def test_elapsed_intervals_coalesce_and_maximum_fires_stop(self) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            timers = self.driver(chat)
            self.assertEqual(timers.delay(), 1)
            self.assertEqual(timers.tick(), ())
            self.assertEqual(chat.state.entries, ())
            clock[0] = 200
            self.assertEqual(len(timers.tick()), 1)
            record = chat.state.schedules[0].state
            self.assertEqual(record.next_due_at, 210)
            self.assertEqual(len(record.fires), 1)
            revision = chat.state.revision
            self.assertEqual(timers.tick(), ())
            self.assertEqual(chat.state.revision, revision)
            self.assertEqual(timers.delay(), 1)
            await chat.step(CapturingClient())
            clock[0] = 210
            self.assertEqual(len(timers.tick()), 1)
            await chat.step(CapturingClient())
            self.assertEqual(chat.state.schedules[0].state.status, "exhausted")
            clock[0] = 250
            before = chat.state
            self.assertEqual(timers.tick(), ())
            self.assertIsNone(timers.delay())
            self.assertEqual(chat.state, before)

    async def test_busy_and_user_queue_defer_without_writes_or_overlap(self) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            timers = self.driver(chat)
            clock[0] = 200
            state = chat.state
            self.assertEqual(timers.tick(busy=True), ())
            self.assertEqual(timers.delay(busy=True), 1)
            self.assertEqual(chat.state, state)
            chat.submit("User steering first")
            state = chat.state
            self.assertEqual(timers.tick(), ())
            self.assertEqual(timers.delay(), 1)
            self.assertEqual(chat.state, state)
            client = WaitingClient()
            task = asyncio.create_task(chat.step(client))
            await client.started.wait()
            state = chat.state
            self.assertEqual(timers.tick(), ())
            self.assertEqual(chat.state, state)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            timers.tick()
            self.assertEqual(chat.state.schedules[0].state.status, "paused")
            self.assertEqual(len(chat.state.schedules[0].state.fires), 0)

    async def test_expiry_clock_changes_and_resource_limits_fail_closed(self) -> None:
        for change in ("expiry", "backwards", "nan", "input_limit"):
            with TemporaryDirectory() as directory:
                chat, clock = self.fresh(
                    Path(directory),
                    **({"input_bytes": 1} if change == "input_limit" else {}),
                )
                timers = self.driver(chat)
                timers.tick()
                if change == "expiry":
                    clock[0] = 401
                elif change == "backwards":
                    clock[0] = 99
                elif change == "nan":
                    clock[0] = float("nan")
                else:
                    clock[0] = 110
                self.assertEqual(timers.tick(), ())
                self.assertEqual(chat.state.entries, ())
                self.assertEqual(
                    chat.state.schedules[0].state.status,
                    "expired"
                    if change == "expiry"
                    else "exhausted"
                    if change == "input_limit"
                    else "paused",
                )
                self.assertIsNone(timers.delay())

    async def test_stale_bindings_and_observer_failure_pause_without_dispatch(
        self,
    ) -> None:
        for change in ("policy", "owner", "missing"):
            with TemporaryDirectory() as directory:
                chat, clock = self.fresh(Path(directory))
                timers = self.driver(chat)
                original = chat.schedule_observer
                assert original is not None
                if change == "missing":

                    def fail(_: InertScheduleSpec) -> ScheduleBinding:
                        raise OSError("scope unavailable")

                    chat.schedule_observer = fail
                else:
                    field = "policy_sha256" if change == "policy" else "owner_uid"
                    value = "f" * 64 if change == "policy" else chat.state.owner_uid + 1
                    chat.schedule_observer = (
                        lambda s, field=field, value=value, original=original: original(
                            s
                        ).model_copy(update={field: value})
                    )
                clock[0] = 110
                self.assertEqual(timers.tick(), ())
                self.assertEqual(chat.state.entries, ())
                self.assertIn(
                    chat.state.schedules[0].state.status, {"paused", "blocked"}
                )
                self.assertIsNone(timers.delay())

    async def test_single_owner_and_unqualified_controller_cannot_drive(self) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            timers = self.driver(chat)
            with self.assertRaises(ValueError):
                ActiveSessionTimers(chat, lambda _: None).open()
            timers.close()
            timers.close()
            self.assertFalse(chat.schedule_timer_active)
            chat.schedule_observer = None
            other = self.driver(chat)
            clock[0] = 110
            before = chat.state
            self.assertEqual(other.tick(), ())
            self.assertIsNone(other.delay())
            self.assertEqual(chat.state, before)
            self.assertFalse(chat.schedule_timer_active)

    async def test_close_retires_queued_intent_and_cold_restart_never_replays(
        self,
    ) -> None:
        for kind in (ConversationStore, SQLiteConversationStore):
            with TemporaryDirectory() as directory:
                chat, clock = self.fresh(Path(directory))
                # Initialize the store before installing the already constructed header.
                initial = ConversationController.fresh(Path(directory), chat.cassette)
                with kind(
                    Path(directory) / "sessions", initial.session_id, Path(directory)
                ) as store:
                    # Bind this controller to the store's freshly created session.
                    plain = ConversationController(
                        initial,
                        chat.cassette,
                        lambda _: None,
                        goal_clock=lambda clock=clock: clock[0],
                    )
                    store.save(plain.state)
                    plain.save = store.save
                    plain.schedule_observer = recorded_loop_observer(plain)
                    plain.create_goal(definition())
                    loop_command(plain, create(), lambda _: None)
                    timers = self.driver(plain)
                    clock[0] = 110
                    timers.tick()
                    ledger = plain.state.schedules[0].state.ledger
                    timers.close()
                    stored = store.load()
                    self.assertEqual(stored.entries[0].status, "cancelled")
                    self.assertEqual(stored.schedules[0].state.ledger, ledger)
                    resumed = ConversationController(
                        stored,
                        plain.cassette,
                        store.save,
                        goal_clock=lambda clock=clock: clock[0],
                    )
                    resumed.schedule_observer = recorded_loop_observer(resumed)
                    driver = self.driver(resumed)
                    clock[0] = 150
                    before = resumed.state
                    self.assertEqual(driver.tick(), ())
                    self.assertEqual(resumed.state, before)
                    self.assertEqual(
                        loop_command(resumed, "/loop resume watch", lambda _: None),
                        "accepted",
                    )
                    clock[0] = 160
                    self.assertEqual(len(driver.tick()), 1)
                    driver.close()
                    self.assertEqual(
                        resumed.state.schedules[0].state.ledger.attempts, 2
                    )

    async def test_terminal_drives_timer_and_preserves_post_admission_user_priority(
        self,
    ) -> None:
        for steering in (False, True):
            with TemporaryDirectory() as directory:
                chat, clock = self.fresh(Path(directory))
                client = CapturingClient()
                self.use_client(chat, client)
                queue: asyncio.Queue[ConversationInput] = asyncio.Queue()

                def emit(
                    event: dict[str, object],
                    chat: ConversationController = chat,
                    queue: asyncio.Queue[ConversationInput] = queue,
                    steering: bool = steering,
                ) -> None:
                    if (
                        steering
                        and event["type"] == "conversation.loop"
                        and len(chat.state.entries) == 1
                        and chat.state.entries[0].status == "queued"
                    ):
                        queue.put_nowait("User arrived after timer admission")

                with patch.object(ActiveSessionTimers, "poll_seconds", 0.01):
                    task = asyncio.create_task(terminal(chat, queue, emit))
                    try:
                        await until(lambda chat=chat: chat.schedule_timer_active)
                        clock[0] = 110
                        await until(lambda client=client: len(client.requests) == 1)
                        await until(lambda chat=chat: chat.schedule_timer_idle)
                        if steering:
                            self.assertEqual(chat.state.entries[0].status, "cancelled")
                            self.assertEqual(
                                chat.state.entries[1].text,
                                "User arrived after timer admission",
                            )
                            self.assertNotIn(
                                "Inspect committed CI results", str(client.requests)
                            )
                        else:
                            self.assertEqual(chat.state.entries[0].status, "completed")
                            self.assertEqual(
                                len(chat.state.schedules[0].state.fires), 1
                            )
                    finally:
                        queue.put_nowait("/quit")
                        await asyncio.wait_for(task, 3)
                    self.assertFalse(chat.schedule_timer_active)

    async def test_dynamic_cadence_is_bounded_persisted_and_driven(self) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(
                Path(directory),
                cadence="dynamic",
                minimum_interval_seconds=5,
                maximum_interval_seconds=20,
            )
            timers = self.driver(chat)
            chat.set_schedule_cadence(
                "watch", 15, expected_revision=chat.state.revision
            )
            self.assertEqual(chat.state.schedules[0].state.cadence_history, (10, 15))
            before = chat.state
            with self.assertRaises(ValueError):
                chat.set_schedule_cadence(
                    "watch", 21, expected_revision=chat.state.revision
                )
            with self.assertRaises(ValueError):
                chat.set_schedule_cadence("watch", 5, expected_revision=0)
            self.assertEqual(chat.state, before)
            clock[0] = 110
            self.assertEqual(timers.tick(), ())
            clock[0] = 115
            self.assertEqual(len(timers.tick()), 1)
            self.assertEqual(chat.state.schedules[0].state.next_due_at, 130)

    async def test_due_timer_yields_to_cancel_stop_and_eof(self) -> None:
        for control in ("/loop cancel watch", "/stop", None):
            with TemporaryDirectory() as directory:
                chat, clock = self.fresh(Path(directory))
                clock[0] = 110
                queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
                queue.put_nowait(control)
                if control is not None:
                    queue.put_nowait("/quit")
                await terminal(chat, queue, lambda _: None)
                self.assertEqual(chat.state.entries, ())
                self.assertEqual(chat.state.schedules[0].state.fires, ())
                self.assertFalse(chat.schedule_timer_active)

    async def test_composer_defers_timers_and_discard_reopens_safe_boundary(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            events: list[dict[str, object]] = []
            client = CapturingClient()
            self.use_client(chat, client)
            with patch.object(ActiveSessionTimers, "poll_seconds", 0.01):
                task = asyncio.create_task(terminal(chat, queue, events.append))
                try:
                    queue.put_nowait("/compose")
                    await until(
                        lambda: any(e["type"] == "composer.started" for e in events)
                    )
                    clock[0] = 200
                    await asyncio.sleep(0.04)
                    self.assertEqual(chat.state.entries, ())
                    queue.put_nowait("/discard")
                    await until(lambda: len(client.requests) == 1)
                finally:
                    queue.put_nowait("/quit")
                    await asyncio.wait_for(task, 3)
                self.assertFalse(chat.schedule_timer_active)

    async def test_pre_dispatch_failure_retires_intent_without_retry(self) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            client = CapturingClient()
            self.use_client(chat, client)

            def unavailable() -> None:
                raise ValueError("trusted memory validation failed")

            chat.validate_memory = unavailable
            with patch.object(ActiveSessionTimers, "poll_seconds", 0.01):
                task = asyncio.create_task(terminal(chat, queue, lambda _: None))
                try:
                    await until(lambda: chat.schedule_timer_active)
                    clock[0] = 110
                    await until(
                        lambda: (
                            bool(chat.state.entries)
                            and chat.state.entries[0].status == "cancelled"
                        )
                    )
                    record = chat.state.schedules[0].state
                    self.assertEqual(record.status, "paused")
                    self.assertEqual(record.fires[0].state, "skipped")
                    self.assertEqual(record.ledger.attempts, 1)
                    clock[0] = 200
                    await asyncio.sleep(0.04)
                    self.assertEqual(len(chat.state.schedules[0].state.fires), 1)
                    self.assertEqual(client.requests, [])
                finally:
                    queue.put_nowait("/quit")
                    await asyncio.wait_for(task, 3)

    async def test_lost_admission_ack_is_fatal_and_restart_skips_without_replay(
        self,
    ) -> None:
        for kind in (ConversationStore, SQLiteConversationStore):
            with TemporaryDirectory() as directory:
                root = Path(directory)
                cassette = demo_cassette()
                clock = [100.0]
                chat = ConversationController(
                    ConversationController.fresh(root, cassette),
                    cassette,
                    lambda _: None,
                    goal_clock=lambda clock=clock: clock[0],
                )
                with kind(root / "sessions", chat.state.session_id, root) as store:
                    store.save(chat.state)
                    chat.save = store.save
                    chat.schedule_observer = recorded_loop_observer(chat)
                    chat.create_goal(definition())
                    loop_command(chat, create(), lambda _: None)
                    driver = self.driver(chat)

                    def lost(
                        state: ConversationState,
                        store: ConversationStore | SQLiteConversationStore = store,
                    ) -> None:
                        store.save(state)
                        raise OSError("commit succeeded but acknowledgement was lost")

                    chat.save = lost
                    clock[0] = 110
                    with self.assertRaises(OSError):
                        driver.tick()
                    driver.close()
                    stored = store.load()
                    self.assertEqual(stored.entries[0].status, "queued")
                    ledger = stored.schedules[0].state.ledger
                    resumed = ConversationController(
                        stored,
                        cassette,
                        store.save,
                        goal_clock=lambda clock=clock: clock[0],
                    )
                    resumed.schedule_observer = recorded_loop_observer(resumed)
                    other = self.driver(resumed)
                    self.assertEqual(other.tick(), ())
                    self.assertEqual(resumed.state.entries[0].status, "cancelled")
                    self.assertEqual(resumed.state.schedules[0].state.ledger, ledger)
                    other.close()

    async def test_real_cli_timer_consumes_exact_recording_on_both_backends(
        self,
    ) -> None:
        for backend, kind in (
            ("snapshot", ConversationStore),
            ("sqlite", SQLiteConversationStore),
        ):
            with TemporaryDirectory() as directory:
                root = Path(directory)
                original = demo_cassette()
                chat = ConversationController(
                    ConversationController.fresh(root, original),
                    original,
                    lambda _: None,
                )
                session_id = chat.state.session_id
                with kind(root / "sessions", session_id, root) as store:
                    store.save(chat.state)
                    chat.save = store.save
                    goal = chat.create_goal(definition())
                    candidate = chat.state.model_copy(
                        update={
                            "entries": (
                                ConversationEntry(
                                    text="Inspect committed CI results",
                                    goal_id=goal.goal_id,
                                    goal_definition_sha256=goal.definition.sha256,
                                    interaction_mode=chat.state.interaction_mode,
                                ),
                            )
                        }
                    )
                    cassette = AgentCassette(
                        exchanges=(
                            AgentExchange(
                                request_sha256=preview_context(
                                    candidate
                                ).request.sha256,
                                response=original.exchanges[0].response,
                            ),
                        )
                    )
                    chat.refresh_memory(None, cassette, disabled=True)
                    chat.schedule_observer = recorded_loop_observer(chat)
                    self.assertEqual(
                        loop_command(
                            chat,
                            create(
                                interval_seconds=1,
                                expires_in_seconds=30,
                                maximum_fires=1,
                            ),
                            lambda _: None,
                        ),
                        "accepted",
                    )
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "resume",
                    session_id,
                    "-C",
                    str(root),
                    "--storage",
                    str(root / "sessions"),
                    "--storage-backend",
                    backend,
                    "--no-memory",
                    "--json",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                assert process.stdin is not None and process.stdout is not None
                try:
                    process.stdin.write(b"/loop resume watch\n")
                    await process.stdin.drain()
                    events: list[dict[str, object]] = []
                    async with asyncio.timeout(10):
                        while True:
                            raw = await process.stdout.readline()
                            self.assertTrue(raw, events)
                            event = json.loads(raw)
                            events.append(event)
                            if event["type"] == "message.completed":
                                break
                            self.assertNotIn(
                                event["type"], {"conversation.error", "message.failed"}
                            )
                    self.assertTrue(any(e["type"] == "message.running" for e in events))
                    process.stdin.write(b"/quit\n")
                    await process.stdin.drain()
                    _, errors = await asyncio.wait_for(process.communicate(), 3)
                    self.assertEqual(process.returncode, 0, errors.decode())
                    with kind(root / "sessions", session_id, root) as store:
                        state = store.load()
                        self.assertEqual(state.exchanges_consumed, 1)
                        self.assertEqual(
                            state.schedules[0].state.fires[0].state, "completed"
                        )
                        self.assertEqual(state.schedules[0].state.status, "exhausted")
                finally:
                    if process.returncode is None:
                        process.kill()
                        await process.communicate()

    async def test_replacement_owner_cannot_open_until_shutdown_is_persisted(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            timers = self.driver(chat)
            clock[0] = 110
            timers.tick()
            replacement = ActiveSessionTimers(chat, lambda _: None)
            observed: list[str] = []

            def save(state: ConversationState) -> None:
                with self.assertRaises(ValueError):
                    replacement.open()
                observed.append(state.schedules[0].state.status)

            chat.save = save
            timers.close()
            self.assertEqual(observed, ["paused"])
            replacement.open()
            self.assertEqual(replacement.tick(), ())
            replacement.close()

    async def test_running_timer_never_overlaps_or_replays_uncertain_work(self) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            timers = self.driver(chat)
            clock[0] = 110
            timers.tick()
            client = WaitingClient()
            task = asyncio.create_task(chat.step(client))
            await client.started.wait()
            clock[0] = 300
            self.assertEqual(timers.tick(), ())
            self.assertEqual(len(chat.state.schedules[0].state.fires), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            exposure = chat.state.schedules[0].state.ledger
            self.assertGreater(exposure.uncertain_effects, 0)
            self.assertEqual(timers.tick(), ())
            self.assertIsNone(timers.delay())
            resumed = ConversationController(
                chat.state, chat.cassette, lambda _: None, goal_clock=lambda: clock[0]
            )
            resumed.schedule_observer = recorded_loop_observer(resumed)
            other = self.driver(resumed)
            self.assertEqual(other.tick(), ())
            self.assertEqual(resumed.state.schedules[0].state.ledger, exposure)
            self.assertEqual(
                loop_command(resumed, "/loop resume watch", lambda _: None), "rejected"
            )
            self.assertEqual(resumed.state.schedules[0].state.ledger, exposure)

    async def test_skipped_intents_cannot_reset_shared_goal_budget(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            clock = [100.0]
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(root, cassette),
                cassette,
                lambda _: None,
                goal_clock=lambda: clock[0],
            )
            chat.schedule_observer = recorded_loop_observer(chat)
            goal_definition = definition()
            chat.create_goal(
                goal_definition.model_copy(
                    update={
                        "ceiling": goal_definition.ceiling.model_copy(
                            update={"attempts": 1}
                        ),
                    }
                )
            )
            loop_command(chat, create(maximum_fires=1), lambda _: None)
            timers = self.driver(chat)
            clock[0] = 110
            self.assertEqual(len(timers.tick()), 1)
            loop_command(chat, "/loop cancel watch", lambda _: None)
            self.assertEqual(
                loop_command(
                    chat,
                    create(
                        schedule_id="other",
                        maximum_fires=1,
                    ),
                    lambda _: None,
                ),
                "accepted",
            )
            clock[0] = 120
            self.assertEqual(timers.tick(), ())
            self.assertEqual(chat.state.schedules[1].state.status, "exhausted")
            self.assertEqual(len(chat.state.entries), 1)
            chat.submit("User steering also shares the retained ceiling")
            client = CapturingClient()
            with self.assertRaises(ValueError):
                await chat.step(client)
            self.assertEqual(client.requests, [])

    async def test_unqualified_terminal_inspection_does_not_change_schedule_state(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            chat.schedule_observer = None
            clock[0] = 110
            state = chat.state
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            queue.put_nowait("/loop status")
            queue.put_nowait(None)
            await terminal(chat, queue, lambda _: None)
            self.assertEqual(chat.state, state)
            self.assertFalse(chat.schedule_timer_active)

    async def test_resume_waits_new_interval_without_replaying_pending_timer(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            timers = self.driver(chat)
            chat.submit("User has priority over due timer")
            clock[0] = 200
            self.assertIsNone(
                chat.admit_schedule(
                    "watch",
                    expected_revision=chat.state.revision,
                )
            )
            self.assertTrue(chat.state.schedules[0].state.pending_timer)
            chat.cancel_queued()
            timers.close()
            other = self.driver(chat)
            self.assertEqual(
                loop_command(chat, "/loop resume watch", lambda _: None), "accepted"
            )
            self.assertFalse(chat.state.schedules[0].state.pending_timer)
            self.assertEqual(other.tick(), ())
            clock[0] = 210
            self.assertEqual(len(other.tick()), 1)

    async def test_skipped_intents_also_consume_inherited_fork_allowance(self) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory), maximum_fires=1)
            goal = chat.current_goal
            assert goal is not None
            chat.state = chat.state.model_copy(
                update={
                    "branch_budget": BranchBudget(
                        ceiling=goal.definition.ceiling.model_copy(
                            update={"attempts": 1}
                        ),
                        ledger=ResourceLedger(),
                    )
                }
            )
            timers = self.driver(chat)
            clock[0] = 110
            self.assertEqual(len(timers.tick()), 1)
            loop_command(chat, "/loop cancel watch", lambda _: None)
            self.assertEqual(
                loop_command(
                    chat,
                    create(
                        schedule_id="other",
                        maximum_fires=1,
                    ),
                    lambda _: None,
                ),
                "accepted",
            )
            clock[0] = 120
            self.assertEqual(timers.tick(), ())
            self.assertEqual(len(chat.state.entries), 1)
            events: list[dict[str, object]] = []
            loop_command(chat, "/loop --json", events.append)
            report = json.loads(str(events[-1]["text"]))
            self.assertEqual(report["schedules"][0]["branch_remaining"]["attempts"], 0)
            chat.submit("User shares the inherited fork allowance")
            client = CapturingClient()
            with self.assertRaises(ValueError):
                await chat.step(client)
            self.assertEqual(client.requests, [])

    async def test_tui_timer_dispatch_preserves_unsent_editor(self) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as pipe:
            chat, clock = self.fresh(Path(directory))
            client = CapturingClient()
            self.use_client(chat, client)
            ui = ConversationTUI(chat, input=pipe, output=DummyOutput())
            with patch.object(ActiveSessionTimers, "poll_seconds", 0.01):
                task = asyncio.create_task(ui.run())
                try:
                    await until(
                        lambda: ui.app.is_running and chat.schedule_timer_active
                    )
                    ui.editor.text = "Unsent steering draft"
                    clock[0] = 110
                    await until(
                        lambda client=client: (
                            len(client.requests) == 1 and chat.schedule_timer_idle
                        )
                    )
                    self.assertEqual(ui.editor.text, "Unsent steering draft")
                    self.assertIsNotNone(ui.context_preview)
                finally:
                    ui.editor.text = ""
                    pipe.send_text("\x04")
                    await asyncio.wait_for(task, 3)
            self.assertFalse(chat.schedule_timer_active)

    async def test_lost_host_requires_explicit_resume_before_timer_reactivation(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            timers = self.driver(chat)
            observer = chat.schedule_observer
            chat.schedule_observer = None
            clock[0] = 110
            self.assertEqual(timers.tick(), ())
            self.assertEqual(chat.state.schedules[0].state.status, "paused")
            self.assertFalse(chat.schedule_timer_active)
            chat.schedule_observer = observer
            self.assertEqual(timers.tick(), ())
            self.assertEqual(chat.state.entries, ())
            self.assertEqual(
                loop_command(chat, "/loop resume watch", lambda _: None), "accepted"
            )
            clock[0] = 120
            self.assertEqual(len(timers.tick()), 1)
