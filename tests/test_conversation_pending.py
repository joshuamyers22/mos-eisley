"""Queued-text admission preserves saved work, attempts and rejected drafts."""

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

from mos_eisley.conversation import ConversationController, ConversationEntry
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_pending import (
    PendingTextBudgetError,
    PendingTextLimits,
    pending_text_bytes,
)
from mos_eisley.conversation_review import REVIEW_PROMPT, ConversationReviewPacket
from mos_eisley.conversation_state import WorkingConversationState
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.demo import demo_inputs
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


def controller() -> ConversationController:
    cassette = demo_cassette()
    return ConversationController(
        ConversationController.fresh(Path.cwd(), cassette),
        cassette,
        lambda _: None,
        pending_limits=PendingTextLimits(max_bytes=4000),
    )


class PendingTextTests(TestCase):
    def test_strict_limits(self) -> None:
        self.assertEqual(PendingTextLimits().max_bytes, 64000)
        for value in (True, 3999, 512001, "4000", 4000.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PendingTextLimits.model_validate({"max_bytes": value})
        self.assertEqual(PendingTextLimits(max_bytes=512000).max_bytes, 512000)

    def test_exact_utf8_boundary_and_safe_error(self) -> None:
        chat = controller()
        chat.submit('é"\\\n' * 200)  # 1,000 UTF-8 bytes, independent of JSON escaping.
        chat.submit("🛰" * 750)
        self.assertEqual(chat.pending_text_bytes, 4000)
        before = chat.state
        with self.assertRaises(PendingTextBudgetError) as raised:
            chat.submit("private extra input")
        error = raised.exception
        self.assertEqual(error.queued_bytes, 4000)
        self.assertEqual(error.submitted_bytes, 19)
        self.assertEqual(error.required_bytes, 4019)
        self.assertEqual(error.maximum_bytes, 4000)
        self.assertNotIn("private extra input", str(error))
        self.assertIs(chat.state, before)

    def test_only_queued_text_counts(self) -> None:
        entries = (
            ConversationEntry(text="é", status="queued"),
            ConversationEntry(text="x" * 8000, status="running"),
            ConversationEntry(text="x" * 8000, status="cancelled"),
            ConversationEntry(text="x" * 8000, status="interrupted"),
        )
        self.assertEqual(pending_text_bytes(entries), 2)

    def test_rejection_does_not_save_or_poison_and_cancellation_frees_capacity(
        self,
    ) -> None:
        chat = controller()
        chat.submit("x" * 4000)
        before = chat.state
        with (
            patch.object(chat, "save", side_effect=AssertionError("unexpected save")),
            self.assertRaises(PendingTextBudgetError),
        ):
            chat.submit("new")
        self.assertIs(chat.state, before)
        self.assertEqual(chat.state.exchanges_consumed, 0)
        chat.cancel_queued()
        self.assertEqual(chat.pending_text_bytes, 0)
        chat.submit("new")
        self.assertEqual(chat.pending_text_bytes, 3)
        self.assertEqual(chat.state.entries[0].text, "x" * 4000)

    def test_review_uses_same_admission(self) -> None:
        chat = controller()
        chat.submit("x" * (4000 - len(REVIEW_PROMPT.encode())))
        brief, cassette = demo_inputs()
        packet = ConversationReviewPacket(brief=brief, cassette=cassette)
        chat.submit_review(packet)
        self.assertEqual(chat.pending_text_bytes, 4000)
        before = chat.state
        with self.assertRaises(PendingTextBudgetError):
            chat.submit_review(packet)
        self.assertIs(chat.state, before)
        self.assertTrue(chat.state.entries[-1].is_review)

    def test_lower_launch_limit_allows_recovery_of_existing_work(self) -> None:
        chat = controller()
        chat.pending_limits = None
        chat.submit("active")
        chat.submit("x" * 5000)
        running = chat.state.model_copy(
            update={
                "entries": (
                    chat.state.entries[0].model_copy(update={"status": "running"}),
                    chat.state.entries[1],
                ),
                "exchanges_consumed": 1,
            }
        )
        restored = ConversationController(
            running,
            chat.cassette,
            lambda _: None,
            pending_limits=PendingTextLimits(max_bytes=4000),
        )
        self.assertEqual(restored.state.entries[0].status, "interrupted")
        self.assertEqual(restored.pending_text_bytes, 5000)
        self.assertEqual(restored.state.exchanges_consumed, 1)
        with self.assertRaises(PendingTextBudgetError):
            restored.submit("new")
        restored.cancel_queued()
        restored.submit("new")

    def test_sqlite_archive_rejection_needs_no_hydration_or_write(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            brief, recording = demo_inputs()
            packet = ConversationReviewPacket(brief=brief, cassette=recording)
            with SQLiteConversationStore(
                root / "sessions", state.session_id, root
            ) as store:
                store.save(state)
                chat = ConversationController(state, cassette, store.save)
                chat.submit("x" * (4000 - len(REVIEW_PROMPT.encode())))
                chat.submit_review(packet)
                working = store.load_working()
                assert isinstance(working, WorkingConversationState)
                restored = ConversationController(
                    working,
                    cassette,
                    store.save_working,
                    load_entry=store.load_working_entry,
                    pending_limits=PendingTextLimits(max_bytes=4000),
                )
                before = store.snapshot_sha256
                with (
                    patch.object(
                        restored, "load_entry", side_effect=AssertionError("hydrated")
                    ),
                    patch.object(restored, "save", side_effect=AssertionError("saved")),
                    self.assertRaises(PendingTextBudgetError),
                ):
                    restored.submit("new")
                self.assertIs(restored.state, working)
                self.assertEqual(store.snapshot_sha256, before)
                self.assertEqual(restored.state.exchanges_consumed, 0)


class PendingTerminalTests(IsolatedAsyncioTestCase):
    async def test_composer_retains_rejected_draft(self) -> None:
        chat = controller()
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
        for text in ("/compose", "x" * 4001, "/send", "/send", "/quit"):
            queue.put_nowait(text)
        events: list[dict[str, object]] = []
        await terminal(chat, queue, events.append)
        rejected = [
            event for event in events if event.get("reason") == "pending_text_budget"
        ]
        self.assertEqual(len(rejected), 2)
        self.assertEqual(rejected[0]["required_bytes"], 4001)
        self.assertEqual(rejected[0]["maximum_bytes"], 4000)
        self.assertFalse(any(event["type"] == "composer.sent" for event in events))
        self.assertEqual(chat.state.entries, ())
        self.assertEqual(chat.state.revision, 0)
        self.assertEqual(chat.state.exchanges_consumed, 0)

    async def test_tui_retains_rejected_editor_text(self) -> None:
        chat = controller()
        chat.submit("x" * 4000)
        before = chat.state
        with create_pipe_input() as input:
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("keep this draft\r")
                await until(lambda: "Pending text needs" in ui.notice)
                self.assertEqual(ui.editor.text, "keep this draft")
                self.assertIn("4000/4000 queued text bytes", ui.status())
                self.assertIs(chat.state, before)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 3)

    async def test_active_work_frees_capacity_and_rejected_steering_keeps_ancestry(
        self,
    ) -> None:
        chat = controller()
        chat.submit(DEMO_PROMPTS[0])
        client = WaitingClient()
        task = asyncio.create_task(chat.step(client))
        try:
            await asyncio.wait_for(client.started.wait(), 3)
            self.assertEqual(chat.pending_text_bytes, 0)
            chat.steer("x" * 4000)
            before = chat.state
            with self.assertRaises(PendingTextBudgetError):
                chat.steer("too much")
            self.assertIs(chat.state, before)
            self.assertEqual(chat.state.entries[1].steering_for, 0)
            self.assertEqual(chat.state.exchanges_consumed, 1)
            client.release.set()
            await asyncio.wait_for(task, 3)
            self.assertEqual(chat.state.entries[0].status, "completed")
            self.assertEqual(chat.pending_text_bytes, 4000)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_existing_queue_can_run_above_new_limit(self) -> None:
        chat = controller()
        chat.submit(DEMO_PROMPTS[0])
        chat.pending_limits = None
        chat.submit("x" * 5000)
        chat.pending_limits = PendingTextLimits(max_bytes=4000)
        self.assertGreater(chat.pending_text_bytes, 4000)
        self.assertTrue(await chat.step())
        self.assertEqual(chat.state.entries[0].status, "completed")
        self.assertEqual(chat.pending_text_bytes, 5000)
        self.assertEqual(chat.state.exchanges_consumed, 1)


class PendingCLITests(TestCase):
    def invoke(
        self, root: Path, *args: str, text: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                *args,
                "--storage",
                str(root / "sessions"),
                "-C",
                str(root),
                "--json",
            ],
            input=text,
            text=True,
            capture_output=True,
            env={**os.environ, "HOME": str(root)},
            timeout=30,
        )

    def test_bare_launch_and_resume_report_per_launch_limit_without_changing_state(
        self,
    ) -> None:
        for backend, store_type in (
            ("snapshot", ConversationStore),
            ("sqlite", SQLiteConversationStore),
        ):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                root = Path(directory)
                result = self.invoke(
                    root,
                    "--pending-text-max-bytes=4000",
                    "--no-memory",
                    "--storage-backend",
                    backend,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                events = [json.loads(line) for line in result.stdout.splitlines()]
                budget = next(
                    event
                    for event in events
                    if event["type"] == "conversation.pending_text"
                )
                self.assertEqual(
                    (budget["queued_bytes"], budget["maximum_bytes"]), (0, 4000)
                )
                sid = next(
                    event["session_id"]
                    for event in events
                    if event["type"] == "conversation.opened"
                )
                with store_type(root / "sessions", sid, root, create=False) as store:
                    state = store.load()
                    chat = ConversationController(state, demo_cassette(), store.save)
                    chat.submit("x" * 4001)
                    before = digest(canonical_bytes(chat.state))
                for flags, maximum, submitted in (
                    (("--pending-text-max-bytes", "4000"), 4000, "new\n"),
                    ((), 64000, ""),
                ):
                    result = self.invoke(
                        root,
                        "resume",
                        sid,
                        "--storage-backend",
                        backend,
                        *flags,
                        text=submitted,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    events = [json.loads(line) for line in result.stdout.splitlines()]
                    budget = next(
                        event
                        for event in events
                        if event["type"] == "conversation.pending_text"
                    )
                    self.assertEqual(
                        (budget["queued_bytes"], budget["maximum_bytes"]),
                        (4001, maximum),
                    )
                    if submitted:
                        rejected = next(
                            event
                            for event in events
                            if event.get("reason") == "pending_text_budget"
                        )
                        self.assertEqual(rejected["required_bytes"], 4004)
                    with store_type(
                        root / "sessions", sid, root, create=False
                    ) as store:
                        saved = store.load()
                        self.assertEqual(digest(canonical_bytes(saved)), before)
                        self.assertEqual(saved.exchanges_consumed, 0)
                        self.assertNotIn("pending_limits", saved.model_dump())

    def test_invalid_limits_and_unused_inspection_option_reject_before_creation(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for value in ("3999", "512001", "true"):
                result = self.invoke(root, "--pending-text-max-bytes", value)
                self.assertEqual(result.returncode, 2)
                self.assertFalse((root / "sessions").exists())
            result = self.invoke(
                root,
                "resume",
                "--last",
                "--inspect",
                "--storage-backend",
                "sqlite",
                "--pending-text-max-bytes",
                "4000",
            )
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("conversation.opened", result.stdout)
            self.assertFalse((root / "sessions").exists())
