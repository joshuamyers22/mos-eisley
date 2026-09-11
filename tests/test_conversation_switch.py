"""Directory handoff keeps saved intent separate from fresh project context."""

import asyncio
import os
import pty
import select
import subprocess
import sys
import termios
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import Input, create_pipe_input
from prompt_toolkit.output import DummyOutput, Output

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette, terminal
from mos_eisley.conversation_directory import DirectoryPicker, DirectorySelectionError
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.conversation_switch import switch_target
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes
from mos_eisley.demo import demo_inputs
from mos_eisley.run.conversation_sqlite import (
    SQLiteConversationStore,
    list_sqlite_conversations,
)
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore


async def until(predicate: Callable[[], bool]) -> None:
    async with asyncio.timeout(5):
        while not predicate():
            await asyncio.sleep(0.01)


class SwitchTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.target = self.root / "target"
        self.target.mkdir()
        cassette = demo_cassette()
        self.chat = ConversationController(
            ConversationController.fresh(self.root, cassette),
            cassette,
            lambda state: None,
        )

    async def test_explicit_switch_preserves_pending_entries_and_attempts(self) -> None:
        self.chat.rename("Source session")
        self.chat.submit(DEMO_PROMPTS[0])
        before = canonical_bytes(self.chat.state)
        with create_pipe_input() as input:
            ui = ConversationTUI(
                self.chat,
                allow_directory_switch=True,
                input=input,
                output=DummyOutput(),
            )
            task = asyncio.create_task(ui.run())
            await until(lambda: ui.app.is_running)
            input.send_text("/directory switch target\r")
            await asyncio.wait_for(task, 5)
            assert ui.directory_target is not None
            self.assertEqual(ui.directory_target.path, self.target)
            self.assertEqual(canonical_bytes(self.chat.state), before)
            self.assertEqual(self.chat.state.exchanges_consumed, 0)

    async def test_picker_cancel_keeps_original_controller_and_lock(self) -> None:
        storage = self.root / "sessions"
        with ConversationStore(storage, self.chat.state.session_id, self.root) as store:
            store.save(self.chat.state)
            chat = ConversationController(store.load(), demo_cassette(), store.save)
            chat.submit(DEMO_PROMPTS[0])
            before = canonical_bytes(chat.state)
            pickers: list[DirectoryPicker] = []

            def factory(
                initial: Path, *, base: Path, input: Input, output: Output
            ) -> DirectoryPicker:
                picker = DirectoryPicker(initial, base=base, input=input, output=output)
                pickers.append(picker)
                return picker

            with (
                create_pipe_input() as input,
                patch(
                    "mos_eisley.conversation_tui.DirectoryPicker", side_effect=factory
                ),
            ):
                ui = ConversationTUI(
                    chat, allow_directory_switch=True, input=input, output=DummyOutput()
                )
                task = asyncio.create_task(ui.run())
                try:
                    await until(lambda: ui.app.is_running)
                    input.send_text("\x1b[20~")  # F9
                    await until(lambda: bool(pickers) and pickers[0].app.is_running)
                    with self.assertRaises(BlockingIOError):
                        ConversationStore(
                            storage, chat.state.session_id, self.root, create=False
                        )
                    input.send_text("\x04")
                    await until(lambda: "cancelled" in ui.notice)
                    self.assertIs(ui.controller, chat)
                    self.assertIsNone(ui.directory_target)
                    self.assertEqual(canonical_bytes(chat.state), before)
                    input.send_text("\x1b[20~")
                    await until(lambda: len(pickers) == 2 and pickers[1].app.is_running)
                    ui.queue.put_nowait("/directory")
                    input.send_text("\x15target\r\x13")
                    await until(
                        lambda: not pickers[1].app.is_running and not ui.sending
                    )
                    self.assertIsNone(ui.directory_target)
                    self.assertEqual(canonical_bytes(chat.state), before)
                finally:
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 5)

    async def test_unsent_draft_and_pending_input_block_switch(self) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(
                self.chat,
                allow_directory_switch=True,
                input=input,
                output=DummyOutput(),
            )
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("PRIVATE DRAFT\x1b[20~")
                await until(lambda: "unsent draft" in ui.notice)
                self.assertEqual(ui.editor.text, "PRIVATE DRAFT")
                self.assertIsNone(ui.directory_target)
                self.assertFalse(await ui.switch_directory("/directory switch target"))
                ui.editor.clear()
                ui.queue.put_nowait("/directory")
                self.assertFalse(await ui.switch_directory("/directory switch target"))
                self.assertEqual(self.chat.state.entries, ())
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 5)

    async def test_active_request_must_be_stopped_explicitly(self) -> None:
        from test_conversation import WaitingClient

        client = WaitingClient()
        original = self.chat.step

        async def waiting(*, on_started: Callable[[], None] | None = None) -> bool:
            return await original(client, on_started=on_started)

        with (
            create_pipe_input() as input,
            patch.object(self.chat, "step", side_effect=waiting),
        ):
            ui = ConversationTUI(
                self.chat,
                allow_directory_switch=True,
                input=input,
                output=DummyOutput(),
            )
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text(DEMO_PROMPTS[0] + "\r")
                await asyncio.wait_for(client.started.wait(), 5)
                await until(lambda: not ui.sending)
                input.send_text("/directory switch target\r")
                await until(lambda: "Stop active work" in ui.notice)
                self.assertEqual(self.chat.state.entries[0].status, "running")
                self.assertIsNone(ui.directory_target)
                input.send_text("\x03")
                await until(lambda: self.chat.state.entries[0].status == "cancelled")
                input.send_text("/directory switch target\r")
                await asyncio.wait_for(task, 5)
                self.assertIsNotNone(ui.directory_target)
            finally:
                if not task.done():
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 5)

    async def test_invalid_or_same_directory_keeps_session_usable(self) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(
                self.chat,
                allow_directory_switch=True,
                input=input,
                output=DummyOutput(),
            )
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("/directory switch missing\r")
                await until(lambda: "existing directory" in ui.notice)
                self.assertFalse(ui.sending)
                input.send_text("/directory switch .\r")
                await until(lambda: "Already in" in ui.notice)
                self.assertIsNone(ui.directory_target)
                input.send_text(DEMO_PROMPTS[0] + "\r")
                await until(
                    lambda: (
                        bool(self.chat.state.entries)
                        and self.chat.state.entries[0].status == "completed"
                    )
                )
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 5)

    async def test_pasted_switch_text_is_literal_and_plain_mode_is_unavailable(
        self,
    ) -> None:
        with create_pipe_input() as input:
            ui = ConversationTUI(
                self.chat,
                allow_directory_switch=True,
                input=input,
                output=DummyOutput(),
            )
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("\x1b[200~/directory switch target\x1b[201~\r")
                await until(lambda: bool(self.chat.state.entries))
                self.assertEqual(
                    self.chat.state.entries[0].text, "/directory switch target"
                )
                self.assertIsNone(ui.directory_target)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 5)
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        queue.put_nowait("/directory switch target")
        queue.put_nowait("/quit")
        events: list[dict[str, object]] = []
        await terminal(self.chat, queue, events.append)
        self.assertTrue(
            any("interactive terminal" in str(e.get("text")) for e in events)
        )


class SwitchContractTests(TestCase):
    def test_relative_paths_and_aliases_resolve_from_session_workspace(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "target with spaces "
            target.mkdir()
            (root / "alias").symlink_to(target, target_is_directory=True)
            selected = switch_target("/directory switch alias", root)
            assert selected is not None
            self.assertEqual(selected.path, target)
            self.assertEqual(
                switch_target("/directory switch target with spaces ", root), selected
            )
            self.assertIsNone(switch_target("/directory switch", root))
            for line in (
                "/directory switch PRIVATE\npath",
                "/directory switch ",
                "/other",
            ):
                with self.assertRaises(DirectorySelectionError):
                    switch_target(line, root)

    def test_real_switch_opens_fresh_scoped_session_on_both_backends(self) -> None:
        for backend in ("snapshot", "sqlite"):
            with self.subTest(backend=backend):
                self.check_terminal(backend)

    def check_terminal(self, backend: str) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, target = root / "source", root / "target"
            source.mkdir()
            target.mkdir()
            memory_root = root / "memory"
            a = MemoryStore(memory_root, source)
            a.change("user", "set", text="Shared preference")
            a.change("project", "set", text="SOURCE PROJECT PRIVATE")
            b = MemoryStore(memory_root, target)
            b.change("project", "set", text="Target project preference")
            recording = root / "source-recording.json"
            recording.write_bytes(canonical_bytes(demo_cassette(memory=a.load())))
            brief, cassette = demo_inputs()
            packet = root / "source-review.json"
            packet.write_bytes(
                canonical_bytes(
                    ConversationReviewPacket(brief=brief, cassette=cassette)
                )
            )
            storage = root / "sessions"
            master, slave = pty.openpty()
            original_modes = termios.tcgetattr(slave)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "chat",
                    "-C",
                    str(source),
                    "--storage",
                    str(storage),
                    "--storage-backend",
                    backend,
                    "--memory-storage",
                    str(memory_root),
                    "--name",
                    "Source name",
                    "--cassette",
                    str(recording),
                    "--review-packet",
                    str(packet),
                    DEMO_PROMPTS[0],
                ],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=root,
                env={**os.environ, "HOME": str(root), "TERM": "xterm-256color"},
                start_new_session=True,
            )
            output = bytearray()

            def completed(workspace: Path) -> bool:
                try:
                    if backend == "sqlite":
                        rows = list_sqlite_conversations(storage, workspace).sessions
                        return bool(rows) and rows[0].completed == 1
                    for path in storage.glob("*.json"):
                        state = ConversationSnapshot.model_validate_json(
                            path.read_bytes()
                        ).state
                        if (
                            state.workspace == str(workspace)
                            and state.entries
                            and state.entries[0].status == "completed"
                        ):
                            return True
                except (OSError, ValueError):
                    return False
                return False

            def read_until(
                text: bytes, ready: Callable[[], bool] = lambda: True
            ) -> None:
                deadline = time.monotonic() + 15
                while text not in output or not ready():
                    if time.monotonic() >= deadline:
                        raise AssertionError(repr(output[-5000:]))
                    readable, _, _ = select.select([master], [], [], 0.1)
                    if readable:
                        data = os.read(master, 16384)
                        output.extend(data)
                        if b"\x1b[6n" in data:
                            os.write(master, b"\x1b[1;1R")

            try:
                read_until(b"Directory:", lambda: completed(source))
                os.write(master, b"/directory switch\r")
                read_until(b"Choose a session directory")
                os.write(master, b"\x15../target\r")
                read_until(b"preview is ready")
                output.clear()
                os.write(master, b"\x13")
                read_until(b"conversation.saved")
                read_until(
                    b"Directory:",
                    lambda: (
                        output.rfind(b"Directory:") > output.find(b"conversation.saved")
                    ),
                )
                os.write(master, (DEMO_PROMPTS[0] + "\r").encode())
                read_until(b"Directory:", lambda: completed(target))
                output.clear()
                os.write(master, b"/review\r")
                read_until(b"/review")
                # A full repaint makes the notice independent of the terminal's
                # differential cursor movements and reused characters.
                os.write(master, b"\x0c")
                read_until(b"Review requires an explicit")
                output.clear()
                os.write(master, b"\x04")
                read_until(b"conversation.saved")
                self.assertEqual(process.wait(timeout=5), 0)
                store_type = (
                    SQLiteConversationStore
                    if backend == "sqlite"
                    else ConversationStore
                )
                states: list[ConversationState] = []
                for path in storage.glob("*.lock"):
                    if len(path.stem) != 32:
                        continue
                    for workspace in (source, target):
                        try:
                            with store_type(
                                storage, path.stem, workspace, create=False
                            ) as store:
                                states.append(store.load())
                        except ValueError:
                            pass
                self.assertEqual(len(states), 2)
                first = next(s for s in states if s.workspace == str(source))
                second = next(s for s in states if s.workspace == str(target))
                self.assertEqual(first.session_name, "Source name")
                self.assertIsNone(second.session_name)
                self.assertNotEqual(first.session_id, second.session_id)
                self.assertEqual(second.memory, b.load())
                self.assertNotIn("SOURCE PROJECT PRIVATE", second.model_dump_json())
                self.assertEqual(len(first.entries), 1)
                self.assertEqual(len(second.entries), 1)
                self.assertEqual(second.exchanges_consumed, 1)
                restored = termios.tcgetattr(slave)
                restored[3] &= ~getattr(termios, "PENDIN", 0)
                original_modes[3] &= ~getattr(termios, "PENDIN", 0)
                self.assertEqual(restored, original_modes)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                os.close(master)
                os.close(slave)
