"""Explicit snapshot budgets preserve bounded reads, history and save atomicity."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation import ConversationController, ConversationEntry
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_limits import MAX_SNAPSHOT_BYTES
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.protocol import ModelResponse, TextBlock, Turn, Usage
from mos_eisley.providers.agent_recorded import AgentCassette, AgentExchange
from mos_eisley.run.conversation_store import (
    ConversationSnapshot,
    ConversationStore,
    list_conversations,
)


def large_cassette() -> AgentCassette:
    response = ModelResponse(
        turn=Turn(
            role="assistant",
            blocks=tuple(TextBlock(text="x" * 8000) for _ in range(64)),
        ),
        usage=Usage(input=1, output=1),
        stop_reason="end_turn",
    )
    return AgentCassette(
        exchanges=tuple(
            AgentExchange(request_sha256="0" * 64, response=response) for _ in range(5)
        )
    )


class StorageBudgetTests(TestCase):
    def test_large_snapshot_requires_opt_in_and_survives_load_list_delete(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = large_cassette()
            state = ConversationController.fresh(root, cassette)
            with ConversationStore(root, state.session_id, root) as store:
                store.save(state)
                controller = ConversationController(state, cassette, store.save)
                path = root / f"{state.session_id}.json"
                before = path.read_bytes()
                with self.assertRaisesRegex(ValueError, "byte limit"):
                    controller.refresh_memory(None, cassette)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(controller.state, state)
            with ConversationStore(root, state.session_id, root, create=False) as store:
                controller = ConversationController(store.load(), cassette, store.save)
                controller.refresh_memory(None, cassette, snapshot_max_bytes=4_000_000)
                saved = controller.state
                self.assertGreater(path.stat().st_size, 2_000_000)
            with ConversationStore(root, state.session_id, root, create=False) as store:
                self.assertEqual(store.load(), saved)
                summary = list_conversations(root, root)[0]
                self.assertEqual(summary.snapshot_bytes, path.stat().st_size)
                self.assertEqual(summary.snapshot_max_bytes, 4_000_000)
                self.assertEqual(
                    summary.snapshot_sha256, digest(canonical_bytes(saved))
                )
                self.assertNotIn("retained_cassette", summary.model_dump_json())
                store.delete(summary.snapshot_sha256)
            self.assertFalse(path.exists())

    def test_catalog_scan_budget_is_independent_and_failure_returns_no_partial_rows(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = large_cassette()
            for _ in range(4):
                state = ConversationController.fresh(
                    root, cassette, snapshot_max_bytes=4_000_000
                ).model_copy(update={"retained_cassette": cassette})
                with ConversationStore(root, state.session_id, root) as store:
                    store.save(state)
            with self.assertRaisesRegex(ValueError, "byte limit"):
                list_conversations(root, root)
            rows = list_conversations(root, root, max_bytes=16_000_000)
            self.assertEqual(len(rows), 4)
            total = sum(row.snapshot_bytes for row in rows)
            self.assertEqual(len(list_conversations(root, root, max_bytes=total)), 4)
            with self.assertRaisesRegex(ValueError, "byte limit"):
                list_conversations(root, root, max_bytes=total - 1)
            for maximum in (0, -1, 128_000_001, True):
                with self.assertRaises(ValueError):
                    list_conversations(root, root, max_bytes=maximum)

    def test_shrink_failure_preserves_snapshot_and_poisoned_controller(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette).model_copy(
                update={
                    "entries": tuple(
                        ConversationEntry(text="x" * 8000) for _ in range(16)
                    )
                }
            )
            with ConversationStore(root, state.session_id, root) as store:
                store.save(state)
                path = root / f"{state.session_id}.json"
                before = path.read_bytes()
                controller = ConversationController(state, cassette, store.save)
                with self.assertRaisesRegex(ValueError, "byte limit"):
                    controller.resize_storage(64_000)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(controller.state, state)
                with self.assertRaisesRegex(ValueError, "persistence failed"):
                    controller.cancel_queued()
            with ConversationStore(root, state.session_id, root, create=False) as store:
                controller = ConversationController(store.load(), cassette, store.save)
                controller.resize_storage(4_000_000)
                self.assertEqual(controller.state.entries, state.entries)
                self.assertEqual(controller.state.exchanges_consumed, 0)

    def test_legacy_hash_and_budget_survive_transitions_refresh_and_interruption(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            self.assertNotIn("snapshot_max_bytes", state.model_dump_json())
            with ConversationStore(root, state.session_id, root) as store:
                store.save(state)
                self.assertEqual(
                    digest(canonical_bytes(store.load())),
                    digest(canonical_bytes(state)),
                )
                controller = ConversationController(state, cassette, store.save)
                controller.resize_storage(4_000_000)
                revision = controller.state.revision
                controller.resize_storage(4_000_000)
                self.assertEqual(controller.state.revision, revision)
                controller.submit(DEMO_PROMPTS[0])
                asyncio.run(controller.step())
                runtime = ConversationMemoryRuntime(
                    controller,
                    MemoryStore(root / "memory", root),
                    lambda memory: demo_cassette(memory=memory),
                )
                runtime.refresh(True)
                self.assertEqual(controller.state.snapshot_byte_limit, 4_000_000)
                self.assertEqual(controller.state.entries[0].status, "completed")
                running = controller.state.model_copy(
                    update={
                        "entries": controller.state.entries
                        + (ConversationEntry(text=DEMO_PROMPTS[1], status="running"),),
                        "exchanges_consumed": 2,
                        "revision": controller.state.revision + 1,
                    }
                )
                store.save(running)
                restored = ConversationController(
                    running, controller.cassette, store.save
                )
                self.assertEqual(restored.state.snapshot_byte_limit, 4_000_000)
                self.assertEqual(restored.state.entries[1].status, "interrupted")
                self.assertEqual(restored.state.exchanges_consumed, 2)

    def test_saved_and_absolute_read_limits_reject_before_dispatch(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = large_cassette()
            state = ConversationController.fresh(root, cassette).model_copy(
                update={"retained_cassette": cassette}
            )
            with ConversationStore(root, state.session_id, root) as store:
                path = root / f"{state.session_id}.json"
                path.touch(mode=0o600)
                path.write_bytes(
                    canonical_bytes(
                        ConversationSnapshot(
                            state=state, sha256=digest(canonical_bytes(state))
                        )
                    )
                )
                with self.assertRaisesRegex(ValueError, "saved byte limit"):
                    store.load()
                with path.open("wb") as stream:
                    stream.truncate(MAX_SNAPSHOT_BYTES + 1)
                with patch.object(ConversationSnapshot, "model_validate_json") as parse:
                    with self.assertRaisesRegex(ValueError, "byte limit"):
                        store.load()
                    parse.assert_not_called()
            for maximum in (True, 63_999, 32_000_001):
                with self.assertRaises(ValueError):
                    ConversationController.fresh(
                        root, cassette, snapshot_max_bytes=maximum
                    )

    def test_resize_rejects_active_work_and_atomic_replace_failure(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cassette = demo_cassette()
            state = ConversationController.fresh(root, cassette)
            with ConversationStore(root, state.session_id, root) as store:
                store.save(state)
                controller = ConversationController(state, cassette, store.save)
                with (
                    patch.object(controller, "_busy", True),
                    self.assertRaisesRegex(ValueError, "active work"),
                ):
                    controller.resize_storage(4_000_000)
                with (
                    patch(
                        "mos_eisley.run.conversation_store.os.replace",
                        side_effect=OSError("disk failure"),
                    ),
                    self.assertRaises(OSError),
                ):
                    controller.resize_storage(4_000_000)
                self.assertEqual(store.load(), state)
                self.assertEqual(controller.state, state)
                self.assertFalse(tuple(root.glob(".*.tmp")))


class StorageBudgetCLITests(TestCase):
    def invoke(
        self, home: Path, *args: str, text: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *args],
            input=text,
            text=True,
            capture_output=True,
            env={**os.environ, "HOME": str(home)},
            timeout=20,
        )

    def test_launch_resize_resume_and_inspect_budget(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.invoke(
                home,
                "--session-max-bytes",
                "4000000",
                "--plain",
                text=DEMO_PROMPTS[0] + "\n",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("snapshot budget: 4000000 bytes", result.stdout)
            result = self.invoke(
                home, "resume", "--last", "--session-max-bytes", "6000000", "--plain"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.invoke(
                home, "resume", "--last", "--plain", text=DEMO_PROMPTS[1] + "\n"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("snapshot budget: 6000000 bytes", result.stdout)
            self.assertIn("You gave me a boundary of ten.", result.stdout)
            result = self.invoke(home, "sessions", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            row = json.loads(result.stdout)["sessions"][0]
            self.assertEqual(row["snapshot_max_bytes"], 6_000_000)
            self.assertEqual(row["messages"], 2)
            self.assertEqual(
                row["snapshot_bytes"],
                (home / ".mos-eisley-sessions" / f"{row['session_id']}.json")
                .stat()
                .st_size,
            )
            result = self.invoke(home, "sessions", "--catalog-max-bytes", "1", "--json")
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("conversations.listed", result.stdout)

    def test_memory_refresh_and_budget_change_commit_together(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.invoke(home, "--plain", text=DEMO_PROMPTS[0] + "\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            path = next((home / ".mos-eisley-sessions").glob("*.json"))
            original = json.loads(path.read_bytes())["state"]
            result = self.invoke(
                home,
                "resume",
                "--last",
                "--refresh-memory",
                "--no-memory",
                "--session-max-bytes",
                "4000000",
                "--plain",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            final = json.loads(path.read_bytes())["state"]
            self.assertEqual(final["revision"], original["revision"] + 1)
            self.assertEqual(final["snapshot_max_bytes"], 4_000_000)
            self.assertTrue(final["memory_disabled"])
            self.assertEqual(
                final["exchanges_consumed"], original["exchanges_consumed"]
            )

    def test_invalid_budget_rejected_before_storage_creation(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            for maximum in ("63999", "32000001", "-1", "3.5", "abc"):
                result = self.invoke(home, "--session-max-bytes", maximum, "--plain")
                self.assertEqual(result.returncode, 2)
                self.assertFalse((home / ".mos-eisley-sessions").exists())
            result = self.invoke(home, "sessions", "--catalog-max-bytes", "128000001")
            self.assertEqual(result.returncode, 2)
            self.assertFalse((home / ".mos-eisley-sessions").exists())
