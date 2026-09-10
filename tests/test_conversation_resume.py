"""Bounded resume checkpoints, selected working sets and inert CLI inspection."""

import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.cli import main
from mos_eisley.conversation import (
    ConversationController,
    ConversationEntry,
    ConversationMemoryContext,
)
from mos_eisley.conversation_cli import demo_cassette
from mos_eisley.conversation_memory import MemoryStore
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.providers.agent_recorded import AgentCassette
from mos_eisley.run import conversation_sqlite as backend
from mos_eisley.run.conversation_artifacts import read_sqlite_artifact
from mos_eisley.run.conversation_resume import inspect_sqlite_resume
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore


class ResumeInspectionTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cassette = AgentCassette(exchanges=demo_cassette().exchanges * 4)
        self.state = ConversationController.fresh(self.root, self.cassette).model_copy(
            update={
                "entries": tuple(
                    ConversationEntry(text=f"saved {i}", status="cancelled")
                    for i in range(8)
                ),
                "retained_cassette": self.cassette,
            }
        )
        self.sid = self.state.session_id
        with SQLiteConversationStore(self.root, self.sid, self.root) as store:
            store.save(self.state)

    def rewrite_index(self, change: Callable[[dict[str, Any]], None]) -> None:
        with sqlite3.connect(self.root / DATABASE) as db:
            index = json.loads(
                db.execute(
                    "SELECT record FROM sessions WHERE sid=?", (self.sid,)
                ).fetchone()[0]
            )
            change(index)
            encoded = json.dumps(
                index, ensure_ascii=False, separators=(",", ":")
            ).encode()
            db.execute(
                "UPDATE sessions SET record=?, record_sha=? WHERE sid=?",
                (encoded, digest(encoded), self.sid),
            )

    def test_reads_only_recent_records_and_no_artifact_payloads(self) -> None:
        before = (self.root / DATABASE).read_bytes()
        queries: list[str] = []
        original = sqlite3.connect

        def traced(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            db = original(*args, **kwargs)
            db.set_trace_callback(queries.append)
            return db

        with (
            SQLiteConversationStore(self.root, self.sid, self.root, create=False),
            patch.object(backend.sqlite3, "connect", traced),
        ):
            inspection = inspect_sqlite_resume(self.root, self.sid, self.root)
        self.assertEqual([entry.position for entry in inspection.entries], [4, 5, 6, 7])
        self.assertEqual(inspection.omitted_messages, 4)
        self.assertEqual(inspection.header.exchanges_consumed, 0)
        self.assertEqual(inspection.header_artifacts[0].field, "retained_cassette")
        reads = [query for query in queries if "FROM entries" in query]
        self.assertEqual(len(reads), 4)
        self.assertTrue(
            all(f"position={i + 4}" in query for i, query in enumerate(reads))
        )
        artifacts = [query for query in queries if "FROM artifacts" in query]
        self.assertTrue(artifacts)
        self.assertTrue(
            all(query.startswith("SELECT length(payload)") for query in artifacts)
        )
        self.assertLessEqual(inspection.record_bytes, 512_000)
        self.assertEqual((self.root / DATABASE).read_bytes(), before)

    def test_unfinished_work_and_complete_steering_ancestry_are_included(self) -> None:
        entries = list(self.state.entries)
        entries[1] = entries[1].model_copy(update={"steering_for": 0})
        entries[3] = entries[3].model_copy(update={"status": "queued"})
        entries[5] = entries[5].model_copy(update={"steering_for": 1})
        entries[6] = entries[6].model_copy(
            update={"status": "running", "steering_for": 5}
        )
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            state = store.load().model_copy(
                update={
                    "revision": 1,
                    "entries": tuple(entries),
                    "exchanges_consumed": 4,
                }
            )
            store.save(state)
        before = (self.root / DATABASE).read_bytes()
        inspection = inspect_sqlite_resume(self.root, self.sid, self.root)
        self.assertEqual(
            [entry.position for entry in inspection.entries], [0, 1, 3, 4, 5, 6, 7]
        )
        self.assertEqual(inspection.pending_positions, (3,))
        self.assertEqual(inspection.interrupted_on_resume, (6,))
        self.assertEqual(inspection.header.exchanges_consumed, 4)
        self.assertEqual((self.root / DATABASE).read_bytes(), before)
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            controller = ConversationController(store.load(), self.cassette, store.save)
            self.assertEqual(controller.state.entries[6].status, "interrupted")
            self.assertEqual(controller.state.entries[3].status, "queued")
            self.assertEqual(controller.state.exchanges_consumed, 4)
            self.assertEqual(store.load(), controller.state)

    def test_memory_stays_unexpanded_and_selected_references_can_be_opened(
        self,
    ) -> None:
        memory_store = MemoryStore(self.root / "memory", self.root)
        memory_store.change("user", "set", text="RESUME-PRIVATE-CANARY")
        memory = memory_store.load()
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            state = store.load()
            entries = list(state.entries)
            entries[7] = entries[7].model_copy(
                update={"memory_context": ConversationMemoryContext(memory=memory)}
            )
            store.save(
                state.model_copy(
                    update={"revision": 1, "entries": tuple(entries), "memory": memory}
                )
            )
        inspection = inspect_sqlite_resume(self.root, self.sid, self.root)
        self.assertNotIn("RESUME-PRIVATE-CANARY", inspection.model_dump_json())
        self.assertEqual(
            [ref.field for ref in inspection.header_artifacts],
            ["memory", "retained_cassette"],
        )
        selection = inspection.entries[-1].artifacts[0].selection
        assert selection is not None
        expanded = read_sqlite_artifact(self.root, self.root, selection)
        self.assertIn("RESUME-PRIVATE-CANARY", expanded.model_dump_json())

    def test_header_and_selected_corruption_fail_but_omitted_records_are_not_read(
        self,
    ) -> None:
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute(
                "UPDATE entries SET payload=? WHERE sid=? AND position=0",
                (b"{}", self.sid),
            )
        self.assertEqual(
            inspect_sqlite_resume(self.root, self.sid, self.root).omitted_messages, 4
        )
        with (
            SQLiteConversationStore(
                self.root, self.sid, self.root, create=False
            ) as store,
            self.assertRaises(ValueError),
        ):
            store.load()
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute("DELETE FROM entries WHERE sid=? AND position=7", (self.sid,))
        with self.assertRaisesRegex(ValueError, "message missing"):
            inspect_sqlite_resume(self.root, self.sid, self.root)
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute("UPDATE sessions SET header=? WHERE sid=?", (b"{}", self.sid))
        with self.assertRaisesRegex(ValueError, "header integrity"):
            inspect_sqlite_resume(self.root, self.sid, self.root)

    def test_checkpoint_mismatch_is_rejected_by_inspection_and_full_resume(
        self,
    ) -> None:
        def change(index: dict[str, Any]) -> None:
            index["resume_checkpoint"]["entries"][7]["review"] = True

        self.rewrite_index(change)
        # Keep aggregate progress plausible so the selected-row comparison must run.
        with self.assertRaisesRegex(ValueError, "disagrees with checkpoint"):
            inspect_sqlite_resume(self.root, self.sid, self.root)
        with (
            SQLiteConversationStore(
                self.root, self.sid, self.root, create=False
            ) as store,
            self.assertRaisesRegex(ValueError, "checkpoint integrity"),
        ):
            store.load()

    def test_byte_budget_rejects_before_any_message_payload_is_fetched(self) -> None:
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            state = store.load()
            store.save(
                state.model_copy(
                    update={
                        "revision": 1,
                        "entries": tuple(
                            ConversationEntry(text="😀" * 8000) for _ in range(16)
                        ),
                    }
                )
            )
        queries: list[str] = []
        original = sqlite3.connect

        def traced(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            db = original(*args, **kwargs)
            db.set_trace_callback(queries.append)
            return db

        with (
            patch.object(backend.sqlite3, "connect", traced),
            self.assertRaisesRegex(ValueError, "inspection needs"),
        ):
            inspect_sqlite_resume(self.root, self.sid, self.root)
        self.assertFalse(any("FROM entries" in query for query in queries))
        self.assertFalse(any("FROM artifacts" in query for query in queries))

    def test_legacy_checkpoint_preparation_preserves_exact_raw_rows_and_state(
        self,
    ) -> None:
        self.rewrite_index(lambda index: index.pop("resume_checkpoint"))
        with sqlite3.connect(self.root / DATABASE) as db:
            header = db.execute(
                "SELECT header FROM sessions WHERE sid=?", (self.sid,)
            ).fetchone()[0]
            db.execute(
                "UPDATE sessions SET header=? WHERE sid=?",
                (b"\n " + header + b"\n", self.sid),
            )
        before = (self.root / DATABASE).read_bytes()
        with self.assertRaisesRegex(ValueError, "checkpoint is unavailable"):
            inspect_sqlite_resume(self.root, self.sid, self.root)
        self.assertEqual((self.root / DATABASE).read_bytes(), before)
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            self.assertEqual(store.load(), self.state)
            with self.assertRaisesRegex(ValueError, "changed"):
                store.prepare_transcript("0" * 64)
            summary = store.prepare_transcript(digest(canonical_bytes(self.state)))
            prepared = (self.root / DATABASE).read_bytes()
            store.prepare_transcript(summary.snapshot_sha256)
            self.assertEqual((self.root / DATABASE).read_bytes(), prepared)
            self.assertEqual(store.load(), self.state)
        inspection = inspect_sqlite_resume(self.root, self.sid, self.root)
        self.assertEqual(
            inspection.snapshot_sha256, digest(canonical_bytes(self.state))
        )
        with sqlite3.connect(self.root / DATABASE) as db:
            self.assertEqual(
                db.execute(
                    "SELECT header FROM sessions WHERE sid=?", (self.sid,)
                ).fetchone()[0],
                b"\n " + header + b"\n",
            )

    def test_checkpoint_preparation_rollback_and_normal_save_upgrade(self) -> None:
        self.rewrite_index(lambda index: index.pop("resume_checkpoint"))
        original = backend.conversation_transaction

        @contextmanager
        def fail(db: sqlite3.Connection, *, write: bool = False) -> Generator[None]:
            with original(db, write=write):
                yield
                if write:
                    raise OSError("injected checkpoint commit failure")

        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            with (
                patch.object(backend, "conversation_transaction", fail),
                self.assertRaises(OSError),
            ):
                store.prepare_transcript(digest(canonical_bytes(self.state)))
            with self.assertRaisesRegex(ValueError, "checkpoint is unavailable"):
                inspect_sqlite_resume(self.root, self.sid, self.root)
            state = store.load()
            store.save(state.model_copy(update={"revision": 1}))
        self.assertEqual(
            inspect_sqlite_resume(self.root, self.sid, self.root).header.revision, 1
        )

    def test_identity_expected_hash_and_storage_permissions(self) -> None:
        for workspace, expected in ((self.root / "other", None), (self.root, "0" * 64)):
            with self.assertRaises(ValueError):
                inspect_sqlite_resume(
                    self.root, self.sid, workspace, expected_sha256=expected
                )
        with self.assertRaises(FileNotFoundError):
            inspect_sqlite_resume(self.root / "missing", self.sid, self.root)
        self.assertFalse((self.root / "missing").exists())
        self.rewrite_index(lambda index: index.update(owner_uid=os.getuid() + 1))
        with self.assertRaisesRegex(ValueError, "identity"):
            inspect_sqlite_resume(self.root, self.sid, self.root)
        (self.root / DATABASE).chmod(0o644)
        with self.assertRaisesRegex(ValueError, "private"):
            inspect_sqlite_resume(self.root, self.sid, self.root)

    def test_invalid_checkpoint_counts_progress_and_steering_are_rejected(self) -> None:
        for field, value, expected in (
            ("status", "queued", "counts"),
            ("status", "failed", "progress"),
            ("steering_for", 7, "steering"),
        ):
            with self.subTest(field=field, value=value):

                def change(
                    index: dict[str, Any], field: str = field, value: str | int = value
                ) -> None:
                    detail = index["resume_checkpoint"]["entries"][7]
                    detail.update(status="cancelled", steering_for=None)
                    detail[field] = value

                self.rewrite_index(change)
                with self.assertRaisesRegex(ValueError, expected):
                    inspect_sqlite_resume(self.root, self.sid, self.root)

    def test_header_artifact_content_is_unread_but_missing_reference_fails(
        self,
    ) -> None:
        inspection = inspect_sqlite_resume(self.root, self.sid, self.root)
        ref = inspection.header_artifacts[0]
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute(
                "UPDATE artifacts SET payload=? WHERE sid=? AND sha=?",
                (b"x" * ref.bytes, self.sid, ref.sha256),
            )
        self.assertEqual(
            inspect_sqlite_resume(self.root, self.sid, self.root), inspection
        )
        with (
            SQLiteConversationStore(
                self.root, self.sid, self.root, create=False
            ) as store,
            self.assertRaisesRegex(ValueError, "artifact integrity"),
        ):
            store.load()
        with sqlite3.connect(self.root / DATABASE) as db:
            db.execute("DELETE FROM artifacts WHERE sid=?", (self.sid,))
        with self.assertRaisesRegex(ValueError, "missing resume header artifact"):
            inspect_sqlite_resume(self.root, self.sid, self.root)

    def test_empty_session_is_inspectable_and_old_selection_is_rejected(self) -> None:
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            state = store.load()
            selected = digest(canonical_bytes(state))
            store.save(state.model_copy(update={"revision": 1, "entries": ()}))
        inspection = inspect_sqlite_resume(self.root, self.sid, self.root)
        self.assertEqual(inspection.entries, ())
        self.assertEqual(inspection.pending_positions, ())
        self.assertEqual(inspection.interrupted_on_resume, ())
        with self.assertRaisesRegex(ValueError, "changed"):
            inspect_sqlite_resume(
                self.root, self.sid, self.root, expected_sha256=selected
            )

    def test_cli_inspection_is_read_only_and_never_constructs_a_controller(
        self,
    ) -> None:
        command = [
            "resume",
            self.sid,
            "--inspect",
            "--storage-backend",
            "sqlite",
            "--storage",
            str(self.root),
            "-C",
            str(self.root),
            "--json",
        ]
        before = (self.root / DATABASE).read_bytes()
        with (
            patch(
                "mos_eisley.conversation_cli.ConversationController",
                side_effect=AssertionError("controller constructed"),
            ),
            patch("builtins.print") as output,
        ):
            self.assertEqual(main(command), 0)
        event = json.loads(output.call_args.args[0])
        self.assertEqual(event["type"], "conversation.resume_inspected")
        self.assertEqual(event["omitted_messages"], 4)
        self.assertEqual((self.root / DATABASE).read_bytes(), before)
        result = subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *command],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["session_id"], self.sid)

    def test_cli_latest_and_conflicting_options(self) -> None:
        command = [
            "resume",
            "--last",
            "--inspect",
            "--storage-backend",
            "sqlite",
            "--storage",
            str(self.root),
            "-C",
            str(self.root),
        ]
        with patch("builtins.print") as output:
            self.assertEqual(main(command), 0)
        self.assertEqual(json.loads(output.call_args.args[0])["session_id"], self.sid)
        for extra in (
            ["--refresh-memory"],
            ["--session-max-bytes", "8000000"],
            ["--tui"],
            ["--no-memory"],
            ["--cassette", "missing"],
            ["--storage-backend", "snapshot"],
        ):
            with self.subTest(extra=extra), patch("builtins.print"):
                self.assertEqual(main([*command, *extra]), 2)
