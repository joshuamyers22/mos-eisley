"""Explicit keyboard selection, stale guards and passive real-terminal resume."""

import argparse
import asyncio
import os
import pty
import select
import subprocess
import sys
import termios
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import (
    DEMO_PROMPTS,
    add_commands,
    demo_cassette,
    run_command,
)
from mos_eisley.conversation_picker import ResumePicker, ResumeSelection, safe_label
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.conversation_names import resume_catalog
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


async def until(predicate: Callable[[], bool]) -> None:
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.01)


class PickerTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = self.root / "sessions"
        state = ConversationController.fresh(self.root, demo_cassette()).model_copy(
            update={"session_name": "Café task"}
        )
        with ConversationStore(self.storage, state.session_id, self.root) as store:
            store.save(state)
        self.catalog = resume_catalog(self.storage, self.root, sqlite=False)

    async def test_keyboard_filter_clear_page_and_explicit_select(self) -> None:
        row = self.catalog.sessions[0]
        rows = tuple(
            row.model_copy(
                update={
                    "session_id": f"{index:032x}",
                    "session_name": f"Task {index:02d}",
                }
            )
            for index in range(45)
        )
        catalog = replace(self.catalog, sessions=rows)
        with create_pipe_input() as input:
            ui = ResumePicker(
                catalog, lambda: catalog, input=input, output=DummyOutput()
            )
            task = asyncio.create_task(ui.app.run_async())
            try:
                await until(lambda ui=ui: ui.app.is_running)
                self.assertEqual(len(ui.render_rows()), 20)
                input.send_text("\x1b[6~")
                await until(lambda: ui.index == 20)
                self.assertIn(rows[20].session_id, ui.render_rows()[0][1])
                input.send_text("\x1b[5~")
                await until(lambda: ui.index == 0)
                input.send_text("task 44")
                await until(lambda: len(ui.rows) == 1)
                self.assertEqual(ui.rows[0].session_id, rows[44].session_id)
                input.send_text("\x7f")
                await until(lambda: len(ui.rows) == 5)
                input.send_text("\x15")
                await until(lambda: len(ui.rows) == 45)
                input.send_text("\x1b[B\x1b[B\x1b[A\r")
                result = await asyncio.wait_for(task, 3)
                assert result is not None
                self.assertEqual(result.summary.session_id, rows[1].session_id)
            finally:
                if not task.done():
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)

    async def test_active_selection_refresh_failure_and_cancel(self) -> None:
        row = self.catalog.sessions[0].model_copy(update={"active": True})
        catalog = replace(self.catalog, sessions=(row,))
        with create_pipe_input() as input:

            def reload():
                raise ValueError("private diagnostic")

            ui = ResumePicker(catalog, reload, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.app.run_async())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("\r")
                await until(lambda: "active" in ui.notice)
                self.assertFalse(task.done())
                input.send_text("\x1b[15~")
                await until(lambda: not ui.valid)
                self.assertEqual(ui.rows, ())
                self.assertNotIn("private diagnostic", ui.notice)
                ui.select()
                self.assertFalse(task.done())
                ui.reload = lambda: self.catalog
                input.send_text("\x1b[15~")
                await until(lambda: ui.valid)
                input.send_text("\x04")
                self.assertIsNone(await asyncio.wait_for(task, 3))
            finally:
                if not task.done():
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)

    async def test_rename_pauses_pending_work_and_save_failure_exits(self) -> None:
        cassette = demo_cassette()
        for fail in (False, True):
            chat = ConversationController(
                ConversationController.fresh(self.root, cassette),
                cassette,
                lambda state: None,
            )
            chat.submit(DEMO_PROMPTS[0])
            with create_pipe_input() as input:
                ui = ConversationTUI(chat, input=input, output=DummyOutput())
                task = asyncio.create_task(ui.run())
                await until(lambda ui=ui: ui.app.is_running)
                if fail:
                    with patch.object(
                        chat, "save", side_effect=ValueError("save failed")
                    ):
                        input.send_text("/rename Work\r")
                        with self.assertRaisesRegex(ValueError, "save failed"):
                            await asyncio.wait_for(task, 3)
                    self.assertIsNone(chat.state.session_name)
                else:
                    try:
                        input.send_text("/rename Work\r")
                        await until(lambda chat=chat: chat.state.session_name == "Work")
                        self.assertIn("Work", ui.header())
                        self.assertEqual(chat.state.entries[0].status, "queued")
                        self.assertEqual(chat.state.exchanges_consumed, 0)
                    finally:
                        input.send_text("\x04")
                        await asyncio.wait_for(task, 3)

    def test_rendering_escapes_control_paths_and_contains_only_metadata(self) -> None:
        with create_pipe_input() as input:
            catalog = replace(self.catalog, workspace="/private/\x1b[31m\nproject")
            ui = ResumePicker(
                catalog, lambda: catalog, input=input, output=DummyOutput()
            )
            rendered = ui.header() + repr(ui.render_rows())
            self.assertIn("Café task", rendered)
            self.assertIn(self.catalog.sessions[0].session_id, rendered)
            self.assertNotIn(DEMO_PROMPTS[0], rendered)
            self.assertNotIn("\x1b", rendered)
            self.assertEqual(safe_label("\n\u202e"), "\\n\\u202e")


class PickerGuardTests(TestCase):
    def test_changed_selection_or_replaced_root_never_opens_controller(self) -> None:
        for sqlite in (False, True):
            for replace_root in (False, True):
                with (
                    self.subTest(sqlite=sqlite, replace_root=replace_root),
                    TemporaryDirectory() as directory,
                ):
                    root = Path(directory)
                    storage = root / "sessions"
                    backend = SQLiteConversationStore if sqlite else ConversationStore
                    state = ConversationController.fresh(root, demo_cassette())
                    with backend(storage, state.session_id, root) as store:
                        store.save(state)
                    catalog = resume_catalog(storage, root, sqlite=sqlite)
                    picked = ResumeSelection(
                        catalog.location, catalog.workspace, catalog.sessions[0]
                    )
                    if replace_root:
                        storage.rename(root / "previous")
                        storage.mkdir(mode=0o700)
                        with backend(storage, state.session_id, root) as store:
                            store.save(state)
                    else:
                        with backend(
                            storage, state.session_id, root, create=False
                        ) as store:
                            chat = ConversationController(
                                store.load(), demo_cassette(), store.save
                            )
                            chat.rename("Changed after selection")
                    parser = argparse.ArgumentParser()
                    add_commands(parser.add_subparsers(dest="command").add_parser)
                    args = parser.parse_args(
                        [
                            "resume",
                            "--storage",
                            str(storage),
                            "-C",
                            str(root),
                            "--storage-backend",
                            "sqlite" if sqlite else "snapshot",
                            "--json",
                            "--no-memory",
                        ]
                    )
                    with (
                        patch(
                            "mos_eisley.conversation_cli._choose_resume",
                            return_value=picked,
                        ),
                        patch(
                            "mos_eisley.conversation_cli.ConversationController",
                            side_effect=AssertionError("opened controller"),
                        ),
                    ):
                        if replace_root:
                            with self.assertRaises(ValueError):
                                run_command(args)
                        else:
                            self.assertEqual(run_command(args), 2)

    def test_real_picker_restores_terminal_and_leaves_queue_paused(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            storage = root / ".mos-eisley-sessions"
            state = ConversationController.fresh(root, demo_cassette())
            with ConversationStore(storage, state.session_id, root) as store:
                store.save(state)
                chat = ConversationController(state, demo_cassette(), store.save)
                chat.rename("Parser cleanup")
                chat.submit(DEMO_PROMPTS[0])
                before = canonical_bytes(chat.state)
            master, slave = pty.openpty()
            original = termios.tcgetattr(slave)
            process = subprocess.Popen(
                [sys.executable, "-m", "mos_eisley.cli", "resume", "-C", str(root)],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env={**os.environ, "TERM": "xterm-256color", "HOME": str(root)},
                start_new_session=True,
            )
            output = bytearray()

            def read_until(text: bytes) -> None:
                deadline = time.monotonic() + 10
                while text not in output:
                    if time.monotonic() >= deadline:
                        raise AssertionError(repr(output[-5000:]))
                    readable, _, _ = select.select([master], [], [], 0.1)
                    if readable:
                        data = os.read(master, 16384)
                        output.extend(data)
                        if b"\x1b[6n" in data:
                            os.write(master, b"\x1b[1;1R")

            try:
                read_until(b"Resume a saved session")
                read_until(b"Parser cleanup")
                os.write(master, b"parser\r")
                read_until(b"Directory:")
                os.write(master, b"\x04")
                read_until(b"conversation.saved")
                self.assertEqual(process.wait(timeout=5), 0)
                restored = termios.tcgetattr(slave)
                restored[3] &= ~getattr(termios, "PENDIN", 0)
                original[3] &= ~getattr(termios, "PENDIN", 0)
                self.assertEqual(restored, original)
                with ConversationStore(
                    storage, state.session_id, root, create=False
                ) as store:
                    self.assertEqual(canonical_bytes(store.load()), before)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                os.close(master)
                os.close(slave)
