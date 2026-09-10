"""Incremental cold verification, bounded hydration and publication failures."""

import asyncio
import gc
import json
import sqlite3
import weakref
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from test_conversation_working_state import ObservedStore

from mos_eisley.conversation import ConversationController, ConversationEntry
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_review import (
    REVIEW_PROMPT,
    ConversationReviewPacket,
    review_summary,
    run_conversation_review,
)
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    WorkingConversationState,
)
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.demo import demo_inputs
from mos_eisley.run import conversation_sqlite as backend
from mos_eisley.run.conversation_sqlite import DATABASE


def encoded(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


class ColdResumeTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = self.root / "sessions"
        self.cassette = demo_cassette()
        brief, recording = demo_inputs()
        packet = ConversationReviewPacket(brief=brief, cassette=recording)
        result = asyncio.run(run_conversation_review(packet))
        review = ConversationEntry(
            text=REVIEW_PROMPT,
            status="completed",
            answer=review_summary(result),
            review_packet=packet,
            review_result=result,
        )
        older_result = result.model_copy(
            update={
                "verdict": result.verdict.model_copy(
                    update={"rationale": "Earlier review evidence."}
                )
            }
        )
        older_review = review.model_copy(
            update={
                "review_result": older_result,
                "answer": review_summary(older_result),
            }
        )
        state = ConversationController.fresh(self.root, self.cassette)
        self.original = state.model_copy(
            update={
                "entries": (
                    older_review,
                    review,
                    review,
                    ConversationEntry(text=REVIEW_PROMPT, review_packet=packet),
                ),
                "retained_cassette": self.cassette,
            }
        )
        self.store = ObservedStore(self.storage, state.session_id, self.root)
        self.addCleanup(self.store.close)
        self.store.chunks = []
        self.store.save(self.original)
        self.store.close()
        self.store = ObservedStore(
            self.storage, state.session_id, self.root, create=False
        )
        self.addCleanup(self.store.close)
        self.store.chunks = []
        self.store.allow_full_reads = False

    def load(self) -> WorkingConversationState:
        state = self.store.load_working()
        self.assertIsInstance(state, WorkingConversationState)
        assert isinstance(state, WorkingConversationState)
        return state

    def mutate_index(self, change: Callable[[dict[str, Any]], None]) -> None:
        with sqlite3.connect(self.storage / DATABASE) as db:
            record = json.loads(db.execute("SELECT record FROM sessions").fetchone()[0])
            change(record)
            payload = encoded(record)
            db.execute(
                "UPDATE sessions SET record=?, record_sha=?", (payload, digest(payload))
            )

    def mutate_part(
        self, position: int | None, change: Callable[[dict[str, Any]], None]
    ) -> None:
        with sqlite3.connect(self.storage / DATABASE) as db:
            raw = db.execute(
                "SELECT header FROM sessions"
                if position is None
                else "SELECT payload FROM entries WHERE position=?",
                () if position is None else (position,),
            ).fetchone()[0]
            part = json.loads(raw)
            change(part)
            payload = encoded(part)
            record = json.loads(db.execute("SELECT record FROM sessions").fetchone()[0])
            if position is None:
                db.execute("UPDATE sessions SET header=?", (payload,))
                record["resume_checkpoint"]["header_sha256"] = digest(payload)
                record["resume_checkpoint"]["header_bytes"] = len(payload)
            else:
                db.execute(
                    "UPDATE entries SET payload=? WHERE position=?", (payload, position)
                )
                record["entry_sha256"][position] = digest(payload)
                record["resume_checkpoint"]["entries"][position]["bytes"] = len(payload)
            raw_record = encoded(record)
            db.execute(
                "UPDATE sessions SET record=?, record_sha=?",
                (raw_record, digest(raw_record)),
            )

    def test_cold_resume_never_loads_full_state_and_preserves_exact_history(
        self,
    ) -> None:
        queries: list[str] = []
        self.store.trace(queries)
        state = self.load()
        self.assertEqual(self.store.full_reads, 0)
        self.assertEqual(
            self.store.snapshot_sha256, digest(canonical_bytes(self.original))
        )
        self.assertTrue(
            all(isinstance(entry, ArchivedConversationEntry) for entry in state.entries)
        )
        self.assertEqual(
            [entry.review_result is not None for entry in state.entries],
            [False, False, True, False],
        )
        self.assertTrue(self.store.chunks)
        self.assertLessEqual(max(self.store.chunks), 32_768)
        self.assertFalse(
            any("SELECT payload FROM artifacts" in query for query in queries)
        )
        chat = ConversationController(
            state,
            self.cassette,
            self.store.save_working,
            load_entry=self.store.load_working_entry,
        )
        asyncio.run(chat.step())
        self.assertEqual(chat.state.entries[-1].status, "completed")
        self.assertEqual(chat.state.exchanges_consumed, 0)
        self.store.allow_full_reads = True
        full = self.store.load()
        self.assertEqual(full.entries[:3], self.original.entries[:3])
        self.assertEqual(self.store.snapshot_sha256, digest(canonical_bytes(full)))

    def test_each_decoded_entry_is_released_before_validating_the_next(self) -> None:
        references: list[weakref.ReferenceType[ConversationEntry]] = []
        original = ConversationEntry.model_validate_json

        def validate(data: str | bytes | bytearray) -> ConversationEntry:
            self.assertTrue(all(ref() is None for ref in references))
            entry = original(data)
            references.append(weakref.ref(entry))
            return entry

        gc.collect()
        enabled = gc.isenabled()
        gc.disable()
        try:
            with patch.object(
                ConversationEntry, "model_validate_json", side_effect=validate
            ):
                state = self.load()
            self.assertEqual(len(references), 4)
            self.assertTrue(all(ref() is None for ref in references))
            self.assertIsNotNone(state.entries[2].review_result)
        finally:
            if enabled:
                gc.enable()

    def test_historical_entry_budget_rejects_before_any_of_its_artifact_reads(
        self,
    ) -> None:
        # Header still hydrates; the first historical packet must not be fetched.
        queries: list[str] = []
        self.store.trace(queries)
        with (
            patch.object(backend, "MAX_ACTIVE_ENTRY_BYTES", 1),
            self.assertRaisesRegex(ValueError, "cold-resume input needs"),
        ):
            self.load()
        packet = self.original.entries[0].review_packet
        assert packet is not None
        self.assertFalse(
            any(digest(canonical_bytes(packet)) in query for query in queries)
        )
        self.assertIsNone(self.store.snapshot_sha256)
        self.assertFalse(self.store.transaction_open())
        self.assertEqual(self.load().revision, self.original.revision)

    def test_corruption_in_an_older_result_is_not_hidden_by_latest_result_selection(
        self,
    ) -> None:
        # This result appears only in the oldest entry, outside the renderer cache.
        with sqlite3.connect(self.storage / DATABASE) as db:
            part = json.loads(
                db.execute("SELECT payload FROM entries WHERE position=0").fetchone()[0]
            )
            db.execute(
                "UPDATE artifacts SET payload=? WHERE sha=?",
                (b"{}", part["refs"]["review_result"]),
            )
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            self.load()
        self.assertIsNone(self.store.snapshot_sha256)

    def test_typed_entry_validation_runs_even_when_record_hashes_are_updated(
        self,
    ) -> None:
        self.mutate_part(
            0, lambda part: part["body"].update(answer="forged review summary")
        )
        with self.assertRaisesRegex(ValueError, "review result does not match"):
            self.load()

    def test_state_progress_is_validated_across_reference_entries(self) -> None:
        self.mutate_part(None, lambda part: part["body"].update(exchanges_consumed=1))
        with self.assertRaisesRegex(ValueError, "exchange count"):
            self.load()

    def test_header_identity_is_checked_even_with_updated_header_hash(self) -> None:
        self.mutate_part(
            None, lambda part: part["body"].update(workspace=str(self.root / "other"))
        )
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.load()

    def test_checkpoint_kind_cannot_override_verified_entry_kind(self) -> None:
        self.mutate_index(
            lambda record: record["resume_checkpoint"]["entries"][0].update(
                review=False
            )
        )
        with self.assertRaisesRegex(ValueError, "checkpoint integrity"):
            self.load()

    def test_final_snapshot_digest_and_logical_size_are_verified(self) -> None:
        for field, value in (("snapshot_sha256", "0" * 64), ("snapshot_bytes", 1)):
            with self.subTest(field=field):
                with sqlite3.connect(self.storage / DATABASE) as db:
                    original = db.execute(
                        "SELECT record, record_sha FROM sessions"
                    ).fetchone()
                self.mutate_index(
                    lambda record, field=field, value=value: record["summary"].update(
                        {field: value}
                    )
                )
                with self.assertRaisesRegex(ValueError, "state integrity mismatch"):
                    self.load()
                with sqlite3.connect(self.storage / DATABASE) as db:
                    db.execute("UPDATE sessions SET record=?, record_sha=?", original)
        self.assertIsNone(self.store.snapshot_sha256)

    def test_missing_and_unreferenced_artifacts_are_rejected(self) -> None:
        with sqlite3.connect(self.storage / DATABASE) as db:
            db.execute(
                "INSERT INTO artifacts VALUES (?, ?, ?)",
                (self.original.session_id, digest(b"{}"), b"{}"),
            )
        with self.assertRaisesRegex(ValueError, "unreferenced"):
            self.load()
        with sqlite3.connect(self.storage / DATABASE) as db:
            db.execute("DELETE FROM artifacts")
        with self.assertRaisesRegex(ValueError, "missing"):
            self.load()

    def test_interrupted_stream_rolls_back_and_releases_store_without_cyclic_gc(
        self,
    ) -> None:
        self.store.fail_stream = True
        with self.assertRaisesRegex(OSError, "stream interrupted"):
            self.load()
        self.assertFalse(self.store.transaction_open())
        self.assertIsNone(self.store.snapshot_sha256)
        self.store.fail_stream = False
        self.load()
        # A second independently held store tests deterministic lifetime separately.
        self.store.close()
        enabled = gc.isenabled()
        gc.disable()
        try:
            store = ObservedStore(
                self.storage, self.original.session_id, self.root, create=False
            )
            store.chunks = []
            reference = weakref.ref(store)
            store.load_working()
            store.close()
            del store
            self.assertIsNone(reference())
        finally:
            if enabled:
                gc.enable()

    def test_failed_read_transaction_does_not_publish_a_partial_revision(self) -> None:
        transaction = backend.conversation_transaction

        @contextmanager
        def fail_after_read(
            db: sqlite3.Connection, *, write: bool = False
        ) -> Generator[None]:
            with transaction(db, write=write):
                yield
            raise OSError("read completion failed")

        with (
            patch.object(backend, "conversation_transaction", fail_after_read),
            self.assertRaisesRegex(OSError, "read completion failed"),
        ):
            self.load()
        self.assertIsNone(self.store.snapshot_sha256)
        self.assertFalse(self.store.transaction_open())
        self.assertEqual(self.load().revision, self.original.revision)

    def test_failed_reload_discards_checkpoint_before_the_next_save(self) -> None:
        state = self.load()
        chat = ConversationController(state, self.cassette, self.store.save_working)
        self.store.fail_stream = True
        with self.assertRaises(OSError):
            self.load()
        self.store.fail_stream = False
        before = self.store.cold_reads
        chat.resize_context(4000)
        self.assertEqual(self.store.cold_reads, before + 1)
        self.assertEqual(self.store.full_reads, 0)
