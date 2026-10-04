"""Shared loop controls and editor acknowledgements over durable scheduling."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from test_conversation import WaitingClient
from test_conversation_goal import definition
from test_conversation_tui import until

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette, terminal
from mos_eisley.conversation_input import (
    ConversationInput,
    ConversationSubmission,
    submission_command,
)
from mos_eisley.conversation_loop_commands import loop_command, recorded_loop_observer
from mos_eisley.conversation_schedule import InertScheduleSpec, ScheduleBinding
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


def create(**changes: object) -> str:
    value: dict[str, object] = dict(
        schedule_id="watch",
        task_id="ci",
        prompt="Inspect committed CI results",
        interval_seconds=10,
        expires_in_seconds=300,
        maximum_fires=2,
        input_bytes=32000,
        output_bytes=24000,
    )
    value.update(changes)
    return "/loop create " + json.dumps(value)


class LoopTests(IsolatedAsyncioTestCase):
    def fresh(self, root: Path) -> tuple[ConversationController, list[float]]:
        clock = [100.0]
        cassette = demo_cassette()
        chat = ConversationController(
            ConversationController.fresh(root, cassette),
            cassette,
            lambda _: None,
            goal_clock=lambda: clock[0],
        )
        chat.schedule_observer = recorded_loop_observer(chat)
        return chat, clock

    def control(self, chat: ConversationController, command: str) -> dict[str, object]:
        events: list[dict[str, object]] = []
        self.assertEqual(loop_command(chat, command, events.append), "accepted")
        return events[-1]

    async def test_creation_is_explicit_bounded_and_never_dispatches(self) -> None:
        with TemporaryDirectory() as directory:
            chat, _ = self.fresh(Path(directory))
            initial = chat.state
            self.control(chat, "/loop")
            self.assertEqual(chat.state, initial)
            self.assertEqual(loop_command(chat, create(), lambda _: None), "rejected")
            chat.create_goal(definition())
            revision = chat.state.revision
            self.control(chat, create())
            state = chat.state.schedules[0].state
            self.assertEqual(chat.state.revision, revision + 1)
            self.assertEqual(state.spec.binding.session_id, chat.state.session_id)
            self.assertEqual(state.spec.binding.task_id, "ci")
            self.assertEqual(state.spec.ceiling.attempts, 2)
            self.assertEqual(state.spec.ceiling.cost_microusd, 0)
            self.assertEqual(state.spec.expires_at, 400)
            self.assertEqual(chat.state.entries, ())
            self.assertEqual(chat.state.exchanges_consumed, 0)
            self.assertFalse(state.dispatch_authorized)
            self.control(
                chat,
                create(
                    schedule_id="dynamic",
                    cadence="dynamic",
                    minimum_interval_seconds=5,
                    maximum_interval_seconds=20,
                ),
            )
            self.assertEqual(chat.state.schedules[1].state.spec.cadence, "dynamic")

    async def test_rejected_controls_preserve_state(self) -> None:
        with TemporaryDirectory() as directory:
            chat, _ = self.fresh(Path(directory))
            chat.create_goal(definition())
            for command in (
                "/loop monitor CI",
                "/loop create {}",
                "/loop cancel absent",
                "/loop resume absent",
                "/loop status a b",
                "/loop --json --json",
                "/loop status --json --json",
                "/loop\nstatus",
                "/loop " + "x" * 8000,
                create(prompt=" "),
                create(cadence="dynamic"),
                create(maximum_fires=0),
                create(expires_in_seconds=9999),
                create(owner_uid=chat.state.owner_uid),
                create(binding={}),
                create(local_sources=["ci"]),
                create(cost_microusd=1),
            ):
                with self.subTest(command=command[:100]):
                    state = chat.state
                    self.assertEqual(
                        loop_command(chat, command, lambda _: None), "rejected"
                    )
                    self.assertEqual(chat.state, state)
            chat.schedule_observer = None
            self.assertEqual(loop_command(chat, create(), lambda _: None), "rejected")

    async def test_inspection_json_remaining_exposure_and_expiry_are_readonly(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            chat.create_goal(definition())
            self.control(chat, create())
            clock[0] = 110
            self.assertIsNotNone(
                chat.admit_schedule("watch", expected_revision=chat.state.revision)
            )
            state = chat.state
            plain = self.control(chat, "/loop status watch")
            encoded = self.control(chat, "/loop status --json watch")
            self.assertEqual(plain["schedules"], encoded["schedules"])
            self.assertEqual(
                json.loads(str(encoded["text"]))["schedules"], plain["schedules"]
            )
            item = json.loads(str(encoded["text"]))["schedules"][0]
            self.assertEqual(item["remaining_fires"], 1)
            self.assertEqual(item["remaining"]["attempts"], 1)
            self.assertEqual(item["unresolved"][0]["queue_state"], "queued")
            self.assertEqual(chat.state, state)
            chat.schedule_observer = None
            clock[0] = 401
            self.assertIn(
                "Expired by current clock", str(self.control(chat, "/loop")["text"])
            )
            self.assertEqual(chat.state, state)

    async def test_cancel_keeps_charges_and_cannot_resume(self) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            chat.create_goal(definition())
            self.control(chat, create())
            clock[0] = 110
            chat.admit_schedule("watch", expected_revision=chat.state.revision)
            ledger = chat.state.schedules[0].state.ledger
            self.control(chat, "/loop cancel watch")
            self.assertEqual(chat.state.entries[0].status, "cancelled")
            self.assertEqual(chat.state.schedules[0].state.ledger, ledger)
            before = chat.state
            self.assertEqual(
                loop_command(chat, "/loop resume watch", lambda _: None), "rejected"
            )
            self.assertEqual(chat.state, before)

    async def test_both_stores_restart_guarded_resume_and_stale_policy(self) -> None:
        for kind in (ConversationStore, SQLiteConversationStore):
            with TemporaryDirectory() as directory:
                root = Path(directory)
                chat, clock = self.fresh(root)
                with kind(root / "sessions", chat.state.session_id, root) as store:
                    store.save(chat.state)
                    chat.save = store.save
                    chat.create_goal(definition())
                    self.control(chat, create())
                    loaded = store.load()
                    resumed = ConversationController(
                        loaded,
                        chat.cassette,
                        store.save,
                        goal_clock=lambda clock=clock: clock[0],
                    )
                    resumed.schedule_observer = recorded_loop_observer(resumed)
                    self.assertEqual(resumed.state.schedules[0].state.status, "paused")
                    ledger = resumed.state.schedules[0].state.ledger
                    self.control(resumed, "/loop resume watch")
                    self.assertEqual(store.load().schedules[0].state.status, "active")
                    self.assertEqual(resumed.state.schedules[0].state.ledger, ledger)
                    original = resumed.schedule_observer
                    resumed.schedule_observer = lambda s, original=original: original(
                        s
                    ).model_copy(update={"policy_sha256": "f" * 64})
                    self.assertEqual(
                        loop_command(resumed, "/loop resume watch", lambda _: None),
                        "rejected",
                    )
                    self.control(resumed, "/loop cancel watch")
                    self.assertEqual(
                        store.load().schedules[0].state.status, "cancelled"
                    )

    async def test_terminal_typed_and_plain_share_controls_and_acknowledgement(
        self,
    ) -> None:
        for typed in (False, True):
            with TemporaryDirectory() as directory:
                chat, _ = self.fresh(Path(directory))
                chat.create_goal(definition())
                queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
                acknowledgements: list[asyncio.Future[bool]] = []
                for text in (
                    create(),
                    "/loop status --json",
                    "/loop cancel watch",
                    "/loop resume watch",
                ):
                    if typed:
                        ack = asyncio.get_running_loop().create_future()
                        acknowledgements.append(ack)
                        queue.put_nowait(ConversationSubmission(text, False, ack))
                    else:
                        queue.put_nowait(text)
                queue.put_nowait(None)
                events: list[dict[str, object]] = []
                await terminal(chat, queue, events.append)
                self.assertEqual(
                    [a.result() for a in acknowledgements],
                    [True, True, True, False] if typed else [],
                )
                self.assertEqual(chat.state.entries, ())
                self.assertTrue(any(e["type"] == "conversation.loop" for e in events))
        self.assertEqual(submission_command("/loop status"), "loop_control")
        self.assertIsNone(submission_command("/looper"))

    async def test_real_cli_installs_trusted_observer_on_both_backends(self) -> None:
        for backend in ("snapshot", "sqlite"):
            for output in ("--plain", "--json"):
                with TemporaryDirectory() as directory:
                    root = Path(directory)
                    result = await asyncio.to_thread(
                        subprocess.run,
                        [
                            sys.executable,
                            "-m",
                            "mos_eisley.cli",
                            "chat",
                            "-C",
                            str(root),
                            "--storage",
                            str(root / "sessions"),
                            "--storage-backend",
                            backend,
                            "--no-memory",
                            output,
                        ],
                        input="\n".join(
                            (
                                "/goal new Inspect committed CI results",
                                create(),
                                "/loop status watch",
                                "/loop cancel watch",
                                "/quit",
                                "",
                            )
                        ),
                        text=True,
                        capture_output=True,
                        timeout=20,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("Loop control rejected", result.stdout)
                    if output == "--json":
                        events = [
                            json.loads(line) for line in result.stdout.splitlines()
                        ]
                        loops = [e for e in events if e["type"] == "conversation.loop"]
                        self.assertEqual(len(loops), 3)
                        self.assertEqual(
                            loops[-1]["schedules"][0]["record"]["state"]["status"],
                            "cancelled",
                        )
                        self.assertTrue(all(not e["automatic_dispatch"] for e in loops))
                    else:
                        self.assertIn("watch: active", result.stdout)
                        self.assertIn("watch: cancelled", result.stdout)

    async def test_pasted_controls_are_literal_author_text(self) -> None:
        with TemporaryDirectory() as directory:
            chat, _ = self.fresh(Path(directory))
            queue: asyncio.Queue[ConversationInput] = asyncio.Queue()
            ack = asyncio.get_running_loop().create_future()
            queue.put_nowait(ConversationSubmission("/loop status", True, ack))
            queue.put_nowait(None)
            await terminal(chat, queue, lambda _: None)
            self.assertTrue(ack.result())
            self.assertEqual(chat.state.entries[0].text, "/loop status")
            self.assertEqual(chat.state.schedules, ())

    async def test_uncertain_work_is_visible_and_resume_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            chat, clock = self.fresh(Path(directory))
            chat.create_goal(definition())
            self.control(chat, create())
            clock[0] = 110
            chat.admit_schedule("watch", expected_revision=chat.state.revision)
            client = WaitingClient()
            task = asyncio.create_task(chat.step(client))
            await client.started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            before = chat.state
            event = self.control(chat, "/loop --json")
            item = json.loads(str(event["text"]))["schedules"][0]
            self.assertEqual(item["unresolved"][0]["state"], "uncertain")
            self.assertGreater(
                item["record"]["state"]["ledger"]["uncertain_effects"], 0
            )
            self.assertEqual(
                loop_command(chat, "/loop resume watch", lambda _: None), "rejected"
            )
            self.assertEqual(chat.state, before)

    async def test_failed_persistence_is_fatal_and_no_success_is_emitted(self) -> None:
        with TemporaryDirectory() as directory:
            chat, _ = self.fresh(Path(directory))
            chat.create_goal(definition())
            before = chat.state

            def fail(_: object) -> None:
                raise OSError("lost storage acknowledgement")

            chat.save = fail
            events: list[dict[str, object]] = []
            with self.assertRaises(OSError):
                loop_command(chat, create(), events.append)
            self.assertTrue(chat.persistence_broken)
            self.assertEqual(chat.state, before)
            self.assertEqual(events, [])

    async def test_reentrant_scope_observation_cannot_commit_stale_command(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            chat, _ = self.fresh(Path(directory))
            chat.create_goal(definition())
            original = chat.schedule_observer
            assert original is not None

            def changed(spec: InertScheduleSpec) -> ScheduleBinding:
                binding = original(spec)
                chat.set_interaction_mode("plan")
                return binding

            chat.schedule_observer = changed
            self.assertEqual(loop_command(chat, create(), lambda _: None), "rejected")
            self.assertEqual(chat.state.schedules, ())
            self.assertEqual(chat.state.interaction_mode, "plan")

    async def test_tui_reports_preserve_draft_and_rejections_keep_command(self) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as pipe:
            chat, _ = self.fresh(Path(directory))
            ui = ConversationTUI(chat, input=pipe, output=DummyOutput())
            ui.editor.text = "Unsent task draft"
            loop_command(chat, "/loop", ui.emit)
            self.assertEqual(ui.editor.text, "Unsent task draft")
            self.assertEqual(ui.context_command, "/loop status")
            ui.editor.text = ""
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                pipe.send_text("/loop cancel absent\r")
                await until(
                    lambda: not ui.sending and "Loop control rejected" in ui.notice
                )
                self.assertEqual(ui.editor.text, "/loop cancel absent")
                ui.editor.text = ""
                pipe.send_text("/loop status\r")
                await until(lambda: not ui.sending and ui.editor.text == "")
                self.assertEqual(chat.state.entries, ())
            finally:
                pipe.send_text("\x04")
                await asyncio.wait_for(task, 3)
