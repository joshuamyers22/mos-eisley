"""Active timer ownership, input priority, qualification and durable shutdown."""

import asyncio
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
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_input import ConversationInput
from mos_eisley.conversation_loop_commands import loop_command, recorded_loop_observer
from mos_eisley.conversation_schedule import InertScheduleSpec, ScheduleBinding
from mos_eisley.conversation_schedule_driver import ActiveSessionTimers
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.ports import ModelClient
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


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
                        await until(lambda chat=chat: not chat.schedule_boundary_busy)
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
                            len(client.requests) == 1
                            and not chat.schedule_boundary_busy
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
