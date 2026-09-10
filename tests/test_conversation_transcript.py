"""Page integrity, bounded reads, cursor isolation and legacy index preparation."""

import asyncio
import base64
import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation import ConversationController, ConversationEntry
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_memory_runtime import ConversationMemoryRuntime
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.demo import demo_inputs
from mos_eisley.run import conversation_sqlite as backend
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore
from mos_eisley.run.conversation_transcript import (
    MAX_TRANSCRIPT_PAGE_BYTES,
    read_sqlite_transcript,
)


class TranscriptTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = ConversationController.fresh(
            self.root, demo_cassette()
        ).model_copy(
            update={
                "entries": tuple(
                    ConversationEntry(text=f"message {i}") for i in range(8)
                )
            }
        )
        self.sid = self.state.session_id
        with SQLiteConversationStore(self.root, self.sid, self.root) as store:
            store.save(self.state)

    def files(self) -> dict[str, tuple[bytes, int]]:
        return {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.root.iterdir()
            if path.is_file()
        }

    def make_legacy(self) -> None:
        with sqlite3.connect(self.root / DATABASE) as db:
            record = json.loads(
                db.execute(
                    "SELECT record FROM sessions WHERE sid=?", (self.sid,)
                ).fetchone()[0]
            )
            del record["entry_sha256"]
            payload = json.dumps(
                record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
            db.execute(
                "UPDATE sessions SET record=?, record_sha=? WHERE sid=?",
                (payload, digest(payload), self.sid),
            )

    def test_pages_are_read_only_bounded_and_work_while_session_is_open(self) -> None:
        before = self.files()
        queries: list[str] = []
        original = sqlite3.connect

        def traced(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            db = original(*args, **kwargs)
            db.set_trace_callback(queries.append)

            def authorize(
                action: int,
                table: str | None,
                column: str | None,
                database: str | None,
                source: str | None,
            ) -> int:
                if (
                    action == sqlite3.SQLITE_READ
                    and table == "sessions"
                    and column == "header"
                ):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            db.set_authorizer(authorize)
            return db

        with (
            SQLiteConversationStore(self.root, self.sid, self.root, create=False),
            patch.object(backend.sqlite3, "connect", traced),
        ):
            first = read_sqlite_transcript(self.root, self.sid, self.root, limit=3)
        self.assertEqual(
            [row.content.text for row in first.entries],
            [f"message {i}" for i in range(3)],
        )
        payload_reads = [
            query
            for query in queries
            if query.startswith("SELECT CASE WHEN length(payload)=")
        ]
        self.assertEqual(len(payload_reads), 3)
        self.assertTrue(all(f"position={i}" in payload_reads[i] for i in range(3)))
        second = read_sqlite_transcript(
            self.root, self.sid, self.root, limit=5, cursor=first.next_cursor
        )
        self.assertEqual([row.position for row in second.entries], list(range(3, 8)))
        self.assertIsNone(second.next_cursor)
        self.assertEqual(first.snapshot_sha256, digest(canonical_bytes(self.state)))
        self.assertEqual(self.files(), before)

    def test_byte_admission_stops_before_fetching_next_payload(self) -> None:
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            state = store.load().model_copy(
                update={
                    "revision": 1,
                    "entries": tuple(
                        ConversationEntry(text="😀" * 8000) for _ in range(16)
                    ),
                }
            )
            store.save(state)
        first = read_sqlite_transcript(self.root, self.sid, self.root, limit=16)
        self.assertEqual(len(first.entries), 15)
        self.assertLessEqual(first.record_bytes, MAX_TRANSCRIPT_PAGE_BYTES)
        last = read_sqlite_transcript(
            self.root, self.sid, self.root, limit=16, cursor=first.next_cursor
        )
        self.assertEqual([row.position for row in last.entries], [15])
        self.assertIsNone(last.next_cursor)

    def test_selected_corruption_fails_and_off_page_content_is_not_read(self) -> None:
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute(
                "UPDATE entries SET payload=? WHERE sid=? AND position=7",
                (b"{}", self.sid),
            )
        first = read_sqlite_transcript(self.root, self.sid, self.root, limit=7)
        self.assertEqual(len(first.entries), 7)
        with self.assertRaisesRegex(ValueError, "integrity"):
            read_sqlite_transcript(
                self.root, self.sid, self.root, cursor=first.next_cursor
            )
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute("DELETE FROM entries WHERE sid=? AND position=0", (self.sid,))
        with self.assertRaisesRegex(ValueError, "bounds|missing"):
            read_sqlite_transcript(self.root, self.sid, self.root)

    def test_stale_foreign_and_malformed_cursors_fail(self) -> None:
        first = read_sqlite_transcript(self.root, self.sid, self.root, limit=1)
        assert first.next_cursor is not None
        token = json.loads(base64.urlsafe_b64decode(first.next_cursor))
        for field, value in (
            ("owner_uid", os.getuid() + 1),
            ("store_id", "0" * 32),
            ("workspace", "/other"),
            ("session_id", "0" * 32),
            ("snapshot_sha256", "0" * 64),
            ("position", 15),
        ):
            with self.subTest(field=field):
                cursor = base64.urlsafe_b64encode(
                    json.dumps({**token, field: value}).encode()
                ).decode()
                with self.assertRaisesRegex(ValueError, "stale or foreign"):
                    read_sqlite_transcript(
                        self.root, self.sid, self.root, cursor=cursor
                    )
        for cursor in ("!", "x" * 32001, base64.urlsafe_b64encode(b"{}").decode()):
            with self.assertRaisesRegex(ValueError, "invalid transcript cursor"):
                read_sqlite_transcript(self.root, self.sid, self.root, cursor=cursor)
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            state = store.load()
            store.save(state.model_copy(update={"revision": 1}))
        with self.assertRaisesRegex(ValueError, "stale or foreign"):
            read_sqlite_transcript(
                self.root, self.sid, self.root, cursor=first.next_cursor
            )

    def test_review_and_memory_are_references_without_artifact_decoding(self) -> None:
        memory = MemoryStore(self.root / "memory", self.root)
        memory.change("user", "set", text="PAGE-MEMORY-CANARY")
        selected = memory.load()
        cassette = demo_cassette(memory=selected)
        state = ConversationController.fresh(self.root, cassette, selected)
        brief, recording = demo_inputs()
        with SQLiteConversationStore(self.root, state.session_id, self.root) as store:
            store.save(state)
            controller = ConversationController(state, cassette, store.save)
            controller.submit(DEMO_PROMPTS[0])
            asyncio.run(controller.step())
            ConversationMemoryRuntime(
                controller, memory, lambda selected: demo_cassette(memory=selected)
            ).refresh(True)
            controller.submit_review(
                ConversationReviewPacket(brief=brief, cassette=recording)
            )
            asyncio.run(controller.step())
        queries: list[str] = []
        original = sqlite3.connect

        def traced(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            db = original(*args, **kwargs)
            db.set_trace_callback(queries.append)
            return db

        with patch.object(backend.sqlite3, "connect", traced):
            page = read_sqlite_transcript(self.root, state.session_id, self.root)
        artifact_reads = [query for query in queries if "FROM artifacts" in query]
        self.assertEqual(len(artifact_reads), 3)
        self.assertTrue(
            all(query.startswith("SELECT length(payload)") for query in artifact_reads)
        )
        self.assertNotIn("PAGE-MEMORY-CANARY", page.model_dump_json())
        self.assertEqual(
            [ref.field for ref in page.entries[0].artifacts], ["memory_context"]
        )
        self.assertEqual(
            [ref.field for ref in page.entries[1].artifacts],
            ["review_packet", "review_result"],
        )
        sha = page.entries[0].artifacts[0].sha256
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute(
                "UPDATE artifacts SET payload=? WHERE sid=? AND sha=?",
                (b"invalid-json", state.session_id, sha),
            )
        # Pages verify record hashes and reference availability/size. Full artifact
        # integrity remains a full-load check until explicit expansion is implemented.
        read_sqlite_transcript(self.root, state.session_id, self.root)
        with (
            SQLiteConversationStore(
                self.root, state.session_id, self.root, create=False
            ) as store,
            self.assertRaisesRegex(ValueError, "artifact integrity"),
        ):
            store.load()
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute(
                "DELETE FROM artifacts WHERE sid=? AND sha=?", (state.session_id, sha)
            )
        with self.assertRaisesRegex(ValueError, "missing transcript artifact"):
            read_sqlite_transcript(self.root, state.session_id, self.root)

    def test_legacy_preparation_preserves_state_records_and_timestamp(self) -> None:
        self.make_legacy()
        with sqlite3.connect(self.root / DATABASE) as db:
            payload = db.execute(
                "SELECT payload FROM entries WHERE sid=? AND position=0", (self.sid,)
            ).fetchone()[0]
            db.execute(
                "UPDATE entries SET payload=? WHERE sid=? AND position=0",
                (b"\n " + payload + b"\n", self.sid),
            )
        before = self.files()
        with self.assertRaisesRegex(ValueError, "index is unavailable"):
            read_sqlite_transcript(self.root, self.sid, self.root)
        self.assertEqual(self.files(), before)
        with sqlite3.connect(self.root / DATABASE) as db:
            records = db.execute("SELECT * FROM entries").fetchall()
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            self.assertEqual(store.load(), self.state)
            with self.assertRaisesRegex(ValueError, "changed"):
                store.prepare_transcript("0" * 64)
            summary = store.prepare_transcript(digest(canonical_bytes(self.state)))
            self.assertEqual(store.load(), self.state)
            prepared = self.files()
            store.prepare_transcript(summary.snapshot_sha256)
            self.assertEqual(self.files(), prepared)
        with sqlite3.connect(self.root / DATABASE) as db:
            self.assertEqual(db.execute("SELECT * FROM entries").fetchall(), records)
            row = db.execute(
                "SELECT modified_ns FROM sessions WHERE sid=?", (self.sid,)
            ).fetchone()
            self.assertEqual(row[0], summary.modified_ns)
        self.assertEqual(
            read_sqlite_transcript(self.root, self.sid, self.root).revision, 0
        )

    def test_preparation_rollback_and_normal_save_upgrade(self) -> None:
        self.make_legacy()
        original = backend.conversation_transaction

        @contextmanager
        def fail(db: sqlite3.Connection, *, write: bool = False) -> Generator[None]:
            with original(db, write=write):
                yield
                if write:
                    raise OSError("injected prepare commit failure")

        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            with (
                patch.object(backend, "conversation_transaction", fail),
                self.assertRaises(OSError),
            ):
                store.prepare_transcript(digest(canonical_bytes(self.state)))
            with self.assertRaisesRegex(ValueError, "index is unavailable"):
                read_sqlite_transcript(self.root, self.sid, self.root)
            state = store.load()
            store.save(state.model_copy(update={"revision": 1}))
        self.assertEqual(
            read_sqlite_transcript(self.root, self.sid, self.root).revision, 1
        )

    def test_private_owner_workspace_and_missing_store_checks(self) -> None:
        before = self.files()
        with self.assertRaises(FileNotFoundError):
            read_sqlite_transcript(self.root / "missing", self.sid, self.root)
        self.assertFalse((self.root / "missing").exists())
        for limit in (0, 17, True):
            with self.assertRaisesRegex(ValueError, "page size"):
                read_sqlite_transcript(self.root, self.sid, self.root, limit=limit)
        with self.assertRaisesRegex(ValueError, "workspace"):
            read_sqlite_transcript(self.root, self.sid, self.root / "other")
        self.assertEqual(self.files(), before)
        (self.root / DATABASE).chmod(0o644)
        with self.assertRaisesRegex(ValueError, "private"):
            read_sqlite_transcript(self.root, self.sid, self.root)
        (self.root / DATABASE).chmod(0o600)
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute("UPDATE metadata SET owner_uid=?", (os.getuid() + 1,))
        with self.assertRaisesRegex(ValueError, "ownership"):
            read_sqlite_transcript(self.root, self.sid, self.root)

    def test_empty_session_and_missing_session(self) -> None:
        state = ConversationController.fresh(self.root, demo_cassette())
        with SQLiteConversationStore(self.root, state.session_id, self.root) as store:
            store.save(state)
        page = read_sqlite_transcript(self.root, state.session_id, self.root)
        self.assertEqual(page.entries, ())
        self.assertIsNone(page.next_cursor)
        with self.assertRaises(FileNotFoundError):
            read_sqlite_transcript(self.root, "0" * 32, self.root)

    def test_reader_observes_committed_state_during_another_transaction(self) -> None:
        with sqlite3.connect(self.root / DATABASE) as writer:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute(
                "UPDATE entries SET payload=? WHERE sid=? AND position=0",
                (b"unfinished write", self.sid),
            )
            page = read_sqlite_transcript(self.root, self.sid, self.root)
            self.assertEqual(page.entries[0].content.text, "message 0")
            writer.rollback()
        cursor = page.next_cursor
        other = ConversationController.fresh(self.root, demo_cassette())
        with SQLiteConversationStore(self.root, other.session_id, self.root) as store:
            store.save(other)
        with self.assertRaisesRegex(ValueError, "stale or foreign"):
            read_sqlite_transcript(self.root, self.sid, self.root, cursor=cursor)

    def test_cli_preparation_paging_and_terminal_safe_output(self) -> None:
        self.make_legacy()

        def invoke(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    "session-transcript",
                    self.sid,
                    "--storage",
                    str(self.root),
                    "-C",
                    str(self.root),
                    *args,
                ],
                text=True,
                capture_output=True,
                timeout=20,
                env={**os.environ, "HOME": str(self.root)},
            )

        for args in (
            (),
            ("--prepare",),
            ("--expected-sha256", "0" * 64),
            ("--prepare", "--expected-sha256", "0" * 64, "--limit", "1"),
        ):
            result = invoke(*args)
            self.assertEqual(result.returncode, 2, result.stderr)
        prepared = invoke(
            "--prepare", "--expected-sha256", digest(canonical_bytes(self.state))
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        first = invoke("--limit", "2", "--json")
        self.assertEqual(first.returncode, 0, first.stderr)
        payload = json.loads(first.stdout)
        self.assertEqual(len(payload["entries"]), 2)
        second = invoke("--cursor", payload["next_cursor"])
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["entries"][0]["position"], 2)
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            state = store.load()
            store.save(
                state.model_copy(
                    update={
                        "revision": 1,
                        "entries": (
                            ConversationEntry(text="terminal\x1b[31m\ncanary"),
                        ),
                    }
                )
            )
        escaped = invoke()
        self.assertEqual(escaped.returncode, 0, escaped.stderr)
        self.assertNotIn("\x1b", escaped.stdout)
