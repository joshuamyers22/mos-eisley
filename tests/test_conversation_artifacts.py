"""Selected artifact integrity, pre-allocation budgets and explicit UI expansion."""

import asyncio
import base64
import json
import os
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_history import TranscriptHistory
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.conversation_tui import ConversationTUI
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.demo import demo_inputs
from mos_eisley.run.conversation_artifacts import ArtifactContent, read_sqlite_artifact
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore
from mos_eisley.run.conversation_transcript import read_sqlite_transcript


def make_fixture(root: Path) -> str:
    memory = MemoryStore(root / "memory", root)
    memory.change("user", "set", text="EXPANSION-CANARY\x1b[31m")
    selected = memory.load()
    cassette = demo_cassette(memory=selected)
    state = ConversationController.fresh(root, cassette, selected)
    brief, recording = demo_inputs()
    with SQLiteConversationStore(root, state.session_id, root) as store:
        store.save(state)
        chat = ConversationController(state, cassette, store.save)
        chat.submit(DEMO_PROMPTS[0])
        asyncio.run(chat.step())
        ConversationMemoryRuntime(
            chat, memory, lambda selected: demo_cassette(memory=selected)
        ).refresh(True)
        chat.submit_review(ConversationReviewPacket(brief=brief, cassette=recording))
        asyncio.run(chat.step())
    return state.session_id


class ArtifactTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sid = make_fixture(self.root)

    def selection(self, field: str = "memory_context") -> str:
        page = read_sqlite_transcript(self.root, self.sid, self.root)
        selection = next(
            ref.selection
            for entry in page.entries
            for ref in entry.artifacts
            if ref.field == field
        )
        assert selection is not None
        return selection

    def test_each_artifact_is_explicit_verified_and_read_only(self) -> None:
        before = (self.root / DATABASE).read_bytes()
        for field in ("memory_context", "review_packet", "review_result"):
            with self.subTest(field=field):
                content = read_sqlite_artifact(
                    self.root, self.root, self.selection(field)
                )
                self.assertEqual(content.field, field)
                self.assertEqual(content.session_id, self.sid)
                self.assertEqual(
                    content.position, 0 if field == "memory_context" else 1
                )
                self.assertEqual(
                    "EXPANSION-CANARY" in content.model_dump_json(),
                    field == "memory_context",
                )
        self.assertEqual((self.root / DATABASE).read_bytes(), before)

    def test_budget_precedes_payload_fetch_and_only_selection_is_read(
        self,
    ) -> None:
        token = self.selection()
        size = json.loads(base64.urlsafe_b64decode(token))["bytes"]
        queries: list[str] = []
        original = sqlite3.connect

        def traced(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            db = original(*args, **kwargs)
            db.set_trace_callback(queries.append)
            return db

        with patch("mos_eisley.run.conversation_sqlite.sqlite3.connect", traced):
            with self.assertRaisesRegex(ValueError, "expansion limit"):
                read_sqlite_artifact(self.root, self.root, token, max_bytes=size - 1)
            self.assertFalse(
                any("THEN payload END FROM artifacts" in query for query in queries)
            )
            queries.clear()
            content = read_sqlite_artifact(self.root, self.root, token, max_bytes=size)
        self.assertEqual(content.bytes, size)
        self.assertEqual(
            sum("THEN payload END FROM artifacts" in query for query in queries), 1
        )
        self.assertFalse(any("header" in query.lower() for query in queries))
        self.assertEqual(sum("FROM entries" in query for query in queries), 1)

    def test_stale_foreign_and_unbound_selections_fail(self) -> None:
        token = self.selection()
        value = json.loads(base64.urlsafe_b64decode(token))
        for field, replacement in (
            ("owner_uid", os.getuid() + 1),
            ("store_id", "0" * 32),
            ("workspace", "/other"),
            ("snapshot_sha256", "0" * 64),
            ("field", "review_packet"),
            ("sha256", "0" * 64),
            ("position", 1),
            ("bytes", value["bytes"] + 1),
        ):
            with self.subTest(field=field):
                changed = base64.urlsafe_b64encode(
                    json.dumps({**value, field: replacement}).encode()
                ).decode()
                with self.assertRaises(ValueError):
                    read_sqlite_artifact(self.root, self.root, changed)
        with patch(
            "mos_eisley.run.conversation_artifacts.sqlite_read_transaction"
        ) as transaction:
            with self.assertRaisesRegex(ValueError, "another session"):
                read_sqlite_artifact(
                    self.root, self.root, token, expected_session_id="0" * 32
                )
            transaction.assert_not_called()
        with self.assertRaisesRegex(ValueError, "workspace"):
            read_sqlite_artifact(self.root, self.root / "other", token)
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            state = store.load()
            store.save(state.model_copy(update={"revision": state.revision + 1}))
        with self.assertRaisesRegex(ValueError, "stale"):
            read_sqlite_artifact(self.root, self.root, token)

    def test_corrupt_or_missing_artifact_and_message_are_rejected(self) -> None:
        token = self.selection()
        value = json.loads(base64.urlsafe_b64decode(token))
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute(
                "UPDATE artifacts SET payload=? WHERE sid=? AND sha=?",
                (b"x" * value["bytes"], self.sid, value["sha256"]),
            )
        with self.assertRaisesRegex(ValueError, "artifact integrity"):
            read_sqlite_artifact(self.root, self.root, token)
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute(
                "DELETE FROM artifacts WHERE sid=? AND sha=?",
                (self.sid, value["sha256"]),
            )
        with self.assertRaisesRegex(ValueError, "missing"):
            read_sqlite_artifact(self.root, self.root, token)
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute(
                "UPDATE entries SET payload=? WHERE sid=? AND position=0",
                (b"{}", self.sid),
            )
        with self.assertRaisesRegex(ValueError, "message integrity"):
            read_sqlite_artifact(self.root, self.root, token)

    def test_invalid_schema_error_does_not_echo_artifact_content(self) -> None:
        # Build a digest-consistent malformed artifact/record/index to reach schema
        # validation. Deliberate same-user rewrites remain outside the trust model.
        token = self.replace_memory_payload(b'{"unexpected":"INVALID-ARTIFACT-CANARY"}')
        with self.assertRaisesRegex(ValueError, "schema or memory identity") as caught:
            read_sqlite_artifact(self.root, self.root, token)
        self.assertNotIn("INVALID-ARTIFACT-CANARY", str(caught.exception))

    def replace_memory_payload(self, payload: bytes) -> str:
        token = self.selection()
        value = json.loads(base64.urlsafe_b64decode(token))
        sha = digest(payload)
        with sqlite3.connect(self.root / DATABASE) as db:
            body = json.loads(
                db.execute(
                    "SELECT payload FROM entries WHERE sid=? AND position=0",
                    (self.sid,),
                ).fetchone()[0]
            )
            body["refs"]["memory_context"] = sha
            record = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            db.execute(
                "UPDATE entries SET payload=? WHERE sid=? AND position=0",
                (record, self.sid),
            )
            db.execute(
                "INSERT INTO artifacts VALUES (?, ?, ?)", (self.sid, sha, payload)
            )
            index = json.loads(
                db.execute(
                    "SELECT record FROM sessions WHERE sid=?", (self.sid,)
                ).fetchone()[0]
            )
            index["entry_sha256"][0] = digest(record)
            encoded = json.dumps(index, sort_keys=True, separators=(",", ":")).encode()
            db.execute(
                "UPDATE sessions SET record=?, record_sha=? WHERE sid=?",
                (encoded, digest(encoded), self.sid),
            )
        return base64.urlsafe_b64encode(
            json.dumps({**value, "sha256": sha, "bytes": len(payload)}).encode()
        ).decode()

    def test_default_budget_rejects_large_valid_payload_until_explicit_override(
        self,
    ) -> None:
        content = read_sqlite_artifact(self.root, self.root, self.selection())
        # Whitespace tests the actual stored-byte budget independently of typed
        # field limits and normalized output size.
        payload = json.dumps(content.content).encode() + b" " * 512_000
        token = self.replace_memory_payload(payload)
        with self.assertRaisesRegex(ValueError, "expansion limit is 512000"):
            read_sqlite_artifact(self.root, self.root, token)
        expanded = read_sqlite_artifact(
            self.root, self.root, token, max_bytes=len(payload)
        )
        self.assertEqual(expanded.content, content.content)
        self.assertEqual(expanded.bytes, len(payload))

    def test_other_session_commit_invalidates_selection(self) -> None:
        token = self.selection()
        state = ConversationController.fresh(self.root, demo_cassette())
        with SQLiteConversationStore(self.root, state.session_id, self.root) as store:
            store.save(state)
        with self.assertRaisesRegex(ValueError, "stale"):
            read_sqlite_artifact(self.root, self.root, token)

    def test_bad_arguments_and_missing_storage_create_nothing(self) -> None:
        token = self.selection()
        for limit in (0, 32_000_001, True):
            with self.assertRaises(ValueError):
                read_sqlite_artifact(self.root, self.root, token, max_bytes=limit)
        for invalid in ("!", "x" * 32001, "e30="):
            with self.assertRaisesRegex(ValueError, "invalid artifact selection"):
                read_sqlite_artifact(self.root / "absent", self.root, invalid)
        with self.assertRaises(FileNotFoundError):
            read_sqlite_artifact(self.root / "absent", self.root, token)
        self.assertFalse((self.root / "absent").exists())
        (self.root / DATABASE).chmod(0o644)
        with self.assertRaisesRegex(ValueError, "private"):
            read_sqlite_artifact(self.root, self.root, token)

    def test_cli_expands_one_selection_and_escapes_terminal_controls(self) -> None:
        token = self.selection()

        def invoke(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "session-artifact",
                    token,
                    "--storage",
                    str(self.root),
                    "-C",
                    str(self.root),
                    *args,
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )

        result = invoke("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["field"], "memory_context")
        self.assertNotIn("\x1b", result.stdout)
        self.assertIn("EXPANSION-CANARY", result.stdout)
        limited = invoke("--max-bytes", "1")
        self.assertEqual(limited.returncode, 2)
        self.assertEqual(limited.stdout, "")


async def until(predicate: Callable[[], bool]) -> None:
    async with asyncio.timeout(4):
        while not predicate():
            await asyncio.sleep(0.01)


class ArtifactUITests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sid = await asyncio.to_thread(make_fixture, self.root)
        self.store = SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        )
        self.addCleanup(self.store.close)
        state = self.store.load()
        assert state.retained_cassette is not None
        self.chat = ConversationController(
            state, state.retained_cassette, self.store.save
        )

    async def test_keyboard_selection_expansion_collapse_and_draft_preservation(
        self,
    ) -> None:
        before = canonical_bytes(self.chat.state)
        with create_pipe_input() as input:
            ui = ConversationTUI(
                self.chat,
                load_transcript=self.store.transcript_page,
                load_artifact=self.store.transcript_artifact,
                input=input,
                output=DummyOutput(),
            )
            history = ui.history
            assert history is not None
            task = asyncio.create_task(ui.run())
            try:
                await until(lambda: ui.app.is_running)
                input.send_text("UNSENT\x1b[15~")
                await until(lambda: history.page is not None and not history.loading)
                self.assertNotIn("EXPANSION-CANARY", ui.transcript.text)
                input.send_text("\x1b[19~")
                await until(
                    lambda: history.expanded is not None and not history.loading
                )
                self.assertIn("EXPANSION-CANARY", ui.transcript.text)
                self.assertNotIn("\x1b", ui.transcript.text)
                input.send_text("\x1b[18~")
                await until(lambda: history.selected_artifact == 1)
                self.assertIsNone(history.expanded)
                self.assertNotIn("EXPANSION-CANARY", ui.transcript.text)
                input.send_text("\x1b[19~")
                await until(
                    lambda: history.expanded is not None and not history.loading
                )
                assert history.expanded is not None
                self.assertEqual(history.expanded.field, "review_packet")
                input.send_text("\x1b[19~\x1b[15~")
                await until(lambda: not history.visible)
                self.assertIsNone(history.expanded)
                self.assertEqual(ui.editor.text, "UNSENT")
                self.assertEqual(canonical_bytes(self.chat.state), before)
            finally:
                input.send_text("\x04")
                await asyncio.wait_for(task, 4)

    async def test_obsolete_artifact_is_discarded_and_next_selection_waits(
        self,
    ) -> None:
        entered, release = threading.Event(), threading.Event()
        calls = 0

        def slow(selection: str) -> ArtifactContent:
            nonlocal calls
            calls += 1
            entered.set()
            if not release.wait(3):
                raise ValueError("test read timed out")
            return self.store.transcript_artifact(selection)

        history = TranscriptHistory(
            self.store.transcript_page,
            lambda: (self.sid, self.chat.state.revision, len(self.chat.state.entries)),
            lambda: None,
            slow,
        )
        try:
            history.reload()
            await until(lambda: not history.loading)
            history.toggle_artifact()
            await until(entered.is_set)
            history.select_next_artifact()
            history.toggle_artifact()
            self.assertEqual(calls, 1)
            release.set()
            await until(lambda: not history.loading)
            assert history.expanded is not None
            self.assertEqual(history.expanded.field, "review_packet")
            self.assertEqual(calls, 2)
            history.reload()
            self.assertIsNone(history.expanded)
        finally:
            release.set()
            await history.shutdown()

    async def test_wrong_artifact_response_never_enters_the_view(self) -> None:
        def wrong(selection: str) -> ArtifactContent:
            return self.store.transcript_artifact(selection).model_copy(
                update={"position": 15}
            )

        history = TranscriptHistory(
            self.store.transcript_page,
            lambda: (self.sid, self.chat.state.revision, len(self.chat.state.entries)),
            lambda: None,
            wrong,
        )
        try:
            history.reload()
            await until(lambda: not history.loading)
            history.toggle_artifact()
            await until(lambda: not history.loading)
            self.assertIsNone(history.expanded)
            self.assertIn("selection changed", history.artifact_error or "")
            self.assertIsNotNone(history.page)
        finally:
            await history.shutdown()
