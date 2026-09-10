"""Independent active-input admission before hydration and terminal recovery."""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from test_conversation_working_state import ObservedStore

from mos_eisley.conversation import (
    ConversationController,
    ConversationEntry,
    ConversationMemoryContext,
)
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_inputs import (
    ActiveInputLimitError,
    ActiveInputLimits,
    read_recording,
)
from mos_eisley.conversation_memory import MemoryRefreshError, MemoryStore
from mos_eisley.conversation_state import WorkingConversationState
from mos_eisley.core.agent import AgentUsage
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelResponse, TextBlock, Turn, Usage
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore


class InputLimitTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = self.root / "sessions"
        self.memories = MemoryStore(self.root / "memory", self.root)
        self.memories.change("user", "set", text="memory é " * 1000)
        self.memory = self.memories.load()
        self.cassette = AgentCassette(
            exchanges=(
                AgentExchange(
                    request_sha256="0" * 64,
                    response=ModelResponse(
                        turn=Turn(
                            role="assistant", blocks=(TextBlock(text="x" * 6000),)
                        ),
                        usage=Usage(input=1, output=1),
                        stop_reason="end_turn",
                    ),
                ),
            )
        )
        self.original = ConversationController.fresh(
            self.root, self.cassette, self.memory
        ).model_copy(update={"retained_cassette": self.cassette})
        with SQLiteConversationStore(
            self.storage, self.original.session_id, self.root
        ) as store:
            store.save(self.original)

    def open(self, limits: ActiveInputLimits) -> ObservedStore:
        store = ObservedStore(
            self.storage,
            self.original.session_id,
            self.root,
            create=False,
            input_limits=limits,
        )
        store.chunks = []
        store.allow_full_reads = False
        self.addCleanup(store.close)
        return store

    def invoke(self, *args: str, text: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "mos_eisley.cli",
                "resume",
                self.original.session_id,
                "--storage-backend",
                "sqlite",
                "--storage",
                str(self.storage),
                "--memory-storage",
                str(self.root / "memory"),
                "-C",
                str(self.root),
                "--json",
                *args,
            ],
            input=text,
            text=True,
            capture_output=True,
            env={**os.environ, "HOME": str(self.root)},
            timeout=30,
        )

    def snapshot_hash(self) -> str:
        with SQLiteConversationStore(
            self.storage, self.original.session_id, self.root, create=False
        ) as store:
            return digest(canonical_bytes(store.load()))

    def test_each_stored_input_is_admitted_before_either_artifact_is_fetched(
        self,
    ) -> None:
        for limits, flag in (
            (ActiveInputLimits(memory_max_bytes=4096), "--active-memory-max-bytes"),
            (ActiveInputLimits(recording_max_bytes=4096), "--recording-max-bytes"),
        ):
            with self.subTest(flag=flag):
                store = self.open(limits)
                queries: list[str] = []
                store.trace(queries)
                with self.assertRaisesRegex(ActiveInputLimitError, flag):
                    store.load_working()
                self.assertEqual(store.chunks, [])
                self.assertFalse(
                    any("SELECT payload FROM artifacts" in query for query in queries)
                )
                self.assertIsNone(store.snapshot_sha256)
                self.assertFalse(store.transaction_open())
                store.close()

    def test_exact_serialized_boundaries_preserve_snapshot_and_attempts(self) -> None:
        assert self.memory is not None
        limits = ActiveInputLimits(
            memory_max_bytes=len(canonical_bytes(self.memory)),
            recording_max_bytes=len(canonical_bytes(self.cassette)),
        )
        store = self.open(limits)
        state = store.load_working()
        self.assertIsInstance(state, WorkingConversationState)
        self.assertEqual(store.snapshot_sha256, digest(canonical_bytes(self.original)))
        self.assertEqual(state.exchanges_consumed, 0)
        self.assertNotIn("input_limits", state.model_dump_json())

    def test_unprepared_index_cannot_bypass_pre_hydration_limits(self) -> None:
        with sqlite3.connect(self.storage / DATABASE) as db:
            record = json.loads(db.execute("SELECT record FROM sessions").fetchone()[0])
            record.pop("resume_checkpoint")
            record.pop("entry_sha256")
            raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            db.execute("UPDATE sessions SET record=?, record_sha=?", (raw, digest(raw)))
        store = self.open(ActiveInputLimits(recording_max_bytes=4096))
        with self.assertRaises(ActiveInputLimitError):
            store.load_working()
        self.assertEqual(store.full_reads, 0)
        self.assertEqual(store.chunks, [])

    def test_configured_full_reader_also_rejects_before_artifact_hydration(
        self,
    ) -> None:
        store = self.open(ActiveInputLimits(recording_max_bytes=4096))
        store.allow_full_reads = True
        queries: list[str] = []
        store.trace(queries)
        with self.assertRaises(ActiveInputLimitError):
            store.load()
        self.assertFalse(
            any("SELECT payload FROM artifacts" in query for query in queries)
        )

    def test_controller_rejects_before_running_work_is_recovered(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(self.root, cassette)
        controller = ConversationController(state, cassette, lambda _: None)
        controller.submit("queued")
        running = controller.state.model_copy(
            update={
                "memory": self.memory,
                "entries": tuple(
                    entry.model_copy(update={"status": "running"})
                    for entry in controller.state.entries
                ),
                "exchanges_consumed": 1,
            }
        )
        saves: list[object] = []
        with self.assertRaises(ActiveInputLimitError):
            ConversationController(
                running,
                cassette,
                saves.append,
                input_limits=ActiveInputLimits(memory_max_bytes=4096),
            )
        self.assertEqual(saves, [])

    def test_refresh_rejection_leaves_controller_usable_without_saving(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(self.root, cassette)
        saves: list[object] = []
        controller = ConversationController(
            state,
            cassette,
            saves.append,
            input_limits=ActiveInputLimits(
                memory_max_bytes=4096, recording_max_bytes=4096
            ),
        )
        for memory, recording, flag in (
            (self.memory, cassette, "--active-memory-max-bytes"),
            (None, self.cassette, "--recording-max-bytes"),
        ):
            with (
                self.subTest(flag=flag),
                self.assertRaisesRegex(MemoryRefreshError, flag),
            ):
                controller.refresh_memory(memory, recording)
            self.assertEqual(controller.state, state)
            self.assertEqual(saves, [])
        controller.submit("still usable")
        self.assertEqual(len(saves), 1)
        self.assertEqual(controller.state.exchanges_consumed, 0)

    def test_recording_file_rejects_oversize_before_json_decoding(self) -> None:
        path = self.root / "recording.json"
        path.write_bytes(b"!" * 4097)
        with self.assertRaisesRegex(ActiveInputLimitError, "Recording file exceeds"):
            read_recording(path, ActiveInputLimits(recording_max_bytes=4096))
        path.write_bytes(canonical_bytes(self.cassette))
        self.assertEqual(read_recording(path, ActiveInputLimits()), self.cassette)

    def test_cli_storage_increase_does_not_bypass_recording_limit(self) -> None:
        before = self.snapshot_hash()
        rejected = self.invoke(
            "--session-max-bytes", "4000000", "--recording-max-bytes", "4096"
        )
        self.assertEqual(rejected.returncode, 2, rejected.stderr)
        self.assertIn("--recording-max-bytes", rejected.stderr)
        self.assertIn(str(len(canonical_bytes(self.cassette))), rejected.stderr)
        self.assertEqual(self.snapshot_hash(), before)

    def test_cli_limits_are_visible_per_open_and_do_not_change_saved_hashes(
        self,
    ) -> None:
        before = self.snapshot_hash()
        for args, memory_limit, recording_limit in (
            (
                (
                    "--active-memory-max-bytes",
                    "64000",
                    "--recording-max-bytes",
                    "64000",
                ),
                64000,
                64000,
            ),
            ((), 131072, 2000000),
        ):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                event = next(
                    json.loads(line)
                    for line in result.stdout.splitlines()
                    if json.loads(line)["type"] == "conversation.input_limits"
                )
                self.assertEqual(event["memory_max_bytes"], memory_limit)
                self.assertEqual(event["recording_max_bytes"], recording_limit)
                self.assertEqual(self.snapshot_hash(), before)

    def test_cli_inspection_rejects_unused_input_limits(self) -> None:
        result = self.invoke("--inspect", "--recording-max-bytes", "64000")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("conversation.opened", result.stdout)

    def test_bare_launch_accepts_input_limits_and_reports_them(self) -> None:
        for option in (
            "--active-memory-max-bytes=64000",
            "--recording-max-bytes=64000",
        ):
            with self.subTest(option=option):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        option,
                        "--no-memory",
                        "--storage",
                        str(self.root / "new"),
                        "-C",
                        str(self.root),
                        "--json",
                    ],
                    input="",
                    text=True,
                    capture_output=True,
                    env={**os.environ, "HOME": str(self.root)},
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                events = [json.loads(line) for line in result.stdout.splitlines()]
                self.assertTrue(
                    any(
                        event["type"] == "conversation.input_limits" for event in events
                    )
                )

    def test_strict_limit_contract_rejects_invalid_values(self) -> None:
        for field, values in (
            ("memory_max_bytes", (True, 4095, 262145)),
            ("recording_max_bytes", (True, 4095, 32000001)),
        ):
            for value in values:
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(ValueError),
                ):
                    ActiveInputLimits.model_validate({field: value})

    def test_dispatch_rechecks_active_input_before_consuming_attempt(self) -> None:
        cassette = demo_cassette()
        state = ConversationController.fresh(self.root, cassette, self.memory)
        controller = ConversationController(state, cassette, lambda _: None)
        controller.submit("pending")
        controller.input_limits = ActiveInputLimits(memory_max_bytes=4096)
        before = controller.state
        with self.assertRaises(ActiveInputLimitError):
            asyncio.run(controller.step())
        self.assertEqual(controller.state, before)
        self.assertEqual(controller.state.exchanges_consumed, 0)

    def test_active_memory_limit_does_not_hide_larger_historical_memory(self) -> None:
        entry = ConversationEntry(
            text="earlier",
            status="completed",
            answer="saved",
            usage=AgentUsage(
                requests=1, tools=0, billed_input=1, billed_output=1, largest_request=1
            ),
            memory_context=ConversationMemoryContext(memory=self.memory),
        )
        with SQLiteConversationStore(
            self.storage, self.original.session_id, self.root, create=False
        ) as store:
            state = store.load()
            store.save(
                state.model_copy(
                    update={
                        "memory": None,
                        "entries": (entry,),
                        "exchanges_consumed": 1,
                        "revision": state.revision + 1,
                    }
                )
            )
        store = self.open(ActiveInputLimits(memory_max_bytes=4096))
        state = store.load_working()
        self.assertIsNone(state.memory)
        self.assertTrue(state.entries[0].has_memory_context)
        self.assertEqual(state.exchanges_consumed, 1)

    def test_configured_writers_reject_before_updating_saved_state(self) -> None:
        store = self.open(ActiveInputLimits())
        state = store.load_working()
        assert isinstance(state, WorkingConversationState)
        before = store.snapshot_sha256
        store.input_limits = ActiveInputLimits(memory_max_bytes=4096)
        proposed = state.model_copy(update={"revision": state.revision + 1})
        with self.assertRaises(ActiveInputLimitError):
            store.save_working(proposed)
        with self.assertRaises(ActiveInputLimitError):
            store.save(
                self.original.model_copy(update={"revision": state.revision + 1})
            )
        self.assertEqual(store.snapshot_sha256, before)
        self.assertFalse(store.transaction_open())
