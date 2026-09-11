"""Project discovery is bounded display metadata, never a new memory binding."""

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

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_directory import DirectoryPicker
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_project import ProjectLocation
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore


class ProjectTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "repository"
        self.workspace = self.repo / "packages" / "one"
        self.workspace.mkdir(parents=True)
        (self.repo / ".git").mkdir()

    def test_nearest_marker_and_canonical_alias(self) -> None:
        alias = self.root / "alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        location = ProjectLocation.inspect(alias)
        self.assertEqual(location.workspace, str(self.workspace))
        self.assertEqual(location.root, str(self.repo))
        self.assertEqual(location.detection, "git-directory")
        nested = self.workspace.parent
        (nested / ".git").mkdir()
        self.assertEqual(ProjectLocation.inspect(alias).root, str(nested))

    def test_git_files_keep_worktrees_separate_without_reading_pointers(self) -> None:
        for name in ("one", "two"):
            tree = self.repo / name
            tree.mkdir()
            (tree / ".git").write_text("gitdir: /PRIVATE/shared/metadata\n")
            with patch.object(Path, "open", side_effect=AssertionError("file read")):
                location = ProjectLocation.inspect(tree)
            self.assertEqual(location.root, str(tree))
            self.assertEqual(location.detection, "git-file")
            self.assertNotIn("PRIVATE", location.describe())

    def test_symlinks_and_special_markers_do_not_fall_back_to_outer_repo(self) -> None:
        marker = self.workspace / ".git"
        marker.symlink_to(self.repo / ".git", target_is_directory=True)
        self.assertEqual(
            ProjectLocation.inspect(self.workspace).detection, "unavailable"
        )
        marker.unlink()
        os.mkfifo(marker)
        location = ProjectLocation.inspect(self.workspace)
        self.assertIsNone(location.root)
        self.assertEqual(location.detection, "unavailable")

    def test_scan_limit_and_read_errors_are_distinct_from_absence(self) -> None:
        with patch("mos_eisley.conversation_project.MAX_PROJECT_ANCESTORS", 2):
            location = ProjectLocation.inspect(self.workspace)
        self.assertIsNone(location.root)
        self.assertEqual(location.detection, "limit")
        with patch.object(Path, "lstat", side_effect=PermissionError("PRIVATE")):
            location = ProjectLocation.inspect(self.workspace)
        self.assertEqual(location.detection, "unavailable")
        self.assertNotIn("PRIVATE", location.describe())
        self.assertEqual(
            ProjectLocation.inspect(self.root / "missing").detection, "unavailable"
        )
        with patch.object(Path, "lstat", side_effect=FileNotFoundError):
            location = ProjectLocation.inspect(self.root)
        self.assertEqual(location.detection, "none")

    def test_picker_preview_shows_root_and_invalidates_on_edit(self) -> None:
        with create_pipe_input() as input:
            picker = DirectoryPicker(self.workspace, input=input, output=DummyOutput())
            picker.preview()
            self.assertIn(str(self.repo), picker.details())
            self.assertIn("Project memory identity", picker.details())
            picker.editor.insert_text("x")
            self.assertIsNone(picker.selection)
            self.assertIsNone(picker.project_location)
            self.assertNotIn(str(self.repo), picker.details())

    def test_cli_and_resume_report_root_without_rebinding_memory_or_state(self) -> None:
        memory_root = self.root / "memory"
        MemoryStore(memory_root, self.repo).change(
            "project", "set", text="ROOT MEMORY MUST NOT LOAD"
        )
        workspace_memory = MemoryStore(memory_root, self.workspace)
        workspace_memory.change("project", "set", text="Workspace memory")
        for backend in ("snapshot", "sqlite"):
            with self.subTest(backend=backend):
                storage = self.root / backend
                options = [
                    "-C",
                    str(self.workspace),
                    "--storage",
                    str(storage),
                    "--storage-backend",
                    backend,
                    "--memory-storage",
                    str(memory_root),
                    "--json",
                ]

                def launch(
                    arguments: list[str], options: list[str]
                ) -> list[dict[str, object]]:
                    result = subprocess.run(
                        [sys.executable, "-m", "mos_eisley.cli", *arguments, *options],
                        input="/directory\n/quit\n",
                        capture_output=True,
                        text=True,
                        cwd=self.root,
                        timeout=15,
                        check=True,
                    )
                    return [json.loads(line) for line in result.stdout.splitlines()]

                events = launch(["chat"], options)
                opened = next(e for e in events if e["type"] == "conversation.opened")
                directory = next(
                    e for e in events if e["type"] == "conversation.directory"
                )
                self.assertEqual(opened["project_root"], str(self.repo))
                self.assertEqual(directory["project_root"], str(self.repo))
                self.assertEqual(directory["memory_workspace"], str(self.workspace))
                session_id = str(opened["session_id"])
                store_type = (
                    SQLiteConversationStore
                    if backend == "sqlite"
                    else ConversationStore
                )
                with store_type(
                    storage, session_id, self.workspace, create=False
                ) as store:
                    state = store.load()
                self.assertEqual(state.memory, workspace_memory.load())
                self.assertNotIn("ROOT MEMORY MUST NOT LOAD", state.model_dump_json())
                before = canonical_bytes(state)
                # A new launch refreshes discovery metadata, not saved identity.
                marker = self.workspace / ".git"
                marker.write_text("gitdir: /PRIVATE/new/metadata\n")
                try:
                    events = launch(["resume", session_id], options)
                    opened = next(
                        e for e in events if e["type"] == "conversation.opened"
                    )
                    self.assertEqual(opened["project_root"], str(self.workspace))
                    self.assertEqual(opened["project_detection"], "git-file")
                    with store_type(
                        storage, session_id, self.workspace, create=False
                    ) as store:
                        self.assertEqual(canonical_bytes(store.load()), before)
                finally:
                    marker.unlink()


class ProjectTUITests(IsolatedAsyncioTestCase):
    async def test_header_and_inspection_use_one_snapshot_without_dispatch(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            marker = root / ".git"
            marker.mkdir()
            workspace = root / "nested"
            workspace.mkdir()
            cassette = demo_cassette()
            chat = ConversationController(
                ConversationController.fresh(workspace, cassette),
                cassette,
                lambda state: None,
            )
            before = canonical_bytes(chat.state)
            with create_pipe_input() as input:
                ui = ConversationTUI(chat, input=input, output=DummyOutput())
                marker.rmdir()
                task = asyncio.create_task(ui.run())
                try:
                    async with asyncio.timeout(3):
                        while not ui.app.is_running:
                            await asyncio.sleep(0.01)
                    with patch.object(
                        ProjectLocation, "inspect", side_effect=AssertionError("rescan")
                    ):
                        input.send_text("/directory\r")
                        async with asyncio.timeout(3):
                            while not ui.directory_visible:
                                await asyncio.sleep(0.01)
                        self.assertIn("Project root:", ui.header())
                        self.assertIn(str(root)[-40:], ui.header())
                        self.assertIn(str(workspace)[-40:], ui.header())
                        self.assertIn(
                            f"Working directory\n{workspace}", ui.transcript.text
                        )
                        self.assertIn("Git marker at startup", ui.transcript.text)
                        self.assertIn(
                            f"Project memory identity\n{workspace}", ui.transcript.text
                        )
                        self.assertEqual(canonical_bytes(chat.state), before)
                finally:
                    input.send_text("\x04")
                    await asyncio.wait_for(task, 3)
