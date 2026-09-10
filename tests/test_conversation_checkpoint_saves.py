"""Verified checkpoint reuse, external-write invalidation and commit boundaries."""

import asyncio
import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run import conversation_sqlite as backend
from mos_eisley.run.conversation_sqlite import (
    DATABASE,
    SQLiteConversationStore,
    list_sqlite_conversations,
)
from mos_eisley.run.conversation_store import ConversationSnapshot


class ObservedStore(SQLiteConversationStore):
    full_reads = 0
    allow_full_reads = True

    def _load(self, db: sqlite3.Connection) -> ConversationSnapshot:
        self.full_reads += 1
        if not self.allow_full_reads:
            raise AssertionError("unexpected full-state read")
        return super()._load(db)

    def trace(self, queries: list[str]) -> None:
        self._connection().set_trace_callback(queries.append)

    def reconnect(self) -> None:
        self._open_database(create=False, writable=True)

    def mutate_directly(self) -> None:
        self._connection().execute("UPDATE artifacts SET payload=?", (b"{}",))


class CheckpointSaveTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        memory_store = MemoryStore(self.root / "memory", self.root)
        memory_store.change("user", "set", text="CHECKPOINT-MEMORY-CANARY")
        self.memory = memory_store.load()
        self.cassette = demo_cassette(memory=self.memory)
        state = ConversationController.fresh(self.root, self.cassette, self.memory)
        self.store = ObservedStore(self.root, state.session_id, self.root)
        self.addCleanup(self.store.close)
        self.store.save(state)
        self.chat = ConversationController(state, self.cassette, self.store.save)

    def test_repeated_controller_transitions_read_no_old_payloads(self) -> None:
        self.store.allow_full_reads = False
        queries: list[str] = []
        self.store.trace(queries)
        for prompt in DEMO_PROMPTS:
            self.chat.submit(prompt)
            asyncio.run(self.chat.step())
        self.assertEqual(self.chat.state.exchanges_consumed, 2)
        selects = [query for query in queries if query.startswith("SELECT")]
        self.assertTrue(selects)
        self.assertFalse(
            any("payload" in query or "header" in query for query in selects)
        )
        # One insert/update per queued, running, completed transition. Earlier
        # completed messages never reach an upsert for subsequent messages.
        writes = [query for query in queries if query.startswith("INSERT INTO entries")]
        self.assertEqual(len(writes), 6)
        self.assertFalse(
            any(query.startswith("INSERT INTO artifacts") for query in queries)
        )
        self.assertFalse(
            any(query.startswith("DELETE FROM artifacts") for query in queries)
        )
        self.store.allow_full_reads = True
        self.assertEqual(self.store.load(), self.chat.state)

    def test_full_resume_establishes_reuse_and_read_only_browsing_keeps_it(
        self,
    ) -> None:
        sid = self.chat.state.session_id
        self.store.close()
        with ObservedStore(self.root, sid, self.root, create=False) as store:
            state = store.load()
            self.assertEqual(store.full_reads, 1)
            store.allow_full_reads = False
            list_sqlite_conversations(self.root, self.root)
            store.transcript_page(None)
            controller = ConversationController(state, self.cassette, store.save)
            controller.submit(DEMO_PROMPTS[0])
            asyncio.run(controller.step())
            self.assertEqual(store.full_reads, 1)

    def test_external_commit_in_another_session_forces_one_full_revalidation(
        self,
    ) -> None:
        before = self.store.full_reads
        other = ConversationController.fresh(self.root, demo_cassette())
        with SQLiteConversationStore(self.root, other.session_id, self.root) as store:
            store.save(other)
        self.chat.submit(DEMO_PROMPTS[0])
        self.assertEqual(self.store.full_reads, before + 1)
        self.store.allow_full_reads = False
        asyncio.run(self.chat.step())
        self.assertEqual(self.chat.state.exchanges_consumed, 1)

    def test_external_corruption_cannot_be_blessed_by_next_save(self) -> None:
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute("UPDATE artifacts SET payload=?", (b"{}",))
        before = (self.root / DATABASE).read_bytes()
        original = self.chat.state
        with self.assertRaisesRegex(ValueError, "artifact integrity"):
            self.chat.submit("must not overwrite corruption")
        self.assertEqual(self.chat.state, original)
        self.assertEqual((self.root / DATABASE).read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "persistence failed"):
            self.chat.submit("must reopen")

    def test_direct_connection_mutation_also_invalidates_verification(self) -> None:
        self.store.mutate_directly()
        with self.assertRaisesRegex(ValueError, "artifact integrity"):
            self.chat.submit("must revalidate")

    def test_valid_external_revision_still_rejects_stale_handle(self) -> None:
        updated = self.chat.state.model_copy(update={"revision": 1})
        with sqlite3.connect(self.root / DATABASE) as db:
            record, header = db.execute(
                "SELECT record, header FROM sessions"
            ).fetchone()
            index, packed = json.loads(record), json.loads(header)
            packed["body"]["revision"] = 1
            encoded_header = json.dumps(
                packed, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
            index["summary"]["revision"] = 1
            index["summary"]["snapshot_sha256"] = digest(canonical_bytes(updated))
            index["resume_checkpoint"]["header_sha256"] = digest(encoded_header)
            index["resume_checkpoint"]["header_bytes"] = len(encoded_header)
            encoded_index = json.dumps(index).encode()
            db.execute(
                "UPDATE sessions SET record=?, record_sha=?, header=?",
                (encoded_index, digest(encoded_index), encoded_header),
            )
        with self.assertRaisesRegex(ValueError, "changed outside"):
            self.chat.submit("must not replace a verified external revision")
        self.assertEqual(self.store.load(), updated)

    def test_external_commit_after_own_commit_invalidates_published_checkpoint(
        self,
    ) -> None:
        original_transaction = backend.conversation_transaction

        @contextmanager
        def racing(db: sqlite3.Connection, *, write: bool = False) -> Generator[None]:
            with original_transaction(db, write=write):
                yield
            if write:
                # The external commit lands before the store publishes its local
                # checkpoint. Its version must have been captured inside the lock.
                with sqlite3.connect(self.root / DATABASE) as external:
                    external.execute("UPDATE artifacts SET payload=?", (b"{}",))

        with patch.object(backend, "conversation_transaction", racing):
            self.chat.submit(DEMO_PROMPTS[0])
        with self.assertRaisesRegex(ValueError, "artifact integrity"):
            self.chat.submit("must revalidate the intervening commit")

    def test_external_record_changes_and_deletion_reject_stale_handle(self) -> None:
        sid = self.chat.state.session_id
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute("UPDATE sessions SET record_sha=? WHERE sid=?", ("0" * 64, sid))
        with self.assertRaisesRegex(ValueError, "index integrity"):
            self.store.save(self.chat.state.model_copy(update={"revision": 1}))
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute("DELETE FROM sessions WHERE sid=?", (sid,))
        with self.assertRaisesRegex(ValueError, "disappeared"):
            self.store.save(self.chat.state.model_copy(update={"revision": 1}))

    def test_failed_commit_never_publishes_checkpoint_or_advances_state(self) -> None:
        original_transaction = backend.conversation_transaction

        @contextmanager
        def fail(db: sqlite3.Connection, *, write: bool = False) -> Generator[None]:
            with original_transaction(db, write=write):
                yield
                if write:
                    raise OSError("injected checkpoint save commit failure")

        before = self.chat.state
        catalog = list_sqlite_conversations(self.root, self.root)
        with (
            patch.object(backend, "conversation_transaction", fail),
            self.assertRaises(OSError),
        ):
            self.chat.submit("rolled back")
        self.assertEqual(self.chat.state, before)
        self.assertEqual(list_sqlite_conversations(self.root, self.root), catalog)
        full_reads = self.store.full_reads
        # A direct caller may retry, but it must first revalidate the old state.
        self.store.save(before.model_copy(update={"revision": 1}))
        self.assertEqual(self.store.full_reads, full_reads + 1)
        self.assertEqual(self.store.load().entries, before.entries)

    def test_post_commit_error_does_not_allow_retry_from_old_revision(self) -> None:
        original_transaction = backend.conversation_transaction

        @contextmanager
        def uncertain(
            db: sqlite3.Connection, *, write: bool = False
        ) -> Generator[None]:
            with original_transaction(db, write=write):
                yield
            if write:
                raise OSError("injected failure after commit")

        state = self.chat.state
        updated = state.model_copy(update={"revision": 1})
        with (
            patch.object(backend, "conversation_transaction", uncertain),
            self.assertRaises(OSError),
        ):
            self.store.save(updated)
        with self.assertRaisesRegex(ValueError, "changed outside"):
            self.store.save(updated)
        self.assertEqual(self.store.load(), updated)

    def test_reconnected_database_never_reuses_connection_local_version(self) -> None:
        full_reads = self.store.full_reads
        self.store.reconnect()
        self.chat.submit(DEMO_PROMPTS[0])
        self.assertEqual(self.store.full_reads, full_reads + 1)

    def test_resize_does_not_rewrite_entries_or_artifacts(self) -> None:
        self.chat.submit(DEMO_PROMPTS[0])
        asyncio.run(self.chat.step())
        queries: list[str] = []
        self.store.trace(queries)
        self.store.allow_full_reads = False
        self.chat.resize_storage(8_000_000)
        self.assertFalse(
            any(
                "INTO entries" in query or "INTO artifacts" in query
                for query in queries
            )
        )
        self.assertFalse(
            any(query.startswith("SELECT") and "payload" in query for query in queries)
        )
        self.assertEqual(self.chat.state.snapshot_byte_limit, 8_000_000)

    def test_changed_memory_inserts_new_and_removes_only_unreferenced_artifacts(
        self,
    ) -> None:
        with sqlite3.connect(self.root / DATABASE) as db:
            old = set(row[0] for row in db.execute("SELECT sha FROM artifacts"))
        self.store.allow_full_reads = False
        self.chat.refresh_memory(None, demo_cassette(), disabled=True, builtin=True)
        with sqlite3.connect(self.root / DATABASE) as db:
            current = set(row[0] for row in db.execute("SELECT sha FROM artifacts"))
        self.assertTrue(old.isdisjoint(current))
        self.store.allow_full_reads = True
        self.assertEqual(self.store.load(), self.chat.state)

    def test_legacy_index_is_fully_verified_then_upgraded(self) -> None:
        sid = self.chat.state.session_id
        with sqlite3.connect(self.root / DATABASE) as db:
            index = json.loads(
                db.execute(
                    "SELECT record FROM sessions WHERE sid=?", (sid,)
                ).fetchone()[0]
            )
            index.pop("resume_checkpoint")
            index.pop("entry_sha256")
            payload = json.dumps(index).encode()
            db.execute(
                "UPDATE sessions SET record=?, record_sha=? WHERE sid=?",
                (payload, digest(payload), sid),
            )
        self.assertEqual(self.store.load(), self.chat.state)
        before = self.store.full_reads
        self.chat.submit(DEMO_PROMPTS[0])
        self.assertEqual(self.store.full_reads, before + 1)
        self.store.allow_full_reads = False
        asyncio.run(self.chat.step())

    def test_new_session_cannot_adopt_orphan_records(self) -> None:
        state = ConversationController.fresh(self.root, demo_cassette())
        record = canonical_bytes(backend.PackedPart(body={"text": "orphan"}, refs={}))
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute(
                "INSERT INTO entries VALUES (?, 0, ?, 0)", (state.session_id, record)
            )
        with (
            SQLiteConversationStore(self.root, state.session_id, self.root) as store,
            self.assertRaisesRegex(ValueError, "orphan"),
        ):
            store.save(state)
