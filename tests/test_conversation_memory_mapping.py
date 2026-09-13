"""Explicit worktree memory sharing preserves workspace authority and saved identity."""

import argparse
import asyncio
import io
import json
import sqlite3
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from test_conversation_working_state import ObservedStore

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import (
    DEMO_PROMPTS,
    add_commands,
    demo_cassette,
    run_command,
)
from mos_eisley.conversation_directory import DirectoryPicker, DirectorySelection
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_project import (
    memory_workspace,
    select_memory_project,
)
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.conversation_state import WorkingConversationState
from mos_eisley.conversation_switch import fresh_directory_arguments
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.conversation_artifacts import read_sqlite_artifact
from mos_eisley.run.conversation_export import export_conversation
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.conversation_transcript import read_sqlite_transcript
from mos_eisley.run.conversation_transfer import transfer_conversation


class MemoryMappingTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / "worktree-a"
        self.other = self.base / "worktree-b"
        self.project = self.base / "shared-project"
        for path in (self.workspace, self.other, self.project):
            path.mkdir()
            (path / ".git").write_text(
                "gitdir: /shared/git/metadata\n", encoding="utf-8"
            )
        self.storage = self.base / "memory"
        self.shared = MemoryStore(self.storage, self.project)
        self.shared.change("project", "set", text="Shared project decisions")
        self.shared.change("user", "set", text="Personal preferences")

    def launch(
        self, arguments: list[str], text: str = "/quit\n"
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *arguments],
            input=text,
            capture_output=True,
            text=True,
            cwd=self.base,
            timeout=15,
        )

    def test_explicit_mapping_is_required_and_legacy_bytes_omit_the_field(self) -> None:
        legacy = ConversationController.fresh(self.workspace, demo_cassette())
        self.assertNotIn(b"memory_project_mapping", canonical_bytes(legacy))
        self.assertEqual(
            memory_workspace(str(self.workspace), None), str(self.workspace)
        )
        with self.assertRaises(ValueError):
            select_memory_project(self.workspace, self.project)
        selected = select_memory_project(self.workspace, self.project, mapped=True)
        self.assertEqual(selected.path, self.project)
        memory = self.shared.load()
        state = ConversationController.fresh(
            self.workspace,
            demo_cassette(memory=memory),
            memory,
            memory_project_mapping=str(self.project),
        )
        self.assertEqual(state.workspace, str(self.workspace))
        self.assertEqual(state.effective_memory_workspace, str(self.project))
        data = state.model_dump(mode="json")
        data.pop("memory_project_mapping")
        with self.assertRaises(ValueError):
            ConversationState.model_validate_json(json.dumps(data))
        data["memory_project_mapping"] = str(self.project)
        data["memory_project_root"] = str(self.base)
        with self.assertRaisesRegex(ValueError, "either"):
            ConversationState.model_validate_json(json.dumps(data))
        for invalid in (
            "relative",
            str(self.project) + "/",
            str(self.project) + "/../other",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                memory_workspace(str(self.workspace), None, invalid)

    def test_default_git_markers_do_not_share_memory(self) -> None:
        local = MemoryStore(self.storage, self.workspace)
        local.change("project", "set", text="Local worktree only")
        result = self.launch(
            [
                "chat",
                "-C",
                str(self.workspace),
                "--memory-storage",
                str(self.storage),
                "--storage",
                str(self.base / "default"),
                "--json",
            ],
            "/memory\n/quit\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Local worktree only", result.stdout)
        self.assertNotIn("Shared project decisions", result.stdout)
        self.assertNotIn('"memory_project_mapping"', result.stdout)

    def test_two_worktrees_share_only_the_explicit_identity_across_both_backends(
        self,
    ) -> None:
        for backend in ("snapshot", "sqlite"):
            for workspace in (self.workspace, self.other):
                with self.subTest(backend=backend, workspace=workspace):
                    local = MemoryStore(self.storage, workspace)
                    local.change("project", "set", text="Private local canary")
                    sessions = self.base / (backend + workspace.name)
                    args = [
                        "-C",
                        str(workspace),
                        "--memory-storage",
                        str(self.storage),
                        "--storage",
                        str(sessions),
                        "--storage-backend",
                        backend,
                        "--json",
                    ]
                    launched = self.launch(
                        [
                            "--memory-project-map",
                            str(self.project),
                            *args,
                        ],
                        DEMO_PROMPTS[0] + "\n",
                    )
                    self.assertEqual(launched.returncode, 0, launched.stderr)
                    events = [json.loads(line) for line in launched.stdout.splitlines()]
                    opened = next(
                        e for e in events if e["type"] == "conversation.opened"
                    )
                    self.assertEqual(opened["workspace"], str(workspace))
                    self.assertEqual(opened["memory_workspace"], str(self.project))
                    self.assertEqual(
                        opened["memory_project_mapping"], str(self.project)
                    )
                    sid = opened["session_id"]
                    self.shared.change("project", "append", text="Shared update")
                    blocked = self.launch(["resume", sid, *args])
                    self.assertNotEqual(blocked.returncode, 0)
                    resumed = self.launch(
                        ["resume", sid, "--refresh-memory", *args],
                        "/memory\n/directory\n/quit\n",
                    )
                    self.assertEqual(resumed.returncode, 0, resumed.stderr)
                    self.assertIn("Shared update", resumed.stdout)
                    self.assertNotIn("Private local canary", resumed.stdout)
                    store_type = (
                        SQLiteConversationStore
                        if backend == "sqlite"
                        else ConversationStore
                    )
                    with store_type(sessions, sid, workspace, create=False) as store:
                        state = store.load()
                    self.assertEqual(state.workspace, str(workspace))
                    self.assertEqual(state.memory_project_mapping, str(self.project))
                    self.assertIsNone(state.memory_project_root)
                    self.assertEqual(state.entries[0].status, "completed")
                    historical = state.entries[0].memory_context
                    assert historical is not None and historical.memory is not None
                    historical.memory.validate_identity(
                        state.owner_uid, str(self.project)
                    )

    def test_no_memory_keeps_mapping_and_resume_rejects_overrides(self) -> None:
        sessions = self.base / "disabled"
        args = [
            "-C",
            str(self.workspace),
            "--memory-storage",
            str(self.storage),
            "--storage",
            str(sessions),
            "--json",
        ]
        result = self.launch(
            ["chat", "--memory-project-map", "shared-project", "--no-memory", *args]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        sid = next(
            json.loads(line)["session_id"]
            for line in result.stdout.splitlines()
            if json.loads(line)["type"] == "conversation.opened"
        )
        with ConversationStore(sessions, sid, self.workspace, create=False) as store:
            state = store.load()
        self.assertIsNone(state.memory)
        self.assertEqual(state.memory_project_mapping, str(self.project))
        for flag in ("--memory-project-map", "--memory-project-root"):
            rejected = self.launch(["resume", sid, flag, str(self.other), *args])
            self.assertNotEqual(rejected.returncode, 0)
        resumed = self.launch(
            ["resume", sid, "--refresh-memory", *args], "/memory\n/quit\n"
        )
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn("Shared project decisions", resumed.stdout)

    def test_picker_preview_and_switch_clear_mapping_for_new_workspaces(self) -> None:
        with create_pipe_input() as pipe:
            picker = DirectoryPicker(
                self.workspace,
                input=pipe,
                output=DummyOutput(),
                memory_project_mapping=self.project,
            )
            picker.preview()
            self.assertEqual(
                picker.memory_selection, DirectorySelection.inspect(self.project)
            )
            self.assertIn("Mapped project memory identity", picker.details())
            picker.editor.text = str(self.other)
            picker.preview()
            self.assertIsNotNone(picker.selection)
            self.assertEqual(
                picker.memory_selection, DirectorySelection.inspect(self.project)
            )
        arguments = fresh_directory_arguments(
            argparse.Namespace(memory_project_mapping=self.project),
            DirectorySelection.inspect(self.other),
        )
        self.assertIsNone(arguments.memory_project_mapping)
        self.assertIsNone(arguments.memory_project_root)

    def test_startup_picker_pins_alias_before_selection(self) -> None:
        alias = self.base / "memory-alias"
        alias.symlink_to(self.project, target_is_directory=True)
        parser = argparse.ArgumentParser()
        add_commands(parser.add_subparsers(dest="command").add_parser)
        sessions = self.base / "picker"
        args = parser.parse_args(
            [
                "chat",
                "--choose-directory",
                "-C",
                str(self.workspace),
                "--memory-project-map",
                str(alias),
                "--memory-storage",
                str(self.storage),
                "--storage",
                str(sessions),
            ]
        )

        def choose(
            initial: Path,
            *,
            memory_project_root: Path | None = None,
            memory_project_mapping: Path | None = None,
        ) -> DirectorySelection:
            self.assertIsNone(memory_project_root)
            self.assertEqual(memory_project_mapping, self.project)
            alias.unlink()
            alias.symlink_to(self.other, target_is_directory=True)
            return DirectorySelection.inspect(initial)

        with (
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
            patch("mos_eisley.conversation_cli.sys.stdin.isatty", return_value=True),
            patch("mos_eisley.conversation_cli.sys.stdout.isatty", return_value=True),
            patch("mos_eisley.conversation_cli.pick_directory", side_effect=choose),
            patch("mos_eisley.conversation_cli.termios.tcgetattr", return_value=[]),
            patch("mos_eisley.conversation_cli.termios.tcsetattr"),
            patch("mos_eisley.conversation_tui.ConversationTUI") as ui,
        ):
            ui.return_value.run = AsyncMock(return_value=None)
            self.assertEqual(run_command(args), 0)
        state = ConversationState.model_validate_json(
            json.dumps(json.loads(next(sessions.glob("*.json")).read_bytes())["state"])
        )
        self.assertEqual(state.memory_project_mapping, str(self.project))
        self.assertEqual(state.memory, self.shared.load())

    def test_sqlite_cold_history_roundtrip_and_index_tampering(
        self,
    ) -> None:
        memory = self.shared.load()
        cassette = demo_cassette(memory=memory)
        state = ConversationController.fresh(
            self.workspace,
            cassette,
            memory,
            memory_project_mapping=str(self.project),
        )
        storage = self.base / "sqlite"
        with SQLiteConversationStore(
            storage, state.session_id, self.workspace
        ) as store:
            store.save(state)
            chat = ConversationController(state, cassette, store.save)
            chat.submit(DEMO_PROMPTS[0])
            asyncio.run(chat.step())
            self.shared.change("project", "set", text="Shared revision two")
            runtime = ConversationMemoryRuntime(
                chat, self.shared, lambda memory: demo_cassette(memory=memory)
            )
            runtime.refresh(False)
            cassette = chat.cassette
        with ObservedStore(
            storage, state.session_id, self.workspace, create=False
        ) as store:
            store.allow_full_reads = False
            store.chunks = []
            working = store.load_working()
            self.assertIsInstance(working, WorkingConversationState)
            assert isinstance(working, WorkingConversationState)
            self.assertEqual(working.memory_project_mapping, str(self.project))
            chat = ConversationController(
                working,
                cassette,
                store.save_working,
                load_entry=store.load_working_entry,
            )
            chat.submit(DEMO_PROMPTS[1])
            asyncio.run(chat.step())
        page = read_sqlite_transcript(storage, state.session_id, self.workspace)
        token = next(
            ref.selection
            for entry in page.entries
            for ref in entry.artifacts
            if ref.field == "memory_context"
        )
        assert token is not None
        artifact = read_sqlite_artifact(storage, self.workspace, token)
        self.assertIn("Shared project decisions", artifact.model_dump_json())
        with SQLiteConversationStore(
            storage, state.session_id, self.workspace, create=False
        ) as store:
            expected = canonical_bytes(store.load())
        exported = self.base / "export"
        exported.mkdir(mode=0o700)
        preview = export_conversation(
            storage, exported, state.session_id, self.workspace
        )
        export_conversation(
            storage,
            exported,
            state.session_id,
            self.workspace,
            expected_sha256=preview.export_sha256,
            apply=True,
        )
        with ConversationStore(
            exported, state.session_id, self.workspace, create=False
        ) as store:
            self.assertEqual(canonical_bytes(store.load()), expected)
        restored = self.base / "restored"
        restored.mkdir(mode=0o700)
        transfer = transfer_conversation(
            exported, restored, state.session_id, self.workspace
        )
        transfer_conversation(
            exported,
            restored,
            state.session_id,
            self.workspace,
            expected_sha256=transfer.transfer_sha256,
            apply=True,
        )
        with SQLiteConversationStore(
            restored, state.session_id, self.workspace, create=False
        ) as store:
            self.assertEqual(canonical_bytes(store.load()), expected)
        with sqlite3.connect(restored / DATABASE) as db:
            record = json.loads(db.execute("SELECT record FROM sessions").fetchone()[0])
            record["memory_project_mapping"] = str(self.workspace)
            payload = json.dumps(
                record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
            db.execute(
                "UPDATE sessions SET record=?, record_sha=?", (payload, digest(payload))
            )
        with (
            SQLiteConversationStore(
                restored, state.session_id, self.workspace, create=False
            ) as store,
            self.assertRaises(ValueError),
        ):
            store.load_working()

    def test_disabled_mapping_does_not_create_memory_and_rejects_target_retargeting(
        self,
    ) -> None:
        absent_memory = self.base / "absent-memory"
        sessions = self.base / "retarget"
        args = [
            "-C",
            str(self.workspace),
            "--memory-storage",
            str(absent_memory),
            "--storage",
            str(sessions),
            "--json",
        ]
        result = self.launch(
            ["chat", "--memory-project-map", str(self.project), "--no-memory", *args]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(absent_memory.exists())
        (path,) = sessions.glob("*.json")
        saved = path.read_bytes()
        sid = json.loads(saved)["state"]["session_id"]
        self.project.rename(self.base / "original-project")
        self.project.symlink_to(self.other, target_is_directory=True)
        rejected = self.launch(["resume", sid, *args])
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(path.read_bytes(), saved)
        self.assertFalse(absent_memory.exists())

    def test_conflicting_flags_and_missing_mapping_fail_before_session_creation(
        self,
    ) -> None:
        sessions = self.base / "rejected"
        args = [
            "chat",
            "-C",
            str(self.workspace),
            "--storage",
            str(sessions),
            "--memory-storage",
            str(self.storage),
            "--json",
        ]
        for options in (
            [
                "--memory-project-root",
                str(self.base),
                "--memory-project-map",
                str(self.project),
            ],
            ["--memory-project-map", str(self.base / "missing"), "--no-memory"],
        ):
            result = self.launch([*args, *options])
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(sessions.exists())

    def test_recording_generators_accept_the_same_mapping(self) -> None:
        for command in ("conversation-demo", "conversation-review-demo"):
            output = self.base / (command + ".json")
            args = [
                command,
                "-C",
                str(self.workspace),
                "--memory-project-map",
                str(self.project),
                "--memory-storage",
                str(self.storage),
                "--output",
                str(output),
            ]
            if command == "conversation-review-demo":
                args += ["--review-output", str(self.base / "review.json")]
            result = self.launch(args, "")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.exists())
