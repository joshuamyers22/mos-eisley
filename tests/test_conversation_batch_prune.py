"""Atomic batch retention, bounded verification and interruption recovery."""

import asyncio
import gc
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import weakref
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.cli import main
from mos_eisley.conversation import (
    ConversationController,
    ConversationEntry,
    ConversationState,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run import conversation_batch_prune as batch_module
from mos_eisley.run.conversation_batch_prune import (
    BatchPrunePlan,
    BatchPruneReceipt,
    prune_sessions,
)
from mos_eisley.run.conversation_export import export_conversation
from mos_eisley.run.conversation_prune import PruneStore, prune_session
from mos_eisley.run.conversation_retention import (
    RetentionPlan,
    preview_retention,
    retention_cutoff,
)
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore

CUTOFF = retention_cutoff("2026-08-01T00:00:00Z")


class BatchPruneTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = self.root / "sessions"
        self.ids = (f"{1:032x}", f"{2:032x}")
        self.newest = "f" * 32
        cassette = demo_cassette()
        self.fresh = ConversationController.fresh(self.root, cassette)
        chat = ConversationController(self.fresh, cassette, lambda state: None)
        chat.refresh_memory(None, cassette)
        chat.submit(DEMO_PROMPTS[0])
        asyncio.run(chat.step())
        self.states = tuple(
            chat.state.model_copy(update={"session_id": sid}) for sid in self.ids
        )
        for state in self.states:
            self.seed(state, CUTOFF - 10)
        self.seed(self.fresh.model_copy(update={"session_id": self.newest}), CUTOFF + 1)
        for sid in self.ids:
            preview = export_conversation(self.storage, self.storage, sid, self.root)
            export_conversation(
                self.storage,
                self.storage,
                sid,
                self.root,
                expected_sha256=preview.export_sha256,
                apply=True,
            )
            temporary_path = self.storage / f".{sid}.{'e' * 32}.tmp"
            temporary_path.write_bytes(b"PRIVATE unfinished copy")
            temporary_path.chmod(0o600)

    def seed(self, state: ConversationState, timestamp: int) -> None:
        with SQLiteConversationStore(
            self.storage, state.session_id, Path(state.workspace)
        ) as store:
            store.import_snapshot(state, timestamp, validate_source=lambda: None)

    def prune(
        self,
        expected: str | None = None,
        *,
        apply: bool = False,
        ids: tuple[str, ...] | None = None,
    ) -> BatchPruneReceipt:
        return prune_sessions(
            self.storage,
            self.root,
            self.ids if ids is None else ids,
            before_ns=CUTOFF,
            keep_newest=1,
            expected_sha256=expected,
            apply=apply,
        )

    def files(self) -> dict[str, tuple[bytes, int, int]]:
        return {
            p.name: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino)
            for p in self.storage.iterdir()
        }

    def rows(self) -> dict[str, list[tuple[object, ...]]]:
        with sqlite3.connect(self.storage / DATABASE) as db:
            return {
                table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in ("metadata", "sessions", "entries", "artifacts")
            }

    def cli_args(self) -> list[str]:
        return [
            "session-prune-batch",
            *self.ids,
            "--storage",
            str(self.storage),
            "-C",
            str(self.root),
            "--before",
            "2026-08-01T00:00:00Z",
            "--keep-newest",
            "1",
            "--json",
        ]

    def test_preview_order_stability_atomic_counts_and_preserved_copies(self) -> None:
        before = self.files()
        rows = self.rows()
        preview = self.prune()
        self.assertEqual(preview, self.prune(ids=tuple(reversed(self.ids))))
        self.assertEqual(self.files(), before)
        self.assertEqual(preview.removed_sessions, 0)
        self.assertEqual(tuple(t.session_id for t in preview.plan.sessions), self.ids)
        self.assertEqual(
            preview.batch_prune_sha256, digest(canonical_bytes(preview.plan))
        )
        receipt = self.prune(preview.batch_prune_sha256, apply=True)
        self.assertEqual(receipt.status, "deleted")
        self.assertEqual(receipt.removed_sessions, 2)
        self.assertEqual(receipt.removed_messages, 2)
        self.assertEqual(
            receipt.removed_artifacts, sum(t.artifacts for t in preview.plan.sessions)
        )
        self.assertGreater(receipt.removed_artifact_bytes, 0)
        after = self.rows()
        for table in ("sessions", "entries", "artifacts"):
            self.assertEqual(
                after[table], [row for row in rows[table] if row[0] not in self.ids]
            )
        report = preview_retention(
            self.storage, self.root, before_ns=CUTOFF, keep_newest=1
        )
        self.assertEqual(report.plan.generation, preview.plan.retention.generation + 1)
        self.assertEqual(
            {name: value for name, value in self.files().items() if name != DATABASE},
            {name: value for name, value in before.items() if name != DATABASE},
        )
        self.assertEqual(
            BatchPruneReceipt.model_validate_json(receipt.model_dump_json()), receipt
        )
        with self.assertRaises(ValueError):
            self.prune(preview.batch_prune_sha256, apply=True)

    def test_single_and_metadata_hashes_never_open_writable(self) -> None:
        single = prune_session(
            self.storage, self.root, self.ids[0], before_ns=CUTOFF, keep_newest=1
        )
        metadata = preview_retention(
            self.storage, self.root, before_ns=CUTOFF, keep_newest=1
        )
        before = self.files()
        original = SQLiteConversationStore._open_database  # pyright: ignore[reportPrivateUsage]

        def readonly(
            store: SQLiteConversationStore, *, create: bool, writable: bool
        ) -> None:
            self.assertFalse(writable)
            original(store, create=create, writable=writable)

        with patch.object(SQLiteConversationStore, "_open_database", readonly):
            for expected in (None, "0" * 64, single.prune_sha256, metadata.plan_sha256):
                with self.assertRaises(ValueError):
                    self.prune(expected, apply=True)
        self.assertEqual(self.files(), before)

    def test_any_busy_selected_lock_blocks_and_releases_earlier_locks(self) -> None:
        preview = self.prune()
        before = self.files()
        for store_type in (ConversationStore, SQLiteConversationStore):
            with store_type(self.storage, self.ids[-1], self.root, create=False):
                for apply in (False, True):
                    with self.assertRaises(BlockingIOError):
                        self.prune(preview.batch_prune_sha256, apply=apply)
                with ConversationStore(
                    self.storage, self.ids[0], self.root, create=False
                ):
                    pass
        self.assertEqual(self.files(), before)
        self.assertEqual(self.prune(), preview)

    def test_absent_foreign_and_protected_selection_fail_before_body_reads(
        self,
    ) -> None:
        queued = self.fresh.model_copy(
            update={
                "session_id": f"{4:032x}",
                "entries": (ConversationEntry(text="PRIVATE queued work"),),
            }
        )
        self.seed(queued, CUTOFF - 1)
        other = self.root / "other"
        other.mkdir()
        foreign = self.fresh.model_copy(
            update={"session_id": f"{5:032x}", "workspace": str(other.resolve())}
        )
        self.seed(foreign, CUTOFF - 1)
        before = self.files()
        with patch.object(
            SQLiteConversationStore, "_load", side_effect=AssertionError("body read")
        ):
            for sid in (
                self.newest,
                queued.session_id,
                foreign.session_id,
                f"{6:032x}",
            ):
                with self.assertRaises((ValueError, OSError)):
                    self.prune(ids=(self.ids[0], sid))
        self.assertEqual(self.files(), before)

    def test_corrupt_last_session_prevents_any_deletion_and_content_echo(self) -> None:
        with sqlite3.connect(self.storage / DATABASE) as db:
            db.execute(
                "UPDATE artifacts SET payload=? WHERE sid=?",
                (b"PRIVATE corrupt bytes", self.ids[-1]),
            )
        before = self.files()
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            result = main(self.cli_args())
        self.assertEqual(result, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("PRIVATE", errors.getvalue())
        self.assertEqual(self.files(), before)

    def test_foreign_generation_and_unselected_activity_invalidate_consent(
        self,
    ) -> None:
        preview = self.prune()
        before = self.rows()
        with (
            ConversationStore(self.storage, self.newest, self.root, create=False),
            self.assertRaises(ValueError),
        ):
            self.prune(preview.batch_prune_sha256, apply=True)
        self.assertEqual(self.rows(), before)
        other = self.root / "other"
        other.mkdir()
        self.seed(
            self.fresh.model_copy(
                update={"session_id": f"{4:032x}", "workspace": str(other.resolve())}
            ),
            CUTOFF - 1,
        )
        before = self.rows()
        with self.assertRaises(ValueError):
            self.prune(preview.batch_prune_sha256, apply=True)
        self.assertEqual(self.rows(), before)

    def test_change_after_preflight_rejected_in_write_transaction(self) -> None:
        preview = self.prune()
        original = batch_module._apply_batch  # pyright: ignore[reportPrivateUsage]

        def changed(stores: tuple[PruneStore, ...], plan: BatchPrunePlan) -> None:
            with sqlite3.connect(self.storage / DATABASE) as db:
                db.execute("UPDATE metadata SET generation=generation+1 WHERE id=1")
            original(stores, plan)

        with (
            patch.object(batch_module, "_apply_batch", changed),
            self.assertRaises(ValueError),
        ):
            self.prune(preview.batch_prune_sha256, apply=True)
        self.assertEqual(len(self.rows()["sessions"]), 3)

    def test_last_selected_corruption_after_preflight_rolls_back_whole_batch(
        self,
    ) -> None:
        preview = self.prune()
        original = batch_module._apply_batch  # pyright: ignore[reportPrivateUsage]

        def changed(stores: tuple[PruneStore, ...], plan: BatchPrunePlan) -> None:
            with sqlite3.connect(self.storage / DATABASE) as db:
                db.execute(
                    "UPDATE artifacts SET payload=? WHERE sid=?",
                    (b"PRIVATE corrupt bytes", self.ids[-1]),
                )
            original(stores, plan)

        with (
            patch.object(batch_module, "_apply_batch", changed),
            self.assertRaises(ValueError),
        ):
            self.prune(preview.batch_prune_sha256, apply=True)
        self.assertEqual(len(self.rows()["sessions"]), 3)
        with SQLiteConversationStore(
            self.storage, self.ids[0], self.root, create=False, writable=False
        ) as store:
            self.assertEqual(store.inspect_snapshot()[0].state, self.states[0])

    def test_late_lock_or_database_replacement_rejected(self) -> None:
        original = batch_module._apply_batch  # pyright: ignore[reportPrivateUsage]
        for name in (f"{self.ids[-1]}.lock", DATABASE):
            preview = self.prune()

            def changed(
                stores: tuple[PruneStore, ...], plan: BatchPrunePlan, name: str = name
            ) -> None:
                path = self.storage / name
                replacement = self.storage / "replacement"
                shutil.copyfile(path, replacement)
                replacement.chmod(0o600)
                os.replace(replacement, path)
                original(stores, plan)

            with (
                patch.object(batch_module, "_apply_batch", changed),
                self.assertRaises(ValueError),
            ):
                self.prune(preview.batch_prune_sha256, apply=True)
            self.assertEqual(len(self.rows()["sessions"]), 3)

    def test_exception_after_first_delete_rolls_back_all_rows_and_generation(
        self,
    ) -> None:
        preview = self.prune()
        before = self.rows()

        def partial(db: sqlite3.Connection, plan: BatchPrunePlan) -> None:
            db.execute(
                "DELETE FROM sessions WHERE sid=?", (plan.sessions[0].session_id,)
            )
            raise OSError("injected write failure")

        with (
            patch.object(batch_module, "_delete_batch", partial),
            self.assertRaises(OSError),
        ):
            self.prune(preview.batch_prune_sha256, apply=True)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.prune(), preview)

    def test_all_selected_locks_held_and_write_transaction_blocks_external_commit(
        self,
    ) -> None:
        preview = self.prune()
        original = SQLiteConversationStore._load  # pyright: ignore[reportPrivateUsage]
        blocked = 0

        def verified(
            store: SQLiteConversationStore, db: sqlite3.Connection
        ) -> ConversationSnapshot:
            nonlocal blocked
            for sid in self.ids:
                with (
                    self.assertRaises(BlockingIOError),
                    ConversationStore(self.storage, sid, self.root, create=False),
                ):
                    pass
            with sqlite3.connect(self.storage / DATABASE, timeout=0) as other:
                try:
                    other.execute("BEGIN IMMEDIATE")
                except sqlite3.OperationalError:
                    blocked += 1
                else:
                    other.rollback()
            return original(store, db)

        with patch.object(SQLiteConversationStore, "_load", verified):
            self.prune(preview.batch_prune_sha256, apply=True)
        self.assertEqual(blocked, len(self.ids))

    def test_full_states_released_between_selections_and_metadata_read_once(
        self,
    ) -> None:
        references: list[weakref.ReferenceType[ConversationSnapshot]] = []
        original = SQLiteConversationStore._load  # pyright: ignore[reportPrivateUsage]

        def verified(
            store: SQLiteConversationStore, db: sqlite3.Connection
        ) -> ConversationSnapshot:
            gc.collect()
            self.assertTrue(all(ref() is None for ref in references))
            snapshot = original(store, db)
            references.append(weakref.ref(snapshot))
            return snapshot

        with (
            patch.object(SQLiteConversationStore, "_load", verified),
            patch.object(
                batch_module,
                "read_retention_plan",
                wraps=batch_module.read_retention_plan,
            ) as metadata,
        ):
            self.prune()
        self.assertEqual(metadata.call_count, 1)
        self.assertEqual(len(references), 2)
        self.assertTrue(all(ref() is None for ref in references))

    def test_aggregate_byte_limit_is_checked_before_any_full_state_read(self) -> None:
        sid = f"{3:032x}"
        self.seed(self.fresh.model_copy(update={"session_id": sid}), CUTOFF - 1)
        original = batch_module.read_retention_plan

        def oversized(*args: object, **kwargs: object) -> RetentionPlan:
            plan = original(*args, **kwargs)  # pyright: ignore[reportArgumentType]
            entries = tuple(
                entry.model_copy(
                    update={
                        "summary": entry.summary.model_copy(
                            update={
                                "snapshot_bytes": 32 * 1024 * 1024,
                                "snapshot_max_bytes": 32 * 1024 * 1024,
                            }
                        )
                    }
                )
                if entry.disposition == "candidate"
                else entry
                for entry in plan.sessions
            )
            return plan.model_copy(update={"sessions": entries})

        before = self.files()
        with (
            patch.object(batch_module, "read_retention_plan", oversized),
            patch.object(
                SQLiteConversationStore,
                "_load",
                side_effect=AssertionError("body read"),
            ),
            self.assertRaisesRegex(ValueError, "64 MB"),
        ):
            self.prune(ids=(*self.ids, sid))
        self.assertEqual(self.files(), before)

    def test_maximum_batch_and_invalid_inputs(self) -> None:
        before = self.files()
        for ids in (
            (),
            (self.ids[0], self.ids[0]),
            ("PRIVATE",),
            tuple(f"{n:032x}" for n in range(33)),
        ):
            with self.assertRaises(ValueError):
                self.prune(ids=ids)
        for mode in (0, 1, "yes"):
            with self.assertRaises(ValueError):
                self.prune(apply=mode)  # pyright: ignore[reportArgumentType]
        self.assertEqual(self.files(), before)
        for n in range(3, 33):
            self.seed(
                self.fresh.model_copy(update={"session_id": f"{n:032x}"}), CUTOFF - 1
            )
        ids = tuple(f"{n:032x}" for n in range(1, 33))
        preview = self.prune(ids=ids)
        receipt = self.prune(preview.batch_prune_sha256, apply=True, ids=ids)
        self.assertEqual(receipt.removed_sessions, 32)
        self.assertEqual(len(self.rows()["sessions"]), 1)

    def crash(self, expected: str, boundary: str) -> subprocess.CompletedProcess[str]:
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.run import conversation_batch_prune as batch
original = batch._apply_batch
def before(db, plan):
    db.execute("PRAGMA cache_size=1")
    db.execute("DELETE FROM sessions WHERE sid=?", (plan.sessions[0].session_id,))
    os._exit(77)
def after(stores, plan):
    original(stores, plan)
    os._exit(77)
method, replacement = (
    ("_delete_batch", before) if sys.argv[5] == "before" else ("_apply_batch", after)
)
with patch.object(batch, method, replacement):
    batch.prune_sessions(Path(sys.argv[1]), Path(sys.argv[2]), tuple(sys.argv[6:]),
                         before_ns=int(sys.argv[3]), keep_newest=1,
                         expected_sha256=sys.argv[4], apply=True)
"""
        return subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(self.storage),
                str(self.root),
                str(CUTOFF),
                expected,
                boundary,
                *self.ids,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_crash_after_first_delete_recovers_entire_batch(self) -> None:
        preview = self.prune()
        before = self.rows()
        result = self.crash(preview.batch_prune_sha256, "before")
        self.assertEqual(result.returncode, 77, result.stderr)
        files = self.files()
        self.assertIn(DATABASE + "-journal", files)
        for apply in (False, True):
            with self.assertRaises(ValueError):
                self.prune(preview.batch_prune_sha256, apply=apply)
        self.assertEqual(self.files(), files)
        with SQLiteConversationStore(
            self.storage, self.ids[0], self.root, create=False
        ) as store:
            self.assertEqual(store.inspect_snapshot()[0].state, self.states[0])
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.prune(), preview)

    def test_crash_after_commit_has_no_partial_or_false_retry_receipt(self) -> None:
        preview = self.prune()
        result = self.crash(preview.batch_prune_sha256, "after")
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertEqual(len(self.rows()["sessions"]), 1)
        with self.assertRaises(ValueError):
            self.prune(preview.batch_prune_sha256, apply=True)
        for sid in self.ids:
            self.assertTrue((self.storage / f"{sid}.json").exists())
            self.assertTrue((self.storage / f"{sid}.lock").exists())

    def test_contracts_reject_duplicate_protected_mismatched_and_false_receipts(
        self,
    ) -> None:
        preview = self.prune()
        for field, value in (
            ("sessions", (preview.plan.sessions[0],) * 2),
            ("sessions", tuple(reversed(preview.plan.sessions))),
            ("verification", "index_metadata"),
        ):
            with self.assertRaises(ValueError):
                BatchPrunePlan.model_validate(
                    preview.plan.model_dump() | {field: value}
                )
        for change in (
            {"session_id": self.newest},
            {"snapshot_sha256": "0" * 64},
            {"artifact_bytes": 0},
        ):
            payload = preview.plan.model_dump(mode="json")
            payload["sessions"][0].update(change)
            with self.assertRaises(ValueError):
                BatchPrunePlan.model_validate_json(json.dumps(payload))
        for field in (
            "removed_sessions",
            "removed_messages",
            "removed_artifacts",
            "removed_artifact_bytes",
            "removed_snapshot_bytes",
        ):
            payload = preview.model_dump(mode="json") | {field: 1}
            with self.assertRaises(ValueError):
                BatchPruneReceipt.model_validate_json(json.dumps(payload))

    def test_cli_preview_apply_and_missing_id_retry(self) -> None:
        args = [sys.executable, "-m", "mos_eisley.cli", *self.cli_args()]
        preview = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        payload = json.loads(preview.stdout)
        self.assertEqual(payload["type"], "conversation.batch_prune")
        apply_args = [
            *args,
            "--apply",
            "--expected-sha256",
            payload["batch_prune_sha256"],
        ]
        result = subprocess.run(apply_args, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["removed_sessions"], 2)
        retry = subprocess.run(apply_args, capture_output=True, text=True, timeout=30)
        self.assertEqual(retry.returncode, 2)
        self.assertEqual(retry.stdout, "")
