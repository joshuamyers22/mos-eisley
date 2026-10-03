"""The conversation diff panel uses bounded Git data without changing the chat."""

import asyncio
import subprocess
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_diff_panel import (
    RENDER_LINE_LIMITS,
    inventory_text,
    items,
    patch_text,
)
from mos_eisley.conversation_git import (
    Change,
    ChangeKind,
    DiffBasis,
    GitSnapshot,
    GitState,
    Patch,
)
from mos_eisley.conversation_tui import ConversationTUI

GIT = Path("/usr/bin/git")


def command(root: Path, *args: str) -> None:
    subprocess.run([str(GIT), *args], cwd=root, check=True, capture_output=True)


class DiffPresentationTests(TestCase):
    def test_staged_unstaged_untracked_and_partial_patch_are_labeled(self) -> None:
        changes = (
            Change("a.py", ChangeKind.TRACKED, "M", "M", None, 2, 1, 3, 0),
            Change("later.py", ChangeKind.UNTRACKED),
        )
        snapshot = GitSnapshot(
            GitState.READY,
            Path("/tmp"),
            Path("/tmp"),
            changes,
            "d",
            False,
            "1 entry omitted",
        )
        entries = items(snapshot)
        self.assertEqual(
            [item.basis for item in entries],
            [DiffBasis.STAGED, DiffBasis.UNSTAGED, None],
        )
        listing = inventory_text(snapshot, entries, 1)
        self.assertIn("Incomplete view: 1 entry omitted", listing)
        self.assertIn("+2/-1", listing)
        self.assertIn("+3/-0", listing)
        self.assertIn("untracked", listing)
        self.assertIn("separate read policy", patch_text(None, entries[2], 0))
        patch = Patch("a.py", DiffBasis.STAGED, "d", b"x\n" * 600, "p")
        shown = patch_text(patch, entries[0], 0)
        self.assertEqual(shown.count("x\n"), RENDER_LINE_LIMITS[0])
        self.assertIn("Partial view: 100 lines omitted", shown)

    def test_empty_non_git_and_incomplete_inventory_are_truthful(self) -> None:
        empty = GitSnapshot(GitState.NON_GIT, Path("/tmp"), None, (), "", True)
        self.assertIn("Not a Git checkout", inventory_text(empty, (), 0))
        incomplete = GitSnapshot(
            GitState.READY,
            Path("/tmp"),
            Path("/tmp"),
            (),
            "d",
            False,
            "1 unsafe entry omitted",
        )
        self.assertIn("No displayable", inventory_text(incomplete, (), 0))
        self.assertNotIn("No changed files", inventory_text(incomplete, (), 0))


class DiffTUITests(IsolatedAsyncioTestCase):
    async def test_slow_read_does_not_block_editor_and_closed_generation_is_discarded(
        self,
    ) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            root = Path(directory)
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(root, cassette),
                cassette,
                lambda state: None,
            )
            entered = threading.Event()
            release = threading.Event()

            class SlowReader:
                def __init__(self, selection: object, git_executable: object) -> None:
                    pass

                def snapshot(self) -> GitSnapshot:
                    entered.set()
                    release.wait(3)
                    return GitSnapshot(GitState.NON_GIT, root, None, (), "", True)

            with patch("mos_eisley.conversation_tui.GitWorkspaceReader", SlowReader):
                ui = ConversationTUI(chat, input=input, output=DummyOutput())
                task = asyncio.create_task(ui.run())
                try:
                    async with asyncio.timeout(3):
                        while not ui.app.is_running:
                            await asyncio.sleep(0.01)
                    input.send_text("/diff\r")
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    input.send_text("responsive draft")
                    async with asyncio.timeout(2):
                        while ui.editor.text != "responsive draft":
                            await asyncio.sleep(0.01)
                    input.send_text("\x1b[21~")
                    async with asyncio.timeout(2):
                        while ui.diff_visible:
                            await asyncio.sleep(0.01)
                    release.set()
                    await asyncio.sleep(0.05)
                    self.assertIsNone(ui.diff_snapshot)
                    self.assertEqual(ui.editor.text, "responsive draft")
                finally:
                    release.set()
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 4)

    async def test_open_refresh_edit_select_and_close_preserves_draft(self) -> None:
        with TemporaryDirectory() as directory, create_pipe_input() as input:
            root = Path(directory)
            command(root, "init", "-q")
            command(root, "config", "user.email", "test@example.invalid")
            command(root, "config", "user.name", "Test")
            (root / "one.txt").write_text("before\n")
            (root / "two.txt").write_text("before\n")
            command(root, "add", ".")
            command(root, "commit", "-qm", "base")
            (root / "one.txt").write_text("after\x1b[2J\n")
            (root / "two.txt").write_text("after\n")
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(root, cassette),
                cassette,
                lambda state: None,
            )
            ui = ConversationTUI(chat, input=input, output=DummyOutput())
            task = asyncio.create_task(ui.run())
            try:
                async with asyncio.timeout(3):
                    while not ui.app.is_running:
                        await asyncio.sleep(0.01)
                input.send_text("/diff\r")
                async with asyncio.timeout(8):
                    while ui.diff_patch is None:
                        await asyncio.sleep(0.02)
                self.assertTrue(ui.diff_visible)
                self.assertIn("one.txt", ui.diff_files.text)
                self.assertIn("after", ui.diff_content.text)
                self.assertNotIn("\x1b", ui.diff_content.text)
                ui.editor.insert_text("keep this draft")
                ui.move_diff_selection(1)
                async with asyncio.timeout(8):
                    while getattr(ui.diff_patch, "path", None) != "two.txt":
                        await asyncio.sleep(0.02)
                self.assertIn("two.txt", ui.diff_files.text)
                ui.git_executable = root / "missing-git"
                ui.diff_wakeup.set()
                async with asyncio.timeout(5):
                    while ui.diff_error is None:
                        await asyncio.sleep(0.02)
                self.assertIn("STALE", ui.diff_content.text)
                self.assertIn("Refresh failed", ui.diff_files.text)
                ui.git_executable = GIT
                (root / "two.txt").write_text("newer\n")
                ui.diff_wakeup.set()
                async with asyncio.timeout(8):
                    while "newer" not in ui.diff_content.text:
                        await asyncio.sleep(0.02)
                input.send_text("\t")
                async with asyncio.timeout(3):
                    while not ui.app.layout.has_focus(ui.diff_files):
                        await asyncio.sleep(0.01)
                input.send_text("\x1b[21~")  # xterm F10
                async with asyncio.timeout(3):
                    while ui.diff_visible:
                        await asyncio.sleep(0.01)
                self.assertFalse(ui.diff_visible)
                self.assertTrue(ui.app.layout.has_focus(ui.editor_control))
                self.assertEqual(ui.editor.text, "keep this draft")
                self.assertEqual(chat.state.entries, ())
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 4)
