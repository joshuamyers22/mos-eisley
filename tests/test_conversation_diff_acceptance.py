"""Terminal and race acceptance for the bounded conversation diff panel."""

import asyncio
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import threading
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_git import GitSnapshot, GitState
from mos_eisley.conversation_state import LiveChatIdentity
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.agent import AgentConfig, AgentResult

GIT = Path("/usr/bin/git")


def git(root: Path, *args: str) -> None:
    subprocess.run([str(GIT), *args], cwd=root, check=True, capture_output=True)


def changed_workspace(root: Path) -> Path:
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    (root / "one.txt").write_text("before\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    (root / "one.txt").write_text("after\n")
    return root


async def until(predicate: Callable[[], bool], timeout: float = 8) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.02)


class DiffAcceptanceTests(IsolatedAsyncioTestCase):
    async def test_live_destination_is_shown_without_dispatch_on_first_send(
        self,
    ) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            root = changed_workspace(Path(directory) / "source")
            cassette = demo_cassette()
            identity = LiveChatIdentity(
                model="gpt-5.6-luna",
                effort="medium",
                max_output_tokens=128,
                spend_policy_sha256="1" * 64,
                spend_ledger_id="2" * 64,
                artifacts_root=str(root),
            )
            dispatched = False

            async def run_live(_config: AgentConfig, _attempt: int) -> AgentResult:
                nonlocal dispatched
                dispatched = True
                raise AssertionError("attachment preview must not dispatch")

            chat = ConversationController(
                ConversationController.fresh(root, cassette, live_chat=identity),
                cassette,
                lambda _: None,
                run_live_chat=run_live,
            )
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("/diff\r")
                await until(lambda: ui.diff_patch is not None)
                ui.app.layout.focus(ui.diff_content)
                ui.diff_content.buffer.cursor_position = ui.diff_content.text.index(
                    "+after"
                )
                input.send_text("\x1b[24~")
                await until(lambda: bool(ui.diff_attachments))
                ui.app.layout.focus(ui.editor_control)
                ui.editor.insert_text("Explain")
                input.send_text("\r")
                await until(lambda: ui.attachment_send_review is not None)
                self.assertIn(
                    "OpenAI live chat • model gpt-5.6-luna • effort medium",
                    ui.attachment_review.text,
                )
                self.assertIn(
                    "separately selected policy and cap", ui.attachment_review.text
                )
                self.assertFalse(dispatched)
                self.assertEqual(chat.state.entries, ())
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 5)

    async def test_send_reviews_exact_destination_and_rebinds_draft(self) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            root = changed_workspace(Path(directory) / "source")
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(root, cassette), cassette, lambda _: None
            )
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("/diff\r")
                await until(lambda: ui.diff_patch is not None)
                ui.app.layout.focus(ui.diff_content)
                ui.diff_content.buffer.cursor_position = ui.diff_content.text.index(
                    "+after"
                )
                input.send_text("\x1b[24~")
                await until(lambda: bool(ui.diff_attachments))
                frozen = ui.diff_attachments[0]
                ui.app.layout.focus(ui.editor_control)
                ui.editor.insert_text("Explain this line")
                input.send_text("\r")
                await until(lambda: ui.attachment_send_review is not None)
                self.assertEqual(chat.state.entries, ())
                self.assertIn("Recorded local chat", ui.attachment_review.text)
                self.assertIn("No Git edit, tool, review", ui.attachment_review.text)
                self.assertIn(
                    json.dumps(frozen.excerpt, ensure_ascii=True),
                    ui.attachment_review.text,
                )
                self.assertTrue(ui.app.layout.has_focus(ui.attachment_review))

                input.send_text("\x07")  # Ctrl-G cancels without discarding.
                await until(lambda: ui.attachment_send_review is None)
                self.assertEqual(ui.editor.text, "Explain this line")
                self.assertEqual(ui.diff_attachments, [frozen])
                self.assertEqual(chat.state.entries, ())

                input.send_text("\r")
                await until(lambda: ui.attachment_send_review is not None)
                input.send_text("\t")
                await until(lambda: ui.app.layout.has_focus(ui.editor_control))
                ui.editor.insert_text(" please")
                input.send_text("\r")
                await until(
                    lambda: (
                        ui.attachment_send_review is not None
                        and ui.attachment_send_review[0] == "Explain this line please"
                    )
                )
                self.assertEqual(chat.state.entries, ())
                self.assertIn(
                    json.dumps("Explain this line please"),
                    ui.attachment_review.text,
                )
                input.send_text("\r")
                await until(
                    lambda: bool(chat.state.entries) and not ui.diff_attachments
                )
                self.assertEqual(chat.state.entries[0].diff_attachments, (frozen,))
                self.assertTrue(
                    chat.state.entries[0].text.startswith("Explain this line please")
                )
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 5)

    async def test_mouse_range_selects_exact_hunk_lines(self) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            root = changed_workspace(Path(directory) / "source")
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(root, cassette), cassette, lambda _: None
            )
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("/diff\r")
                await until(lambda: ui.diff_patch is not None)
                ui.app.layout.focus(ui.diff_content)
                ui.app.invalidate()
                data = ui.diff_content.text
                removed = next(
                    i for i, line in enumerate(data.splitlines()) if line == "-before"
                )
                added = removed + 1

                # A render_info object can precede the patch's screen map.
                # Wait for both coordinates before sending actual mouse events.
                def patch_coordinates_ready() -> bool:
                    info = ui.diff_content.window.render_info
                    return info is not None and (
                        (removed, 0) in info._rowcol_to_yx  # pyright: ignore[reportPrivateUsage]
                        and (added, len("+after")) in info._rowcol_to_yx  # pyright: ignore[reportPrivateUsage]
                    )

                await until(patch_coordinates_ready)
                info = ui.diff_content.window.render_info
                assert info is not None
                # The renderer's exact screen map is needed to exercise mouse input.
                start_y, start_x = info._rowcol_to_yx[removed, 0]  # pyright: ignore[reportPrivateUsage]
                end_y, end_x = info._rowcol_to_yx[added, len("+after")]  # pyright: ignore[reportPrivateUsage]
                input.send_text(f"\x1b[<0;{start_x + 1};{start_y + 1}M")
                input.send_text(f"\x1b[<32;{end_x + 1};{end_y + 1}M")
                input.send_text(f"\x1b[<0;{end_x + 1};{end_y + 1}m")
                await until(lambda: ui.diff_content.buffer.selection_state is not None)
                input.send_text("\x1b[24~")
                await until(lambda: bool(ui.diff_attachments))
                item = ui.diff_attachments[0]
                self.assertEqual(item.excerpt.encode(), b"-before\n+after\n")
                self.assertEqual((item.old_start, item.old_end), (1, 1))
                self.assertEqual((item.new_start, item.new_end), (1, 1))
                self.assertEqual(chat.state.entries, ())
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 5)

    async def test_rapid_refresh_keeps_frozen_attachment_and_latest_patch(self) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            root = changed_workspace(Path(directory) / "source")
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(root, cassette), cassette, lambda _: None
            )
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("/diff\r")
                await until(lambda: ui.diff_patch is not None)
                ui.app.layout.focus(ui.diff_content)
                ui.diff_content.buffer.cursor_position = ui.diff_content.text.index(
                    "+after"
                )
                input.send_text("\x1b[24~")
                await until(lambda: bool(ui.diff_attachments))
                frozen = ui.diff_attachments[0]
                ui.app.layout.focus(ui.editor_control)
                ui.editor.insert_text("Explain")
                for value in ("middle", "latest"):
                    (root / "one.txt").write_text(value + "\n")
                    ui.diff_wakeup.set()
                await until(
                    lambda: (
                        ui.diff_patch is not None and b"+latest" in ui.diff_patch.data
                    )
                )
                self.assertEqual(frozen.excerpt, "+after\n")
                self.assertIn("changed", ui.attachment_preview())
                ui.send()
                self.assertIsNotNone(ui.attachment_send_review)
                ui.send(literal=True)
                await until(lambda: not ui.sending)
                self.assertEqual(chat.state.entries, ())
                self.assertEqual(ui.editor.text, "Explain")
                self.assertEqual(ui.diff_attachments, [frozen])
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 5)

    async def test_rapid_refresh_coalesces_without_overlapping_git_reads(self) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            root = changed_workspace(Path(directory) / "source")
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(root, cassette), cassette, lambda _: None
            )
            entered = threading.Event()
            release = threading.Event()
            counter_lock = threading.Lock()
            active = 0
            maximum_active = 0
            reads = 0

            class SlowReader:
                def __init__(self, selection: object, git_executable: object) -> None:
                    pass

                def snapshot(self) -> GitSnapshot:
                    nonlocal active, maximum_active, reads
                    with counter_lock:
                        active += 1
                        maximum_active = max(maximum_active, active)
                        reads += 1
                        read_number = reads
                    content = (root / "one.txt").read_text().strip()
                    try:
                        if read_number == 1:
                            entered.set()
                            if not release.wait(5):
                                raise TimeoutError("held Git read was not released")
                        return GitSnapshot(
                            GitState.READY, root, root, (), content, True
                        )
                    finally:
                        with counter_lock:
                            active -= 1

            with patch("mos_eisley.conversation_tui.GitWorkspaceReader", SlowReader):
                ui = ConversationTUI(chat, input=input, output=DummyOutput())
                task = asyncio.create_task(ui.run())
                try:
                    await until(lambda: ui.app.is_running)
                    input.send_text("/diff\r")
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    for index in range(8):
                        (root / "one.txt").write_text(f"version-{index}\n")
                        if index % 2 == 0:
                            ui.toggle_diff()
                            ui.toggle_diff()
                        else:
                            ui.restart_diff_poll()
                        await asyncio.sleep(0.01)
                    self.assertIsNone(ui.diff_snapshot)
                    self.assertEqual(reads, 1)
                    self.assertEqual(maximum_active, 1)
                    release.set()
                    await until(
                        lambda: (
                            ui.diff_snapshot is not None
                            and ui.diff_snapshot.digest == "version-7"
                        )
                    )
                    self.assertEqual(reads, 2)
                    self.assertEqual(maximum_active, 1)
                finally:
                    release.set()
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 5)

    async def test_switch_blocks_attached_source_and_discards_old_generation(
        self,
    ) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            base = Path(directory)
            root = changed_workspace(base / "source")
            target = base / "target"
            target.mkdir()
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(root, cassette), cassette, lambda _: None
            )
            ui = ConversationTUI(
                chat, allow_directory_switch=True, input=input, output=DummyOutput()
            )
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("/diff\r")
                await until(lambda: ui.diff_patch is not None)
                ui.app.layout.focus(ui.diff_content)
                ui.diff_content.buffer.cursor_position = ui.diff_content.text.index(
                    "+after"
                )
                input.send_text("\x1b[24~")
                await until(lambda: bool(ui.diff_attachments))
                self.assertFalse(
                    await ui.switch_directory(f"/directory switch {target}")
                )
                self.assertIsNone(ui.directory_target)
                self.assertEqual(len(ui.diff_attachments), 1)
                ui.diff_attachments.clear()
                ui.restart_diff_poll()
                entered = threading.Event()
                release = threading.Event()

                class SlowReader:
                    def __init__(
                        self, selection: object, git_executable: object
                    ) -> None:
                        pass

                    def snapshot(self) -> GitSnapshot:
                        entered.set()
                        release.wait(3)
                        return GitSnapshot(GitState.NON_GIT, root, None, (), "", True)

                with patch(
                    "mos_eisley.conversation_tui.GitWorkspaceReader", SlowReader
                ):
                    ui.restart_diff_poll()
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    self.assertTrue(ui.control(f"/directory switch {target}"))
                    await until(lambda: ui.directory_target is not None)
                    release.set()
                    await asyncio.sleep(0.05)
                assert ui.directory_target is not None
                self.assertEqual(ui.directory_target.path, target.resolve())
                self.assertFalse(ui.diff_visible)
                if ui.diff_snapshot is not None:
                    self.assertNotEqual(ui.diff_snapshot.state, GitState.NON_GIT)
                self.assertEqual(chat.state.entries, ())
            finally:
                if ui.directory_target is None:
                    input.send_text("\x04")
                await asyncio.wait_for(task, 5)


class DiffPTYTests(TestCase):
    def test_real_pty_attach_resize_remove_and_close(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root = changed_workspace(base / "source")
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "chat",
                    "-C",
                    str(root),
                    "--storage",
                    str(base / "sessions"),
                ],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=root,
                env={**os.environ, "HOME": str(base), "TERM": "xterm-256color"},
                start_new_session=True,
            )
            output = bytearray()

            def rendered_text() -> bytes:
                return re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]", b"", output)

            def read_until(needle: bytes) -> None:
                deadline = time.monotonic() + 15
                while needle not in rendered_text():
                    if time.monotonic() > deadline:
                        raise AssertionError(repr(output[-3000:]))
                    readable, _, _ = select.select([master], [], [], 0.1)
                    if readable:
                        data = os.read(master, 16384)
                        output.extend(data)
                        if b"\x1b[6n" in data:
                            os.write(master, b"\x1b[1;1R")

            try:
                read_until(b"Message")
                os.write(master, b"/diff\r")
                read_until(b"+after")
                output.clear()
                os.write(master, b"\t\t\t" + b"\x1b[B" * 6 + b"\x1b[24~")
                read_until(b"Frozen diff li")
                fcntl.ioctl(
                    slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 80, 0, 0)
                )
                os.kill(process.pid, signal.SIGWINCH)
                output.clear()
                os.write(master, b"\x0c")
                read_until(b"snapshot")
                output.clear()
                os.write(master, b"\x18")  # Ctrl-X
                read_until(b"Latest")
                output.clear()
                os.write(master, b"\x1b[21~")  # F10
                read_until(b"Diff panel clos")
                os.write(master, b"\x04")
                deadline = time.monotonic() + 10
                while process.poll() is None and time.monotonic() < deadline:
                    readable, _, _ = select.select([master], [], [], 0.1)
                    if readable:
                        try:
                            data = os.read(master, 16384)
                        except OSError:
                            break
                        if b"\x1b[6n" in data:
                            os.write(master, b"\x1b[1;1R")
                self.assertEqual(process.wait(timeout=1), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                os.close(master)
                os.close(slave)
