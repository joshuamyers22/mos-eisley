"""Reference-based controller state, streamed saves and exact recovery semantics."""

import asyncio
import gc
import json
import os
import sqlite3
import subprocess
import sys
import weakref
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation import (
    ConversationController,
    ConversationEntry,
    ConversationState,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_context import context_turns
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    WorkingConversationState,
)
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.demo import demo_inputs
from mos_eisley.run import conversation_sqlite as backend
from mos_eisley.run.conversation_sqlite import (
    DATABASE,
    SQLiteConversationStore,
    list_sqlite_conversations,
)
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore


class ObservedStore(SQLiteConversationStore):
    allow_full_reads = True
    full_reads = 0
    cold_reads = 0
    fail_stream = False
    chunks: list[int]

    def _artifact_chunks(
        self,
        db: sqlite3.Connection,
        sha: str,
        artifacts: dict[str, bytes],
        retained: frozenset[str],
    ) -> Generator[bytes]:
        with closing(super()._artifact_chunks(db, sha, artifacts, retained)) as chunks:
            for chunk in chunks:
                if sha not in artifacts:
                    self.chunks.append(len(chunk))
                yield chunk
                if self.fail_stream and sha not in artifacts:
                    raise OSError("stream interrupted")

    def _load(self, db: sqlite3.Connection) -> ConversationSnapshot:
        self.full_reads += 1
        if not self.allow_full_reads:
            raise AssertionError("unexpected full-state hydration")
        return super()._load(db)

    def _load_working(self, db: sqlite3.Connection) -> WorkingConversationState | None:
        self.cold_reads += 1
        return super()._load_working(db)

    def trace(self, queries: list[str]) -> None:
        self._connection().set_trace_callback(queries.append)

    def direct_corruption(self) -> None:
        self._connection().execute("UPDATE artifacts SET payload=?", (b"{}",))

    def reconnect(self) -> None:
        self._open_database(create=False, writable=True)

    def transaction_open(self) -> bool:
        return self._connection().in_transaction


class WorkingStateTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = self.root / "sessions"
        self.memory_store = MemoryStore(self.root / "memory", self.root)
        self.memory_store.change("user", "set", text='ORIGINAL MEMORY é\n"' * 1000)
        self.memory = self.memory_store.load()
        self.cassette = demo_cassette(memory=self.memory)
        state = ConversationController.fresh(self.root, self.cassette, self.memory)
        self.store = ObservedStore(self.storage, state.session_id, self.root)
        self.addCleanup(self.store.close)
        self.store.chunks = []
        self.store.save(state)
        full = ConversationController(state, self.cassette, self.store.save)
        full.refresh_memory(self.memory, self.cassette)
        full.submit(DEMO_PROMPTS[0])
        asyncio.run(full.step())
        self.original = full.state
        loaded = self.store.load_working()
        assert isinstance(loaded, WorkingConversationState)
        self.chat = ConversationController(
            loaded,
            self.cassette,
            self.store.save_working,
            load_entry=self.store.load_working_entry,
        )

    def check_snapshot(self) -> ConversationState:
        self.store.allow_full_reads = True
        sha = self.store.snapshot_sha256
        full = self.store.load()
        self.assertEqual(sha, digest(canonical_bytes(full)))
        summary = list_sqlite_conversations(self.storage, self.root).sessions[0]
        self.assertEqual(
            summary.snapshot_bytes,
            len(
                canonical_bytes(
                    ConversationSnapshot(
                        state=full, sha256=digest(canonical_bytes(full))
                    )
                )
            ),
        )
        self.assertEqual(summary.revision, self.chat.state.revision)
        self.assertEqual(summary.messages, len(self.chat.state.entries))
        return full

    def test_cold_verification_releases_historical_values_and_preserves_hash(
        self,
    ) -> None:
        self.assertIsInstance(self.chat.state.entries[0], ArchivedConversationEntry)
        self.assertIsNone(self.chat.state.entries[0].memory_context)
        self.assertEqual(
            self.store.snapshot_sha256, digest(canonical_bytes(self.original))
        )
        self.assertEqual(self.chat.state.memory, self.original.memory)
        self.assertEqual(
            self.chat.state.retained_cassette, self.original.retained_cassette
        )
        with self.assertRaises(ValueError):
            ConversationState.model_validate_json(self.chat.state.model_dump_json())
        self.assertEqual(self.check_snapshot(), self.original)

    def test_healthy_transitions_stream_old_artifacts_without_full_state_hydration(
        self,
    ) -> None:
        self.store.allow_full_reads = False
        queries: list[str] = []
        self.store.trace(queries)
        self.chat.submit(DEMO_PROMPTS[1])
        asyncio.run(self.chat.step())
        self.chat.resize_context(4000)
        self.chat.resize_storage(4_000_000)
        self.assertTrue(self.store.chunks)
        self.assertLessEqual(max(self.store.chunks), backend.STREAM_CHUNK_BYTES)
        self.assertEqual(
            sum(query.startswith("INSERT INTO entries") for query in queries), 3
        )
        self.assertFalse(
            any(
                "THEN payload END" in query or query.startswith("SELECT payload")
                for query in queries
            )
        )
        full = self.check_snapshot()
        self.assertEqual(full.entries[1].answer, "You gave me a boundary of ten.")
        self.assertEqual(full.exchanges_consumed, 2)
        self.assertTrue(
            all(
                isinstance(entry, ArchivedConversationEntry)
                for entry in self.chat.state.entries
            )
        )

    def test_memory_refresh_preserves_historical_selection_and_collects_old_header(
        self,
    ) -> None:
        self.store.allow_full_reads = False
        self.memory_store.change("user", "set", text="NEW MEMORY")
        memory = self.memory_store.load()
        fresh = demo_cassette(memory=memory)
        cassette = fresh.model_copy(
            update={"exchanges": (self.cassette.exchanges[0], fresh.exchanges[1])}
        )
        self.chat.refresh_memory(memory, cassette)
        self.chat.submit(DEMO_PROMPTS[1])
        asyncio.run(self.chat.step())
        full = self.check_snapshot()
        self.assertEqual(full.memory, memory)
        assert full.entries[0].memory_context is not None
        assert full.entries[1].memory_context is not None
        self.assertEqual(full.entries[0].memory_context.memory, self.memory)
        self.assertEqual(full.entries[1].memory_context.memory, memory)

    def test_review_hydrates_only_requested_packet_and_keeps_one_result(self) -> None:
        brief, cassette = demo_inputs()
        packet = ConversationReviewPacket(brief=brief, cassette=cassette)
        self.store.allow_full_reads = False
        for _ in range(2):
            self.chat.submit_review(packet)
            pending = self.chat.state.entries[-1]
            self.assertIsInstance(pending, ArchivedConversationEntry)
            self.assertIsNone(pending.review_packet)
            self.assertTrue(pending.is_review)
            asyncio.run(self.chat.step())
        self.assertEqual(
            sum(entry.review_result is not None for entry in self.chat.state.entries), 1
        )
        self.assertEqual(self.chat.state.entries[-1].review_brief_id, brief.brief_id)
        self.assertEqual(self.chat.state.exchanges_consumed, 1)
        full = self.check_snapshot()
        self.assertTrue(
            all(entry.review_result is not None for entry in full.entries[1:])
        )
        self.assertEqual(full.entries[-1].review_packet, packet)

    def test_archived_running_review_recovers_without_replaying_it(self) -> None:
        brief, cassette = demo_inputs()
        packet = ConversationReviewPacket(brief=brief, cassette=cassette)
        self.chat.submit_review(packet)
        index = len(self.chat.state.entries) - 1
        pending = self.chat.state.entries[index]
        assert isinstance(pending, ArchivedConversationEntry)
        hydrated = self.store.load_working_entry(index, pending)
        running = self.chat.state.model_copy(
            update={
                "revision": self.chat.state.revision + 1,
                "entries": self.chat.state.entries[:-1]
                + (hydrated.model_copy(update={"status": "running"}),),
            }
        )
        running = self.store.save_working(running)
        self.store.allow_full_reads = False
        self.chat = ConversationController(
            running,
            self.cassette,
            self.store.save_working,
            load_entry=self.store.load_working_entry,
        )
        self.assertEqual(self.chat.state.entries[-1].status, "interrupted")
        self.assertEqual(self.chat.state.exchanges_consumed, 1)
        self.assertFalse(asyncio.run(self.chat.step()))
        self.check_snapshot()

    def test_cancel_queued_archived_reviews_does_not_hydrate_packets(self) -> None:
        brief, cassette = demo_inputs()
        self.chat.submit_review(
            ConversationReviewPacket(brief=brief, cassette=cassette)
        )
        self.store.allow_full_reads = False
        with patch.object(
            self.chat, "load_entry", side_effect=AssertionError("packet hydrated")
        ):
            self.chat.cancel_queued()
        self.assertEqual(self.chat.state.entries[-1].status, "cancelled")
        self.check_snapshot()

    def test_forged_archive_body_reference_position_and_metadata_rejected(self) -> None:
        original = self.chat.state.entries[0]
        assert isinstance(original, ArchivedConversationEntry)
        for changes in (
            {"answer": "forged answer"},
            {"text": "forged prompt"},
            {"source_sha256": "0" * 64},
            {"artifact_refs": {"memory_context": "0" * 64}},
            {"status": "failed", "answer": None, "usage": None},
        ):
            with self.subTest(changes=changes):
                before = self.store.snapshot_sha256
                candidate = self.chat.state.model_copy(
                    update={
                        "revision": self.chat.state.revision + 1,
                        "entries": (original.model_copy(update=changes),),
                    }
                )
                with self.assertRaises(ValueError):
                    self.store.save_working(candidate)
                self.assertEqual(self.store.snapshot_sha256, before)
                self.assertEqual(self.store.load(), self.original)
        for position in (-1, 16, True):
            with self.subTest(position=position), self.assertRaises(ValueError):
                self.store.load_working_entry(position, original)

    def test_external_unrelated_commit_requires_one_cold_revalidation(self) -> None:
        other = ConversationController.fresh(self.root, self.cassette)
        with SQLiteConversationStore(
            self.storage, other.session_id, self.root
        ) as store:
            store.save(other)
        before = self.store.cold_reads
        self.store.allow_full_reads = False
        self.chat.resize_context(4000)
        self.assertEqual(self.store.cold_reads, before + 1)
        self.store.allow_full_reads = False
        self.chat.resize_context(8000)
        self.check_snapshot()

    def test_valid_external_revision_cannot_be_overwritten(self) -> None:
        updated = self.original.model_copy(
            update={"revision": self.original.revision + 1, "context_max_bytes": 8000}
        )
        sha = digest(canonical_bytes(updated))
        with sqlite3.connect(self.storage / DATABASE) as db:
            row = db.execute(
                "SELECT record, header FROM sessions WHERE sid=?", (updated.session_id,)
            ).fetchone()
            record, header = json.loads(row[0]), json.loads(row[1])
            header["body"].update(revision=updated.revision, context_max_bytes=8000)
            raw_header = json.dumps(
                header, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
            record["summary"].update(
                revision=updated.revision,
                snapshot_sha256=sha,
                snapshot_bytes=len(
                    canonical_bytes(ConversationSnapshot(state=updated, sha256=sha))
                ),
            )
            record["resume_checkpoint"].update(
                header_sha256=digest(raw_header), header_bytes=len(raw_header)
            )
            raw = json.dumps(
                record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
            db.execute(
                "UPDATE sessions SET record=?, record_sha=?, header=? WHERE sid=?",
                (raw, digest(raw), raw_header, updated.session_id),
            )
            db.execute("UPDATE metadata SET generation=generation+1")
        before = self.chat.state
        with self.assertRaisesRegex(ValueError, "changed outside"):
            self.chat.resize_context(4000)
        self.assertEqual(self.chat.state, before)
        self.assertEqual(self.store.load(), updated)

    def test_logical_budget_rejection_preserves_snapshot_and_closes_stream(
        self,
    ) -> None:
        for _ in range(8):
            self.chat.submit("x" * 8000)
        before = self.chat.state
        sha = self.store.snapshot_sha256
        with self.assertRaisesRegex(ValueError, "saved byte limit"):
            self.chat.resize_storage(64_000)
        self.assertEqual(self.chat.state, before)
        self.assertFalse(self.store.transaction_open())
        self.assertEqual(digest(canonical_bytes(self.store.load())), sha)

    def test_direct_corruption_rejects_next_transition_and_poisoned_controller(
        self,
    ) -> None:
        before = self.chat.state
        self.store.direct_corruption()
        with self.assertRaises(ValueError):
            self.chat.resize_context(4000)
        self.assertEqual(self.chat.state, before)
        with self.assertRaisesRegex(ValueError, "persistence failed"):
            self.chat.submit("later")

    def test_reconnect_requires_cold_verification_before_reusing_references(
        self,
    ) -> None:
        self.store.reconnect()
        before = self.store.cold_reads
        self.store.allow_full_reads = False
        self.chat.resize_context(4000)
        self.assertEqual(self.store.cold_reads, before + 1)
        self.check_snapshot()

    def test_rollback_and_post_commit_failure_require_reopen(self) -> None:
        transaction = backend.conversation_transaction
        for committed in (False, True):
            with self.subTest(committed=committed):
                loaded = self.store.load_working()
                assert isinstance(loaded, WorkingConversationState)
                self.chat = ConversationController(
                    loaded,
                    self.cassette,
                    self.store.save_working,
                    load_entry=self.store.load_working_entry,
                )
                before = self.chat.state

                @contextmanager
                def interrupted(
                    db: sqlite3.Connection,
                    *,
                    write: bool = False,
                    after: bool = committed,
                ) -> Generator[None]:
                    with transaction(db, write=write):
                        yield
                        if write and not after:
                            raise OSError("rollback fixture")
                    if write and after:
                        raise OSError("uncertain commit fixture")

                with (
                    patch.object(backend, "conversation_transaction", interrupted),
                    self.assertRaises(OSError),
                ):
                    self.chat.resize_context(4000 if not committed else 8000)
                self.assertEqual(self.chat.state, before)
                self.assertFalse(self.store.transaction_open())
                saved = self.store.load()
                self.assertEqual(saved.revision, before.revision + int(committed))
                self.assertEqual(saved.exchanges_consumed, before.exchanges_consumed)

    def test_stream_failure_closes_blob_and_rolls_back(self) -> None:
        before = self.chat.state
        self.store.fail_stream = True
        with self.assertRaises(OSError):
            self.chat.resize_context(4000)
        self.assertEqual(self.chat.state, before)
        self.assertFalse(self.store.transaction_open())
        self.assertEqual(self.store.load(), self.original)

    def test_active_hydration_budget_checked_before_fetching_artifact(self) -> None:
        brief, cassette = demo_inputs()
        self.chat.submit_review(
            ConversationReviewPacket(brief=brief, cassette=cassette)
        )
        before = self.chat.state
        with (
            patch.object(backend, "MAX_ACTIVE_ENTRY_BYTES", 1),
            patch.object(
                backend,
                "_artifact_chunks",
                side_effect=AssertionError("payload read before admission"),
            ),
            self.assertRaisesRegex(ValueError, "oversized"),
        ):
            asyncio.run(self.chat.step())
        self.assertEqual(self.chat.state, before)
        asyncio.run(self.chat.step())
        self.check_snapshot()

    def test_legacy_index_falls_back_until_saved_and_reopened(self) -> None:
        with sqlite3.connect(self.storage / DATABASE) as db:
            row = db.execute(
                "SELECT record FROM sessions WHERE sid=?", (self.chat.state.session_id,)
            ).fetchone()
            record = json.loads(row[0])
            record.pop("entry_sha256")
            record.pop("resume_checkpoint")
            raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            db.execute(
                "UPDATE sessions SET record=?, record_sha=? WHERE sid=?",
                (raw, digest(raw), self.chat.state.session_id),
            )
        full = self.store.load_working()
        self.assertNotIsInstance(full, WorkingConversationState)
        assert not isinstance(full, WorkingConversationState)
        controller = ConversationController(full, self.cassette, self.store.save)
        controller.resize_context(4000)
        self.assertIsInstance(self.store.load_working(), WorkingConversationState)

    def test_noncanonical_artifact_uses_compatibility_path_until_normal_save(
        self,
    ) -> None:
        entry = self.chat.state.entries[0]
        assert isinstance(entry, ArchivedConversationEntry)
        old_sha = entry.artifact_refs["memory_context"]
        with sqlite3.connect(self.storage / DATABASE) as db:
            artifact = db.execute(
                "SELECT payload FROM artifacts WHERE sid=? AND sha=?",
                (self.chat.state.session_id, old_sha),
            ).fetchone()[0]
            payload = json.dumps(json.loads(artifact), indent=2).encode()
            sha = digest(payload)
            db.execute(
                "UPDATE artifacts SET sha=?, payload=? WHERE sid=? AND sha=?",
                (sha, payload, self.chat.state.session_id, old_sha),
            )
            raw_entry = db.execute(
                "SELECT payload FROM entries WHERE sid=? AND position=0",
                (self.chat.state.session_id,),
            ).fetchone()[0]
            part = json.loads(raw_entry)
            part["refs"]["memory_context"] = sha
            raw_entry = json.dumps(part, sort_keys=True, separators=(",", ":")).encode()
            db.execute(
                "UPDATE entries SET payload=? WHERE sid=? AND position=0",
                (raw_entry, self.chat.state.session_id),
            )
            record = json.loads(
                db.execute(
                    "SELECT record FROM sessions WHERE sid=?",
                    (self.chat.state.session_id,),
                ).fetchone()[0]
            )
            record["entry_sha256"][0] = digest(raw_entry)
            record["resume_checkpoint"]["entries"][0]["bytes"] = len(raw_entry)
            raw_record = json.dumps(
                record, sort_keys=True, separators=(",", ":")
            ).encode()
            db.execute(
                "UPDATE sessions SET record=?, record_sha=? WHERE sid=?",
                (raw_record, digest(raw_record), self.chat.state.session_id),
            )
        full = self.store.load_working()
        self.assertEqual(full, self.original)
        assert not isinstance(full, WorkingConversationState)
        controller = ConversationController(full, self.cassette, self.store.save)
        controller.resize_context(4000)
        self.assertIsInstance(self.store.load_working(), WorkingConversationState)

    def test_prepared_legacy_entry_defaults_are_preserved_during_recovery(self) -> None:
        brief, cassette = demo_inputs()
        self.chat.submit_review(
            ConversationReviewPacket(brief=brief, cassette=cassette)
        )
        sid = self.chat.state.session_id
        with sqlite3.connect(self.storage / DATABASE) as db:
            part = json.loads(
                db.execute(
                    "SELECT payload FROM entries WHERE sid=? AND position=1", (sid,)
                ).fetchone()[0]
            )
            for key in ("status", "answer", "usage"):
                part["body"].pop(key)
            payload = json.dumps(part, indent=2).encode()
            db.execute(
                "UPDATE entries SET payload=? WHERE sid=? AND position=1",
                (payload, sid),
            )
            record = json.loads(
                db.execute(
                    "SELECT record FROM sessions WHERE sid=?", (sid,)
                ).fetchone()[0]
            )
            record["entry_sha256"][1] = digest(payload)
            record["resume_checkpoint"]["entries"][1]["bytes"] = len(payload)
            raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            db.execute(
                "UPDATE sessions SET record=?, record_sha=? WHERE sid=?",
                (raw, digest(raw), sid),
            )
        loaded = self.store.load_working()
        assert isinstance(loaded, WorkingConversationState)
        self.chat = ConversationController(
            loaded,
            self.cassette,
            self.store.save_working,
            load_entry=self.store.load_working_entry,
        )
        self.chat.cancel_queued()
        self.assertEqual(self.check_snapshot().entries[1].status, "cancelled")

    def test_json_backend_rejects_reference_based_state(self) -> None:
        with ConversationStore(
            self.root / "json", self.chat.state.session_id, self.root
        ) as store:
            with self.assertRaises(ValueError):
                ConversationState.model_validate_json(self.chat.state.model_dump_json())
            self.assertFalse((self.root / "json" / f"{store.session_id}.json").exists())


class WorkingStateCLITests(TestCase):
    def test_review_events_and_latest_result_survive_working_resume(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            brief, cassette = demo_inputs()
            packet = root / "review.json"
            packet.write_bytes(
                canonical_bytes(
                    ConversationReviewPacket(brief=brief, cassette=cassette)
                )
            )

            def invoke(*args: str, text: str = "") -> list[dict[str, object]]:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "mos_eisley.cli",
                        *args,
                        "--storage-backend",
                        "sqlite",
                        "-C",
                        str(root),
                        "--json",
                    ],
                    input=text,
                    text=True,
                    capture_output=True,
                    env={**os.environ, "HOME": str(root)},
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return [json.loads(line) for line in result.stdout.splitlines()]

            events = invoke(
                "chat", "--review-packet", str(packet), text="/review\n/review\n"
            )
            completed = [
                event for event in events if event["type"] == "message.completed"
            ]
            self.assertEqual(len(completed), 2)
            self.assertTrue(all("review_result" in event for event in completed))
            events = invoke("resume", "--last")
            completed = [
                event for event in events if event["type"] == "message.completed"
            ]
            self.assertEqual(len(completed), 2)
            self.assertTrue(
                all(event["review_brief_id"] == brief.brief_id for event in completed)
            )
            self.assertNotIn("review_result", completed[0])
            self.assertIn("review_result", completed[1])


class WorkingReleaseTests(TestCase):
    def test_streamed_save_releases_store_without_cyclic_collection(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            enabled = gc.isenabled()
            gc.disable()
            try:
                state = ConversationController.fresh(root, demo_cassette())
                with SQLiteConversationStore(root, state.session_id, root) as store:
                    store.save(state)
                    working = store.load_working()
                    assert isinstance(working, WorkingConversationState)
                    store.save_working(
                        working.model_copy(
                            update={"revision": 1, "context_max_bytes": 4000}
                        )
                    )
                reference = weakref.ref(store)
                del store
                self.assertIsNone(reference())
            finally:
                if enabled:
                    gc.enable()

    def test_steering_context_releases_source_entries_without_cyclic_collection(
        self,
    ) -> None:
        enabled = gc.isenabled()
        gc.disable()
        try:
            original = ConversationEntry(text="original", status="interrupted")
            refinement = ConversationEntry(text="refine", steering_for=0)
            reference = weakref.ref(original)
            turns = context_turns((original, refinement), 1)
            del original, refinement
            self.assertIsNone(reference())
            self.assertEqual(len(turns[0].blocks), 2)
        finally:
            if enabled:
                gc.enable()
