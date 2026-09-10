"""Saved terminal context inspection without dispatch or artifact expansion."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from test_conversation import WaitingClient
from test_conversation_tui import until

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_admission_inspection import (
    AdmissionInspection,
    AdmissionInspectionUnavailable,
    admission_position,
    inspect_admission,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_context_preview import preview_context
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    WorkingConversationState,
)
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_fingerprint
from mos_eisley.demo import demo_inputs
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


def controller() -> ConversationController:
    cassette = demo_cassette()
    return ConversationController(
        ConversationController.fresh(Path.cwd(), cassette), cassette, lambda _: None
    )


class AdmissionInspectionTests(TestCase):
    def test_selectors_are_bounded_ascii_positions_and_errors_do_not_echo_input(
        self,
    ) -> None:
        for text, expected in (
            ("/context 0", 0),
            ("/context 15", 15),
            ("/context\t01", 1),
        ):
            self.assertEqual(admission_position(text), expected)
        for text in (
            "/context",
            "/context -1",
            "/context 16",
            "/context 1 2",
            "/context １２",
            "/context " + "9" * 5000,
            "/context PRIVATE",
        ):
            with (
                self.subTest(text=text[:30]),
                self.assertRaises(AdmissionInspectionUnavailable) as caught,
            ):
                admission_position(text)
            self.assertNotIn("PRIVATE", str(caught.exception))

    def test_saved_budgets_and_selection_survive_later_history_and_config_changes(
        self,
    ) -> None:
        chat = controller()
        chat.submit(DEMO_PROMPTS[0])
        chat.submit(DEMO_PROMPTS[1])
        preview = preview_context(chat.state)
        asyncio.run(chat.step())
        saved = chat.state.entries[0].request_admission
        chat.resize_context(4000)
        chat.submit("PRIVATE later submission")
        before = canonical_fingerprint(chat.state)
        with patch(
            "mos_eisley.conversation.prepare_conversation_request",
            side_effect=AssertionError("rebuilt"),
        ):
            report = inspect_admission(chat.state, 0)
        self.assertEqual(report.admission, saved)
        self.assertEqual(report.admission.request, preview.request)
        self.assertEqual(report.admission.selection, preview.selection)
        self.assertEqual(report.admission.context_max_bytes, preview.context_max_bytes)
        self.assertNotEqual(
            report.admission.context_max_bytes, chat.state.context_byte_limit
        )
        self.assertEqual(report.admission.message_count, 2)
        self.assertEqual(report.status, "completed")
        self.assertEqual(report.revision, chat.state.revision)
        self.assertEqual(
            AdmissionInspection.model_validate_json(report.model_dump_json()), report
        )
        text = report.describe()
        self.assertIn(preview.request.sha256, text)
        self.assertIn(preview.context_sha256, text)
        self.assertIn("Omitted message 1", text)
        self.assertNotIn("Omitted message 2", text)
        self.assertIn("not proof of transmission", text)
        self.assertNotIn("PRIVATE", text + report.model_dump_json())
        self.assertEqual(canonical_fingerprint(chat.state), before)

    def test_missing_legacy_review_queued_and_invalid_positions_are_safe_notices(
        self,
    ) -> None:
        chat = controller()
        chat.submit(DEMO_PROMPTS[0])
        with self.assertRaisesRegex(AdmissionInspectionUnavailable, "queued"):
            inspect_admission(chat.state, 0)
        asyncio.run(chat.step())
        old = chat.state.entries[0].model_copy(update={"request_admission": None})
        chat.state = chat.state.model_copy(update={"entries": (old,)})
        with self.assertRaisesRegex(
            AdmissionInspectionUnavailable, "cannot be reconstructed"
        ):
            inspect_admission(chat.state, 0)
        brief, recording = demo_inputs()
        chat.submit_review(ConversationReviewPacket(brief=brief, cassette=recording))
        with self.assertRaisesRegex(AdmissionInspectionUnavailable, "isolated packets"):
            inspect_admission(chat.state, 1)
        for position in (-1, 2, 16, True):
            with (
                self.subTest(position=position),
                self.assertRaisesRegex(
                    AdmissionInspectionUnavailable, "No saved message"
                ),
            ):
                inspect_admission(chat.state, position)

    def test_sqlite_archived_inspection_never_hydrates_or_saves(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            with SQLiteConversationStore(
                root / "sessions", state.session_id, root
            ) as store:
                store.save(state)
                chat = ConversationController(state, cassette, store.save)
                chat.refresh_memory(None, cassette)
                chat.submit(DEMO_PROMPTS[0])
                asyncio.run(chat.step())
                working = store.load_working()
                assert isinstance(working, WorkingConversationState)
                self.assertIsInstance(working.entries[0], ArchivedConversationEntry)
                before = store.snapshot_sha256
                with (
                    patch.object(
                        store,
                        "load_working_entry",
                        side_effect=AssertionError("hydrated"),
                    ),
                    patch.object(
                        store,
                        "_artifact_chunks",
                        side_effect=AssertionError("read artifact"),
                    ),
                    patch.object(
                        store, "save_working", side_effect=AssertionError("saved")
                    ),
                ):
                    report = inspect_admission(working, 0)
                self.assertEqual(
                    report.admission, chat.state.entries[0].request_admission
                )
                self.assertEqual(store.snapshot_sha256, before)


class AdmissionInspectionTerminalTests(IsolatedAsyncioTestCase):
    async def test_inspection_shows_current_status_without_changing_active_attempt(
        self,
    ) -> None:
        chat = controller()
        chat.submit(DEMO_PROMPTS[0])
        client = WaitingClient()
        task = asyncio.create_task(chat.step(client))
        try:
            await client.started.wait()
            running = chat.state
            report = inspect_admission(running, 0)
            self.assertEqual(report.status, "running")
            self.assertIs(chat.state, running)
            self.assertFalse(task.done())
            restored = ConversationController(running, demo_cassette(), lambda _: None)
            recovered = inspect_admission(restored.state, 0)
            self.assertEqual(recovered.status, "interrupted")
            self.assertEqual(recovered.admission, report.admission)
            client.release.set()
            await task
            completed = inspect_admission(chat.state, 0)
            self.assertEqual(completed.status, "completed")
            self.assertEqual(completed.admission, report.admission)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_terminal_history_and_bad_selectors_do_not_enable_work_or_save(
        self,
    ) -> None:
        chat = controller()
        chat.submit(DEMO_PROMPTS[0])
        await chat.step()
        chat.submit(DEMO_PROMPTS[1])
        before = chat.state
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        for line in (
            "/context 0",
            "/context 1",
            "/context PRIVATE",
            "/context 15",
            "/context 0 1",
            "/context",
            None,
        ):
            queue.put_nowait(line)
        events: list[dict[str, object]] = []
        with (
            patch.object(chat, "save", side_effect=AssertionError("saved")),
            patch.object(chat, "step", side_effect=AssertionError("dispatched")),
        ):
            await terminal(chat, queue, events.append)
        reports = [
            event
            for event in events
            if event["type"] == "conversation.context_admission"
        ]
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["message_index"], 0)
        self.assertEqual(reports[0]["schema_version"], 1)
        self.assertNotIn("PRIVATE", json.dumps(events))
        self.assertEqual(
            sum(event["type"] == "conversation.unavailable" for event in events), 4
        )
        self.assertEqual(
            sum(event["type"] == "conversation.context" for event in events), 1
        )
        self.assertIs(chat.state, before)

    async def test_tui_saved_admission_toggle_stale_refresh_and_preview_preserve_draft(
        self,
    ) -> None:
        chat = controller()
        chat.submit(DEMO_PROMPTS[0])
        await chat.step()
        chat.submit(DEMO_PROMPTS[1])
        admission = chat.state.entries[0].request_admission
        with create_pipe_input() as input:
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("unsent draft")
                await until(lambda: ui.editor.text == "unsent draft")
                ui.control("/context 0")
                await until(
                    lambda: "Saved request admission • message 0" in ui.transcript.text
                )
                self.assertEqual(ui.editor.text, "unsent draft")
                ui.control("/context 0")
                await until(lambda: ui.context_preview is None)
                ui.control("/context 0")
                await until(lambda: ui.context_preview is not None)
                chat.resize_context(4000)
                ui.refresh()
                self.assertIn(
                    "Saved admission view is stale; run /context 0 again.",
                    ui.transcript.text,
                )
                ui.control("/context 0")
                await until(
                    lambda: "Saved request admission • message 0" in ui.transcript.text
                )
                self.assertEqual(chat.state.entries[0].request_admission, admission)
                ui.control("/context")
                await until(lambda: "Context preview • message 1" in ui.transcript.text)
                self.assertNotIn("Saved request admission •", ui.transcript.text)
                self.assertEqual(ui.editor.text, "unsent draft")
                self.assertEqual(chat.state.exchanges_consumed, 1)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)


class AdmissionInspectionCLITests(TestCase):
    def test_resumed_inspection_preserves_both_storage_backends(self) -> None:
        for backend, store_type in (
            ("snapshot", ConversationStore),
            ("sqlite", SQLiteConversationStore),
        ):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                root = Path(directory)
                cassette = demo_cassette()
                state = ConversationController.fresh(
                    root, cassette, memory_disabled=True
                )
                with store_type(root / "sessions", state.session_id, root) as store:
                    store.save(state)
                    chat = ConversationController(state, cassette, store.save)
                    chat.refresh_memory(None, cassette, disabled=True)
                    chat.submit(DEMO_PROMPTS[0])
                    asyncio.run(chat.step())
                    chat.submit(DEMO_PROMPTS[1])
                    expected = inspect_admission(chat.state, 0)
                    before = canonical_fingerprint(chat.state)
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        "resume",
                        state.session_id,
                        "--storage-backend",
                        backend,
                        "--storage",
                        str(root / "sessions"),
                        "-C",
                        str(root),
                        "--json",
                    ],
                    input="/context 0\n/context 1\n",
                    text=True,
                    capture_output=True,
                    env={**os.environ, "HOME": str(root)},
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                events = [json.loads(line) for line in result.stdout.splitlines()]
                event = next(
                    event
                    for event in events
                    if event["type"] == "conversation.context_admission"
                )
                self.assertEqual(
                    event,
                    {
                        "type": "conversation.context_admission",
                        **expected.model_dump(mode="json"),
                        "text": expected.describe(),
                    },
                )
                with store_type(
                    root / "sessions", state.session_id, root, create=False
                ) as store:
                    self.assertEqual(canonical_fingerprint(store.load()), before)
