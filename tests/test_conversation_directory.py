"""Directory selection admission, scoped startup and real terminal handoff."""

import argparse
import asyncio
import io
import os
import pty
import select
import subprocess
import sys
import termios
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import (
    DEMO_PROMPTS,
    add_commands,
    demo_cassette,
    run_command,
)
from mos_eisley.conversation_directory import (
    DirectoryCompleter,
    DirectoryPicker,
    DirectorySelection,
    DirectorySelectionError,
)
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore


async def until(predicate: Callable[[], bool]) -> None:
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.01)


class DirectoryTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "Project Café"
        self.project.mkdir()

    def test_symlinks_resolve_and_replacements_are_rejected(self) -> None:
        alias = self.root / "alias"
        alias.symlink_to(self.project, target_is_directory=True)
        selected = DirectorySelection.inspect(alias)
        self.assertEqual(selected.path, self.project)
        selected.verify()
        self.project.rename(self.root / "old")
        self.project.mkdir()
        with self.assertRaisesRegex(DirectorySelectionError, "changed"):
            selected.verify()

    def test_missing_files_loops_and_control_paths_fail_safely(self) -> None:
        file = self.root / "PRIVATE file"
        file.write_text("body must not be opened")
        loop = self.root / "PRIVATE loop"
        loop.symlink_to(loop)
        control = self.root / "PRIVATE\npath"
        control.mkdir()
        for candidate in (self.root / "PRIVATE missing", file, loop, control):
            with (
                self.subTest(candidate=repr(candidate)),
                self.assertRaises(DirectorySelectionError) as error,
            ):
                DirectorySelection.inspect(candidate)
            self.assertNotIn("PRIVATE", str(error.exception))

    def test_completion_is_directory_only_and_handles_dot_and_home(self) -> None:
        (self.root / "Project file").write_text("private")
        (self.root / "Project\ncontrol").mkdir()
        notices: list[str] = []
        completer = DirectoryCompleter(self.root, notices.append)

        def complete(text: str) -> list[str]:
            return [
                c.text
                for c in completer.get_completions(
                    Document(text, len(text)), CompleteEvent()
                )
            ]

        self.assertEqual(complete("Project"), ["Project Café/"])
        self.assertEqual(complete("."), ["/"])
        self.assertEqual(complete(".."), ["/"])
        with patch.dict(os.environ, {"HOME": str(self.root)}):
            self.assertEqual(complete("~"), ["/"])
        self.assertEqual(notices, [])

    def test_completion_bounds_refuse_partial_results(self) -> None:
        for name in ("a", "b", "c"):
            (self.root / name).mkdir()
        notices: list[str] = []
        completer = DirectoryCompleter(self.root, notices.append)
        document = Document(str(self.root) + "/", len(str(self.root)) + 1)
        for bound in ("MAX_COMPLETIONS", "MAX_DIRECTORY_ENTRIES"):
            with patch("mos_eisley.conversation_directory." + bound, 2):
                self.assertEqual(
                    list(completer.get_completions(document, CompleteEvent())), []
                )
        self.assertEqual(len(notices), 2)
        self.assertTrue(all("Type the path directly" in notice for notice in notices))

    def test_cli_noninteractive_rejection_precedes_any_storage(self) -> None:
        for command, flags in (
            ("chat", ()),
            ("resume", ("--last",)),
            ("chat", ("--plain",)),
            ("chat", ("--json",)),
        ):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    command,
                    "--choose-directory",
                    *flags,
                ],
                input="",
                text=True,
                capture_output=True,
                timeout=15,
                env={**os.environ, "HOME": str(self.root)},
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("use -C PATH", result.stderr)
            self.assertFalse((self.root / ".mos-eisley-sessions").exists())
            self.assertFalse((self.root / ".mos-eisley-memory").exists())

    def args(self, *values: str) -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        add_commands(parser.add_subparsers(dest="command").add_parser)
        return parser.parse_args(list(values))

    @contextmanager
    def terminal(self, selection: DirectorySelection | None) -> Generator[None]:
        with (
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
            patch("mos_eisley.conversation_cli.sys.stdin.isatty", return_value=True),
            patch("mos_eisley.conversation_cli.sys.stdout.isatty", return_value=True),
            patch("mos_eisley.conversation_cli.pick_directory", return_value=selection),
            patch("mos_eisley.conversation_cli.termios.tcgetattr", return_value=[]),
            patch("mos_eisley.conversation_cli.termios.tcsetattr"),
            patch("mos_eisley.conversation_tui.ConversationTUI") as ui,
        ):
            ui.return_value.run = AsyncMock(return_value=None)
            yield

    def test_cancellation_does_not_read_memory_or_create_session(self) -> None:
        args = self.args(
            "chat", "--choose-directory", "--storage", str(self.root / "sessions")
        )
        with (
            self.terminal(None),
            patch(
                "mos_eisley.conversation_cli.MemoryStore",
                side_effect=AssertionError("memory read"),
            ),
        ):
            self.assertEqual(run_command(args), 0)
        self.assertFalse((self.root / "sessions").exists())

    def test_chat_selects_project_memory_and_resume_keeps_queue_paused(self) -> None:
        memory_root = self.root / "memory"
        other = MemoryStore(memory_root, self.root)
        other.change("user", "set", text="Shared user preference")
        other.change("project", "set", text="OTHER PROJECT PRIVATE")
        selected_memory = MemoryStore(memory_root, self.project)
        selected_memory.change("project", "set", text="Chosen project preference")
        selected = DirectorySelection.inspect(self.project)
        for backend in ("snapshot", "sqlite"):
            storage = self.root / backend
            options = (
                "--choose-directory",
                "--storage",
                str(storage),
                "--memory-storage",
                str(memory_root),
                "--storage-backend",
                backend,
            )
            args = self.args(
                "chat", "-C", str(self.root), "--name", "Chosen work", *options
            )
            with self.terminal(selected):
                self.assertEqual(run_command(args), 0)
            self.assertEqual(args.workspace, self.project)
            sid = next(p.stem for p in storage.glob("*.lock") if len(p.stem) == 32)
            store_type = (
                SQLiteConversationStore if backend == "sqlite" else ConversationStore
            )
            with store_type(storage, sid, self.project, create=False) as store:
                state = store.load()
                self.assertEqual(state.memory, selected_memory.load())
                self.assertNotIn("OTHER PROJECT PRIVATE", state.model_dump_json())
                self.assertEqual(state.session_name, "Chosen work")
                cassette = demo_cassette(memory=state.memory)
                chat = ConversationController(state, cassette, store.save)
                chat.submit(DEMO_PROMPTS[0])
                before = canonical_bytes(chat.state)
            resumed = self.args("resume", "--name", "Chosen work", *options)
            with self.terminal(selected):
                self.assertEqual(run_command(resumed), 0)
            with store_type(storage, sid, self.project, create=False) as store:
                self.assertEqual(canonical_bytes(store.load()), before)
            wrong = self.args("resume", sid, *options)
            with (
                self.terminal(DirectorySelection.inspect(self.root)),
                self.assertRaises(ValueError),
            ):
                run_command(wrong)

    def test_changed_directory_fails_before_memory_and_storage(self) -> None:
        selected = DirectorySelection.inspect(self.project)
        self.project.rename(self.root / "old")
        self.project.mkdir()
        args = self.args(
            "chat", "--choose-directory", "--storage", str(self.root / "sessions")
        )
        with (
            self.terminal(selected),
            patch(
                "mos_eisley.conversation_cli.MemoryStore",
                side_effect=AssertionError("memory read"),
            ),
        ):
            self.assertEqual(run_command(args), 2)
        self.assertFalse((self.root / "sessions").exists())


class DirectoryKeyboardTests(IsolatedAsyncioTestCase):
    async def test_tab_completion_applies_a_directory_then_previews(self) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            root = Path(directory).resolve()
            project = root / "Project Café"
            project.mkdir()
            ui = DirectoryPicker(root, input=input, output=DummyOutput())
            ui.editor.set_document(Document(str(root) + "/Pro", len(str(root)) + 4))
            task = asyncio.create_task(ui.app.run_async())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("\t")
                await until(lambda: ui.editor.complete_state is not None)
                input.send_text("\t")
                await until(lambda: ui.editor.text == str(project) + "/")
                input.send_text("\r")
                await until(lambda: ui.selection is not None)
                self.assertIn(str(project), ui.details())
                input.send_text("\x1bOQ")
                await until(lambda: ui.app.layout.has_focus(ui.preview_area))
                input.send_text("\x1bOQ")
                await until(lambda: not ui.app.layout.has_focus(ui.preview_area))
                input.send_text("\x04")
                self.assertIsNone(await asyncio.wait_for(task, 3))
            finally:
                if not task.done():
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)

    async def test_edit_requires_new_preview_and_changed_target_cannot_select(
        self,
    ) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            ui = DirectoryPicker(project, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.app.run_async())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("\x13")
                await until(lambda: "Press Enter" in ui.notice)
                self.assertFalse(task.done())
                input.send_text("\r")
                await until(lambda: ui.selection is not None)
                self.assertIn(str(project.resolve()), ui.details())
                input.send_text("/")
                await until(lambda: ui.selection is None)
                input.send_text("\r")
                await until(lambda: ui.selection is not None)
                project.rename(root / "old")
                project.mkdir()
                input.send_text("\x13")
                await until(lambda: "changed" in ui.notice)
                self.assertIsNone(ui.selection)
                input.send_text("\r\x13")
                result = await asyncio.wait_for(task, 3)
                assert result is not None
                self.assertEqual(result.path, project.resolve())
            finally:
                if not task.done():
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)

    async def test_invalid_paste_and_path_bounds_are_not_saved_or_displayed(
        self,
    ) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            ui = DirectoryPicker(Path(directory), input=input, output=DummyOutput())
            task = asyncio.create_task(ui.app.run_async())
            try:
                await until(lambda: ui.app.is_running)
                before = ui.editor.text
                input.send_text("\x1b[200~PRIVATE\nPATH\x1b[201~")
                await until(lambda: "single printable" in ui.notice)
                self.assertEqual(ui.editor.text, before)
                self.assertNotIn("PRIVATE", ui.notice)
                ui.editor.set_document(Document("é" * 2049))
                self.assertEqual(ui.editor.text, before)
                for _ in range(40):
                    ui.editor.save_to_undo_stack()
                    ui.editor.insert_text("x")
                self.assertLessEqual(len(ui.editor.undo_documents), 32)
                ui.editor.undo()
                ui.editor.redo()
                input.send_text("\x04")
                self.assertIsNone(await asyncio.wait_for(task, 3))
            finally:
                if not task.done():
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)


class DirectoryPTYTests(TestCase):
    def test_real_startup_selection_and_cancel_restore_terminal(self) -> None:
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                self.check_terminal(cancel=cancel)

    def test_real_directory_to_resume_picker_handoff(self) -> None:
        self.check_terminal(cancel=False, resume=True)

    def check_terminal(self, *, cancel: bool, resume: bool = False) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            project = root / "selected project"
            project.mkdir()
            storage = root / ".mos-eisley-sessions"
            before: bytes | None = None
            if resume:
                state = ConversationController.fresh(project, demo_cassette())
                with ConversationStore(storage, state.session_id, project) as store:
                    store.save(state)
                    chat = ConversationController(state, demo_cassette(), store.save)
                    chat.rename("Directory resume")
                    chat.submit(DEMO_PROMPTS[0])
                    before = canonical_bytes(chat.state)
            master, slave = pty.openpty()
            original = termios.tcgetattr(slave)
            arguments = ["resume"] if resume else []
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    *arguments,
                    "--choose-directory",
                ],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=root,
                env={**os.environ, "HOME": str(root), "TERM": "xterm-256color"},
                start_new_session=True,
            )
            output = bytearray()

            def read_until(text: bytes) -> None:
                deadline = time.monotonic() + 10
                while text not in output:
                    if time.monotonic() > deadline:
                        raise AssertionError(repr(output[-5000:]))
                    readable, _, _ = select.select([master], [], [], 0.1)
                    if readable:
                        data = os.read(master, 16384)
                        output.extend(data)
                        if b"\x1b[6n" in data:
                            os.write(master, b"\x1b[1;1R")

            try:
                read_until(b"Choose a session directory")
                if cancel:
                    os.write(master, b"\x04")
                    read_until(b"\x1b[?1049l")
                else:
                    os.write(master, b"\x15selected project\r")
                    read_until(b"preview is ready")
                    os.write(master, b"\x13")
                    if resume:
                        read_until(b"Resume a saved session")
                        read_until(b"Directory resume")
                        os.write(master, b"\r")
                    read_until(b"Directory:")
                    os.write(master, b"\x04")
                    read_until(b"conversation.saved")
                self.assertEqual(process.wait(timeout=5), 0)
                restored = termios.tcgetattr(slave)
                restored[3] &= ~getattr(termios, "PENDIN", 0)
                original[3] &= ~getattr(termios, "PENDIN", 0)
                self.assertEqual(restored, original)
                if cancel:
                    self.assertFalse(storage.exists())
                else:
                    snapshot = ConversationSnapshot.model_validate_json(
                        next(storage.glob("*.json")).read_bytes()
                    )
                    self.assertEqual(snapshot.state.workspace, str(project))
                    if before is not None:
                        self.assertEqual(canonical_bytes(snapshot.state), before)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                os.close(master)
                os.close(slave)
