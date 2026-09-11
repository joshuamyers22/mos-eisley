"""Explicit project-memory identities survive refresh, resume and storage transfers."""

import argparse
import asyncio
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from test_conversation_working_state import ObservedStore

from mos_eisley.conversation import ConversationController, ConversationState
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_directory import DirectoryPicker, DirectorySelection
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_project import (
    preview_memory_project,
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


class MemoryProjectTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.workspace = self.root / "project" / "nested"
        self.workspace.mkdir(parents=True)
        self.project = self.workspace.parent
        self.memory_root = self.root / "memory"
        self.project_store = MemoryStore(self.memory_root, self.project)
        self.workspace_store = MemoryStore(self.memory_root, self.workspace)

    def launch(
        self, arguments: list[str], text: str = "/quit\n"
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *arguments],
            input=text,
            capture_output=True,
            text=True,
            cwd=self.root,
            timeout=15,
        )

    def test_preview_is_read_only_and_reports_collision_and_disabled_documents(
        self,
    ) -> None:
        missing = preview_memory_project(self.memory_root, self.workspace, self.project)
        self.assertEqual(missing["status"], "empty")
        self.assertFalse(self.memory_root.exists())
        self.workspace_store.change("project", "set", text="Subdirectory decisions")
        self.assertEqual(
            preview_memory_project(self.memory_root, self.workspace, self.project)[
                "status"
            ],
            "source-only",
        )
        self.project_store.change("project", "set", text="Root decisions")
        self.project_store.change("project", "disable")
        before = {
            p.name: (p.read_bytes(), p.stat().st_mtime_ns)
            for p in self.memory_root.iterdir()
        }
        preview = preview_memory_project(self.memory_root, self.workspace, self.project)
        self.assertEqual(preview["status"], "collision")
        self.assertFalse(preview["applied"])
        self.assertIn("Root decisions", json.dumps(preview))
        self.assertEqual(
            before,
            {
                p.name: (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.memory_root.iterdir()
            },
        )
        result = self.launch(
            [
                "memory-project-preview",
                "-C",
                str(self.workspace),
                "--memory-project-root",
                str(self.project),
                "--memory-storage",
                str(self.memory_root),
                "--json",
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["preview_sha256"], preview["preview_sha256"]
        )
        self.project_store.change("project", "enable")
        self.assertNotEqual(
            preview_memory_project(self.memory_root, self.workspace, self.project)[
                "preview_sha256"
            ],
            preview["preview_sha256"],
        )

    def test_selection_resolves_aliases_and_rejects_unrelated_projects(self) -> None:
        alias = self.root / "alias"
        alias.symlink_to(self.project, target_is_directory=True)
        self.assertEqual(
            select_memory_project(self.workspace, alias).path, self.project
        )
        other = self.root / "other"
        other.mkdir()
        with self.assertRaises(ValueError):
            select_memory_project(self.workspace, other)
        result = self.launch(
            [
                "chat",
                "-C",
                str(self.workspace),
                "--memory-project-root",
                str(other),
                "--storage",
                str(self.root / "sessions"),
                "--no-memory",
                "--json",
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "sessions").exists())

    def test_directory_preview_displays_explicit_memory_identity(self) -> None:
        with create_pipe_input() as input:
            picker = DirectoryPicker(
                self.workspace,
                memory_project_root=self.project,
                input=input,
                output=DummyOutput(),
            )
            picker.preview()
            self.assertIn(f"Project memory identity:\n{self.project}", picker.details())
            picker.editor.text = str(self.root)
            picker.preview()
            self.assertIsNone(picker.selection)
            self.assertIsNone(picker.memory_selection)
            self.assertIn("inside the selected memory root", picker.notice)

    def test_legacy_bytes_and_foreign_active_or_historical_memory(self) -> None:
        self.project_store.change("project", "set", text="Root memory")
        memory = self.project_store.load()
        cassette = demo_cassette(memory=memory)
        legacy = ConversationController.fresh(self.workspace, demo_cassette())
        self.assertNotIn(b"memory_project_root", canonical_bytes(legacy))
        self.assertEqual(
            canonical_bytes(
                ConversationState.model_validate_json(legacy.model_dump_json())
            ),
            canonical_bytes(legacy),
        )
        with self.assertRaises(ValueError):
            ConversationController.fresh(self.workspace, cassette, memory)
        state = ConversationController.fresh(
            self.workspace, cassette, memory, memory_project_root=str(self.project)
        )
        chat = ConversationController(state, cassette, lambda state: None)
        chat.submit(DEMO_PROMPTS[0])
        asyncio.run(chat.step())
        for field in ("memory_project_root",):
            data = chat.state.model_dump(mode="json")
            data[field] = str(self.workspace)
            with self.assertRaises(ValueError):
                ConversationState.model_validate(data)
        chat.refresh_memory(None, cassette, disabled=True)
        data = chat.state.model_dump(mode="json")
        data.pop("memory_project_root")
        with self.assertRaises(ValueError):
            ConversationState.model_validate(data)

    def test_cli_pins_memory_on_both_backends_and_resumes_after_marker_changes(
        self,
    ) -> None:
        self.project_store.change("project", "set", text="Root memory")
        self.workspace_store.change("project", "set", text="Workspace memory")
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
                    str(self.memory_root),
                    "--json",
                ]
                result = self.launch(
                    ["--memory-project-root", str(self.project), *options],
                    DEMO_PROMPTS[0] + "\n",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                opened = next(
                    json.loads(line)
                    for line in result.stdout.splitlines()
                    if json.loads(line)["type"] == "conversation.opened"
                )
                sid = opened["session_id"]
                self.assertEqual(opened["memory_workspace"], str(self.project))
                marker = self.workspace / ".git"
                marker.write_text("gitdir: /different/discovered/root")
                try:
                    resumed = self.launch(
                        ["resume", sid, *options],
                        "/directory\n" + DEMO_PROMPTS[1] + "\n",
                    )
                finally:
                    marker.unlink()
                self.assertEqual(resumed.returncode, 0, resumed.stderr)
                store_type = (
                    SQLiteConversationStore
                    if backend == "sqlite"
                    else ConversationStore
                )
                with store_type(storage, sid, self.workspace, create=False) as store:
                    state = store.load()
                self.assertEqual(state.memory, self.project_store.load())
                self.assertEqual(state.memory_project_root, str(self.project))
                self.assertEqual(
                    [e.status for e in state.entries], ["completed", "completed"]
                )
                self.assertNotIn("Workspace memory", state.model_dump_json())
                rejected = self.launch(
                    [
                        "resume",
                        sid,
                        *options,
                        "--memory-project-root",
                        str(self.workspace),
                    ]
                )
                self.assertNotEqual(rejected.returncode, 0)

    def test_disabled_selection_persists_and_switch_clears_it(self) -> None:
        self.project_store.change("project", "set", text="Root memory")
        cassette = demo_cassette()
        state = ConversationController.fresh(
            self.workspace,
            cassette,
            memory_disabled=True,
            memory_project_root=str(self.project),
        )
        chat = ConversationController(state, cassette, lambda state: None)
        runtime = ConversationMemoryRuntime(
            chat,
            self.project_store,
            lambda memory: demo_cassette(memory=memory),
            ignore_memory=True,
        )
        runtime.refresh(False)
        self.assertEqual(chat.state.memory, self.project_store.load())
        self.assertEqual(chat.state.memory_project_root, str(self.project))
        switched = fresh_directory_arguments(
            argparse.Namespace(memory_project_root=self.project),
            DirectorySelection.inspect(self.root),
        )
        self.assertIsNone(switched.memory_project_root)

    def test_sqlite_cold_history_refresh_and_export_preserve_identity(self) -> None:
        self.project_store.change("project", "set", text="Root revision one")
        memory = self.project_store.load()
        cassette = demo_cassette(memory=memory)
        state = ConversationController.fresh(
            self.workspace, cassette, memory, memory_project_root=str(self.project)
        )
        storage = self.root / "sqlite"
        with SQLiteConversationStore(
            storage, state.session_id, self.workspace
        ) as store:
            store.save(state)
            chat = ConversationController(state, cassette, store.save)
            chat.submit(DEMO_PROMPTS[0])
            asyncio.run(chat.step())
            self.project_store.change("project", "set", text="Root revision two")
            runtime = ConversationMemoryRuntime(
                chat, self.project_store, lambda memory: demo_cassette(memory=memory)
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
            self.assertEqual(working.memory_project_root, str(self.project))
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
            for e in page.entries
            for ref in e.artifacts
            if ref.field == "memory_context"
        )
        assert token is not None
        artifact = read_sqlite_artifact(storage, self.workspace, token)
        self.assertIn("Root revision one", artifact.model_dump_json())
        with SQLiteConversationStore(
            storage, state.session_id, self.workspace, create=False
        ) as store:
            expected = canonical_bytes(store.load())
        target = self.root / "export"
        target.mkdir(mode=0o700)
        preview = export_conversation(storage, target, state.session_id, self.workspace)
        export_conversation(
            storage,
            target,
            state.session_id,
            self.workspace,
            expected_sha256=preview.export_sha256,
            apply=True,
        )
        with ConversationStore(
            target, state.session_id, self.workspace, create=False
        ) as store:
            self.assertEqual(canonical_bytes(store.load()), expected)
        restored = self.root / "restored"
        restored.mkdir(mode=0o700)
        transfer = transfer_conversation(
            target, restored, state.session_id, self.workspace
        )
        transfer_conversation(
            target,
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
            record["memory_project_root"] = str(self.workspace)
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
