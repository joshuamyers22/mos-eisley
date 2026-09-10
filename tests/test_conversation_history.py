"""Keyboard history navigation, bounded background reads and stale-result isolation."""

import asyncio
import os
import pty
import select
import sqlite3
import subprocess
import sys
import termios
import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController, ConversationEntry
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_history import TranscriptHistory
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.run import conversation_transcript as transcript_backend
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore
from mos_eisley.run.conversation_transcript import (
    TranscriptPage,
)


async def until(predicate: Callable[[], bool]) -> None:
    async with asyncio.timeout(4):
        while not predicate():
            await asyncio.sleep(0.01)


class HistoryTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        cassette = demo_cassette()
        state = ConversationController.fresh(self.root, cassette).model_copy(
            update={
                "entries": tuple(
                    ConversationEntry(text=f"saved message {i}") for i in range(8)
                )
            }
        )
        self.store = SQLiteConversationStore(self.root, state.session_id, self.root)
        self.addCleanup(self.store.close)
        self.store.save(state)
        self.chat = ConversationController(state, cassette, self.store.save)

    def load(self, cursor: str | None) -> TranscriptPage:
        return self.store.transcript_page(cursor)

    def history(
        self, loader: Callable[[str | None], TranscriptPage] | None = None
    ) -> TranscriptHistory:
        return TranscriptHistory(
            loader or self.load,
            lambda: (
                self.chat.state.session_id,
                self.chat.state.revision,
                len(self.chat.state.entries),
            ),
            lambda: None,
        )

    async def test_keyboard_pages_preserve_draft_and_do_not_dispatch_or_save(
        self,
    ) -> None:
        before = (self.root / DATABASE).read_bytes()
        with create_pipe_input() as input:
            ui = ConversationTUI(
                self.chat, load_transcript=self.load, input=input, output=DummyOutput()
            )
            history = ui.history
            assert history is not None
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                self.assertNotIn("saved message 0", ui.transcript.text)
                self.assertIn("saved message 7", ui.transcript.text)
                input.send_text("PRIVATE UNSENT\x1b[15~")
                await until(lambda: history.page is not None and not history.loading)
                assert history.page is not None
                self.assertEqual(len(history.page.entries), 4)
                self.assertIn("saved message 0", ui.transcript.text)
                self.assertNotIn("saved message 4", ui.transcript.text)
                self.assertEqual(ui.editor.text, "PRIVATE UNSENT")
                ui.transcript.buffer.cursor_position = len(ui.transcript.text)
                input.send_text("\x1b[6~")
                await until(lambda: history.index == 1 and not history.loading)
                self.assertIn("saved message 7", ui.transcript.text)
                self.assertNotIn("saved message 0", ui.transcript.text)
                self.assertEqual(history.cursors[0], None)
                input.send_text("\x1b[5~")
                await until(lambda: history.index == 0 and not history.loading)
                self.assertEqual(len(history.cursors), 1)
                input.send_text("\x1b[15~")
                await until(lambda: not history.visible)
                self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
                self.assertEqual(ui.editor.text, "PRIVATE UNSENT")
                self.assertEqual(self.chat.state.exchanges_consumed, 0)
                self.assertEqual(self.chat.state.revision, 0)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 4)
        self.assertEqual((self.root / DATABASE).read_bytes(), before)

    async def test_catalog_change_rejects_navigation_until_reload(self) -> None:
        history = self.history()
        try:
            history.reload()
            await until(lambda: not history.loading)
            other = ConversationController.fresh(self.root, demo_cassette())
            with SQLiteConversationStore(
                self.root, other.session_id, self.root
            ) as store:
                store.save(other)
            history.move(1)
            await until(lambda: not history.loading)
            self.assertIsNone(history.page)
            self.assertIn("stale", history.error or "")
            history.reload()
            await until(lambda: not history.loading)
            self.assertIsNotNone(history.page)
            self.assertIsNone(history.error)
        finally:
            await history.shutdown()

    async def test_background_sqlite_read_cannot_make_own_save_fail_busy(self) -> None:
        entered, release = threading.Event(), threading.Event()
        original = transcript_backend.sqlite_read_transaction

        @contextmanager
        def held(root: Path) -> Generator[tuple[sqlite3.Connection, str, int]]:
            with original(root) as transaction:
                entered.set()
                if not release.wait(3):
                    raise ValueError("test reader timed out")
                yield transaction

        with patch.object(transcript_backend, "sqlite_read_transaction", held):
            reader = asyncio.create_task(
                asyncio.to_thread(self.store.transcript_page, None)
            )
            timer = threading.Timer(0.05, release.set)
            try:
                await until(entered.is_set)
                timer.start()
                self.chat.submit("save while browsing")
                page = await reader
                self.assertEqual(page.revision, 0)
                self.assertEqual(self.store.load(), self.chat.state)
                self.assertEqual(self.chat.state.revision, 1)
                self.assertEqual(self.chat.state.exchanges_consumed, 0)
            finally:
                release.set()
                timer.cancel()
                await reader

    async def test_session_change_clears_page_without_replaying_work(self) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(
                self.chat, load_transcript=self.load, input=input, output=DummyOutput()
            )
            history = ui.history
            assert history is not None
            try:
                history.reload()
                await until(lambda: not history.loading)
                self.chat.submit("new queued message")
                ui.refresh()
                self.assertIsNone(history.page)
                self.assertIn("Session changed", ui.transcript.text)
                self.assertEqual(self.chat.state.exchanges_consumed, 0)
                history.reload()
                await until(lambda: not history.loading)
                assert history.page is not None
                self.assertEqual(history.page.total_messages, 9)
            finally:
                await history.shutdown()

    async def test_reload_storm_serializes_reads_and_discards_closed_results(
        self,
    ) -> None:
        entered, release = threading.Event(), threading.Event()
        calls: list[str | None] = []

        def slow(cursor: str | None) -> TranscriptPage:
            calls.append(cursor)
            entered.set()
            if not release.wait(4):
                raise ValueError("test reader timed out")
            return self.load(cursor)

        history = self.history(slow)
        try:
            history.reload()
            await until(entered.is_set)
            for _ in range(30):
                history.reload()
            self.assertEqual(len(calls), 1)
            history.close()
            release.set()
            await until(lambda: not history.loading)
            self.assertIsNone(history.page)
            self.assertFalse(history.visible)
            self.assertEqual(len(calls), 1)
            history.reload()
            await until(lambda: not history.loading)
            self.assertEqual(len(calls), 2)
            self.assertIsNotNone(history.page)
        finally:
            release.set()
            await history.shutdown()

    async def test_pending_reload_replaces_obsolete_result(self) -> None:
        entered, release = threading.Event(), threading.Event()
        calls = 0
        original = self.load(None)

        def slow(cursor: str | None) -> TranscriptPage:
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                if not release.wait(4):
                    raise ValueError("test reader timed out")
                return original
            return self.load(cursor)

        history = self.history(slow)
        try:
            history.reload()
            await until(entered.is_set)
            self.chat.submit("new queued message")
            history.reload()
            release.set()
            await until(lambda: not history.loading)
            assert history.page is not None
            self.assertEqual(history.page.revision, 1)
            self.assertEqual(calls, 2)
        finally:
            release.set()
            await history.shutdown()

    async def test_foreign_result_and_read_error_never_render_a_page(self) -> None:
        original = self.load(None)
        loaders: tuple[Callable[[str | None], TranscriptPage], ...] = (
            lambda cursor: original.model_copy(update={"session_id": "0" * 32}),
            lambda cursor: original.model_copy(update={"revision": 999}),
        )
        for loader in loaders:
            history = self.history(loader)
            try:
                history.reload()
                await until(lambda history=history: not history.loading)
                self.assertIsNone(history.page)
                self.assertIn("Session changed", history.error or "")
            finally:
                await history.shutdown()

        def broken(cursor: str | None) -> TranscriptPage:
            raise ValueError("unsafe\x1b[31mstorage")

        with create_pipe_input() as input:
            ui = ConversationTUI(
                self.chat, load_transcript=broken, input=input, output=DummyOutput()
            )
            failed_history = ui.history
            assert failed_history is not None
            try:
                failed_history.reload()
                await until(lambda: not failed_history.loading)
                self.assertNotIn("\x1b", ui.transcript.text)
                self.assertIn("unavailable", ui.transcript.text)
            finally:
                await failed_history.shutdown()

    async def test_slow_history_keeps_editor_responsive_and_quit_joins_reader(
        self,
    ) -> None:
        entered, release = threading.Event(), threading.Event()

        def slow(cursor: str | None) -> TranscriptPage:
            entered.set()
            if not release.wait(4):
                raise ValueError("test reader timed out")
            return self.load(cursor)

        with create_pipe_input() as input:
            ui = ConversationTUI(
                self.chat, load_transcript=slow, input=input, output=DummyOutput()
            )
            history = ui.history
            assert history is not None
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("\x1b[15~")
                await until(entered.is_set)
                input.send_text("\tdraft during read")
                await until(lambda: ui.editor.text == "draft during read")
                input.send_text("\x04")
                await until(lambda: not ui.app.is_running)
                self.assertEqual(ui.editor.text, "")
                release.set()
                await asyncio.wait_for(task, 4)
                self.assertIsNone(history.task)
                self.assertIsNone(history.page)
                self.assertEqual(self.chat.state.exchanges_consumed, 0)
            finally:
                release.set()
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_snapshot_screen_retains_full_transcript_and_reports_history_scope(
        self,
    ) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(self.chat, input=input, output=DummyOutput())
            self.assertIn("saved message 0", ui.transcript.text)
            self.assertIn("saved message 7", ui.transcript.text)
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("\x1b[15~")
                await until(lambda: "SQLite" in ui.notice)
                self.assertIsNone(ui.history)
                self.assertEqual(self.chat.state.exchanges_consumed, 0)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 4)


class HistoryPTYTests(TestCase):
    def test_sqlite_resume_wires_history_and_restores_terminal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette).model_copy(
                update={
                    "entries": tuple(
                        ConversationEntry(text=f"saved message {i}") for i in range(8)
                    )
                }
            )
            with SQLiteConversationStore(root, state.session_id, root) as store:
                store.save(state)
            before = (root / DATABASE).read_bytes()
            master, slave = pty.openpty()
            original = termios.tcgetattr(slave)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "resume",
                    state.session_id,
                    "--storage-backend",
                    "sqlite",
                    "--storage",
                    str(root),
                    "-C",
                    str(root),
                ],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                start_new_session=True,
                env={**os.environ, "TERM": "xterm-256color", "HOME": str(root)},
            )
            output = bytearray()

            def read_until(expected: bytes) -> None:
                deadline = time.monotonic() + 10
                while expected not in output:
                    if time.monotonic() >= deadline:
                        raise AssertionError(repr(output[-4000:]))
                    readable, _, _ = select.select([master], [], [], 0.1)
                    if readable:
                        data = os.read(master, 16384)
                        output.extend(data)
                        if b"\x1b[6n" in data:
                            os.write(master, b"\x1b[1;1R")

            try:
                read_until(b"\x1b[?1049h")
                read_until(b"Directory:")
                os.write(master, b"\x1b[15~")
                read_until(b"Saved history")
                os.write(master, b"\x0c")
                read_until(b"saved message 0")
                os.write(master, b"\x1b[15~\x04")
                read_until(b"conversation.saved")
                self.assertEqual(process.wait(timeout=5), 0)
                restored = termios.tcgetattr(slave)
                # Darwin can mark queued input for retyping after canonical restore.
                restored[3] &= ~getattr(termios, "PENDIN", 0)
                original[3] &= ~getattr(termios, "PENDIN", 0)
                self.assertEqual(restored, original)
                self.assertEqual((root / DATABASE).read_bytes(), before)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                os.close(master)
                os.close(slave)
