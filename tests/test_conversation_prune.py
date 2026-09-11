"""Full-state pruning consent, policy races and atomic SQLite recovery."""

import asyncio
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.cli import main
from mos_eisley.conversation import (
    ConversationController,
    ConversationEntry,
    ConversationState,
    Status,
)
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.demo import demo_inputs
from mos_eisley.run import conversation_prune as prune_module
from mos_eisley.run.conversation_prune import PrunePlan, PruneReceipt, prune_session
from mos_eisley.run.conversation_retention import preview_retention, retention_cutoff
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore

CUTOFF = retention_cutoff("2026-08-01T00:00:00Z")


class PruneTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = self.root / "sessions"
        self.sid = f"{1:032x}"
        self.cassette = demo_cassette()
        self.fresh = ConversationController.fresh(self.root, self.cassette)
        chat = ConversationController(self.fresh, self.cassette, lambda state: None)
        chat.refresh_memory(None, self.cassette)
        chat.submit(DEMO_PROMPTS[0])
        asyncio.run(chat.step())
        self.state = chat.state.model_copy(update={"session_id": self.sid})
        self.seed(self.state, CUTOFF - 100)
        self.seed(self.fresh.model_copy(update={"session_id": f"{2:032x}"}), CUTOFF + 1)
        self.seed(
            self.fresh.model_copy(update={"session_id": f"{3:032x}"}), CUTOFF - 50
        )
        for name, payload in (
            (
                f"{self.sid}.json",
                canonical_bytes(
                    ConversationSnapshot(
                        state=self.state, sha256=digest(canonical_bytes(self.state))
                    )
                ),
            ),
            (f".{self.sid}.{'f' * 32}.tmp", b"PRIVATE unfinished JSON export"),
            ("backup.json", b"PRIVATE backup"),
        ):
            path = self.storage / name
            path.write_bytes(payload)
            path.chmod(0o600)

    def seed(self, state: ConversationState, timestamp: int) -> None:
        with SQLiteConversationStore(
            self.storage, state.session_id, Path(state.workspace)
        ) as store:
            store.import_snapshot(state, timestamp, validate_source=lambda: None)

    def prune(
        self, expected: str | None = None, *, apply: bool = False, keep: int = 1
    ) -> PruneReceipt:
        return prune_session(
            self.storage,
            self.root,
            self.sid,
            before_ns=CUTOFF,
            keep_newest=keep,
            expected_sha256=expected,
            apply=apply,
        )

    def files(self) -> dict[str, tuple[bytes, int, int]]:
        return {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino)
            for path in self.storage.iterdir()
            if path.is_file()
        }

    def rows(self) -> dict[str, list[tuple[object, ...]]]:
        with sqlite3.connect(self.storage / DATABASE) as db:
            return {
                table: db.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
                for table in ("metadata", "sessions", "entries", "artifacts")
            }

    def assert_saved(self) -> None:
        with SQLiteConversationStore(
            self.storage, self.sid, self.root, create=False, writable=False
        ) as store:
            self.assertEqual(store.inspect_snapshot()[0].state, self.state)

    def cli_args(self) -> list[str]:
        return [
            "session-prune",
            self.sid,
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

    def test_preview_apply_exact_cascades_and_other_copies_remain(self) -> None:
        before = self.files()
        rows = self.rows()
        preview = self.prune()
        self.assertEqual(preview, self.prune())
        self.assertEqual(self.files(), before)
        self.assertEqual(preview.status, "planned")
        self.assertEqual(preview.removed_sessions, 0)
        self.assertEqual(preview.plan.verification, "selected_full_state")
        self.assertGreater(preview.plan.artifacts, 0)
        self.assertGreater(preview.plan.artifact_bytes, 0)
        self.assertEqual(preview.prune_sha256, digest(canonical_bytes(preview.plan)))
        self.assertFalse(preview.plan.selection.active)
        result = self.prune(preview.prune_sha256, apply=True)
        self.assertEqual(result.status, "deleted")
        self.assertEqual(result.removed_sessions, 1)
        self.assertEqual(result.removed_messages, len(self.state.entries))
        self.assertEqual(result.removed_artifacts, preview.plan.artifacts)
        self.assertEqual(result.removed_artifact_bytes, preview.plan.artifact_bytes)
        self.assertEqual(
            result.removed_snapshot_bytes, preview.plan.selection.snapshot_bytes
        )
        after = self.rows()
        for table in ("sessions", "entries", "artifacts"):
            self.assertEqual(
                after[table], [row for row in rows[table] if row[0] != self.sid]
            )
        generation = rows["metadata"][0][-1]
        assert isinstance(generation, int)
        self.assertEqual(after["metadata"][0][-1], generation + 1)
        current = self.files()
        for name, saved in before.items():
            if name != DATABASE:
                self.assertEqual(current[name], saved)
        self.assertNotIn(DATABASE + "-journal", current)
        self.assertEqual(
            result, PruneReceipt.model_validate_json(result.model_dump_json())
        )
        with self.assertRaises(ValueError):
            self.prune(preview.prune_sha256, apply=True)

    def test_metadata_hash_and_missing_or_wrong_consent_never_open_writable(
        self,
    ) -> None:
        preview = self.prune()
        metadata = preview_retention(
            self.storage, self.root, before_ns=CUTOFF, keep_newest=1
        )
        before = self.files()
        original = SQLiteConversationStore._open_database  # pyright: ignore[reportPrivateUsage]
        writes: list[bool] = []

        def observed(
            store: SQLiteConversationStore, *, create: bool, writable: bool
        ) -> None:
            writes.append(writable)
            original(store, create=create, writable=writable)

        with patch.object(SQLiteConversationStore, "_open_database", observed):
            for expected in (
                None,
                "PRIVATE-invalid",
                "0" * 64,
                metadata.plan_sha256,
                preview.plan.snapshot_sha256,
            ):
                with self.assertRaises(ValueError):
                    self.prune(expected, apply=True)
            self.prune()
        self.assertTrue(writes)
        self.assertFalse(any(writes))
        self.assertEqual(self.files(), before)

    def test_active_selected_session_is_never_treated_as_our_own_lock(self) -> None:
        preview = self.prune()
        for backend in (ConversationStore, SQLiteConversationStore):
            with backend(self.storage, self.sid, self.root, create=False):
                for apply in (False, True):
                    with self.assertRaises(BlockingIOError):
                        self.prune(preview.prune_sha256, apply=apply)
        self.assert_saved()

    def test_protected_and_noncompleted_sessions_fail_before_body_reads(self) -> None:
        with patch.object(
            SQLiteConversationStore,
            "_load",
            side_effect=AssertionError("loaded protected state"),
        ):
            with self.assertRaisesRegex(ValueError, "protected"):
                self.prune(keep=1000)
            with self.assertRaisesRegex(ValueError, "protected"):
                prune_session(
                    self.storage,
                    self.root,
                    f"{2:032x}",
                    before_ns=CUTOFF,
                    keep_newest=0,
                )
        statuses: tuple[Status, ...] = (
            "queued",
            "running",
            "failed",
            "interrupted",
            "cancelled",
        )
        for index, status in enumerate(statuses, 4):
            state = self.fresh.model_copy(
                update={
                    "session_id": f"{index:032x}",
                    "entries": (
                        ConversationEntry(
                            text="PRIVATE unfinished work", status=status
                        ),
                    ),
                    "exchanges_consumed": 0 if status in {"queued", "cancelled"} else 1,
                }
            )
            self.seed(state, CUTOFF - index)
            with (
                patch.object(
                    SQLiteConversationStore,
                    "_load",
                    side_effect=AssertionError("loaded protected state"),
                ),
                self.assertRaisesRegex(ValueError, "protected"),
            ):
                prune_session(
                    self.storage,
                    self.root,
                    state.session_id,
                    before_ns=CUTOFF,
                    keep_newest=1,
                )

    def test_corrupt_retained_content_cannot_be_pruned_from_valid_index(self) -> None:
        for table, column in (
            ("sessions", "header"),
            ("entries", "payload"),
            ("artifacts", "payload"),
        ):
            with self.subTest(table=table):
                with sqlite3.connect(self.storage / DATABASE) as db:
                    saved = db.execute(
                        f"SELECT rowid, {column} FROM {table} WHERE sid=?", (self.sid,)
                    ).fetchall()
                    db.execute(
                        f"UPDATE {table} SET {column}=? WHERE sid=?",
                        (b"PRIVATE broken body", self.sid),
                    )
                metadata = preview_retention(
                    self.storage, self.root, before_ns=CUTOFF, keep_newest=1
                )
                self.assertEqual(metadata.candidate_sessions, 2)
                before = self.files()
                output, errors = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(errors):
                    self.assertEqual(main(self.cli_args()), 2)
                self.assertEqual(output.getvalue(), "")
                self.assertNotIn("PRIVATE", errors.getvalue())
                self.assertEqual(self.files(), before)
                with sqlite3.connect(self.storage / DATABASE) as db:
                    db.executemany(
                        f"UPDATE {table} SET {column}=? WHERE rowid=?",
                        [(payload, rowid) for rowid, payload in saved],
                    )
        self.assert_saved()

    def test_new_generation_after_preview_invalidates_even_other_workspace_changes(
        self,
    ) -> None:
        preview = self.prune()
        other = self.root / "another-project"
        other.mkdir()
        state = self.fresh.model_copy(
            update={"session_id": f"{9:032x}", "workspace": str(other.resolve())}
        )
        self.seed(state, CUTOFF - 1)
        before = self.files()
        with self.assertRaisesRegex(ValueError, "selection changed"):
            self.prune(preview.prune_sha256, apply=True)
        self.assertEqual(self.files(), before)
        self.assert_saved()

    def test_generation_or_activity_race_between_preflight_and_write_rejects(
        self,
    ) -> None:
        store_type = prune_module._PruneStore  # pyright: ignore[reportPrivateUsage]
        original = store_type.apply
        for race in ("generation", "activity"):
            preview = self.prune()

            def changed(
                store: SQLiteConversationStore, plan: PrunePlan, race: str = race
            ) -> None:
                if race == "generation":
                    self.seed(
                        self.fresh.model_copy(update={"session_id": f"{9:032x}"}),
                        CUTOFF - 1,
                    )
                    original(store, plan)  # pyright: ignore[reportArgumentType]
                else:
                    with ConversationStore(
                        self.storage, f"{3:032x}", self.root, create=False
                    ):
                        original(store, plan)  # pyright: ignore[reportArgumentType]

            with (
                patch.object(store_type, "apply", changed),
                self.assertRaisesRegex(ValueError, "selection changed"),
            ):
                self.prune(preview.prune_sha256, apply=True)
            self.assert_saved()

    def test_root_database_and_lock_replacement_before_write_fail_closed(self) -> None:
        store_type = prune_module._PruneStore  # pyright: ignore[reportPrivateUsage]
        original = store_type.apply
        for target in ("database", "lock", "root"):
            preview = self.prune()

            def changed(
                store: SQLiteConversationStore, plan: PrunePlan, target: str = target
            ) -> None:
                if target == "root":
                    self.storage.rename(self.root / "previous-root")
                    shutil.copytree(self.root / "previous-root", self.storage)
                elif target == "database":
                    copy = self.storage / "replacement.db"
                    shutil.copyfile(self.storage / DATABASE, copy)
                    copy.chmod(0o600)
                    os.replace(copy, self.storage / DATABASE)
                else:
                    path = self.storage / f"{self.sid}.lock"
                    path.rename(self.storage / "previous.lock")
                    path.touch(mode=0o600)
                original(store, plan)  # pyright: ignore[reportArgumentType]

            with (
                patch.object(store_type, "apply", changed),
                self.assertRaisesRegex(ValueError, "changed"),
            ):
                self.prune(preview.prune_sha256, apply=True)
            self.assert_saved()

    def test_file_identity_changes_between_preview_and_apply_invalidate_hash(
        self,
    ) -> None:
        for target in (DATABASE, f"{self.sid}.lock"):
            preview = self.prune()
            path = self.storage / target
            copy = self.storage / "replacement"
            shutil.copyfile(path, copy)
            copy.chmod(0o600)
            os.replace(copy, path)
            with self.assertRaisesRegex(ValueError, "selection changed"):
                self.prune(preview.prune_sha256, apply=True)
        self.assert_saved()

    def test_error_after_delete_rolls_back_session_children_and_generation(
        self,
    ) -> None:
        before = self.rows()
        preview = self.prune()
        store_type = prune_module._PruneStore  # pyright: ignore[reportPrivateUsage]

        def fail(store: SQLiteConversationStore, db: sqlite3.Connection) -> None:
            db.execute("DELETE FROM sessions WHERE sid=?", (store.session_id,))
            raise OSError("PRIVATE disk full")

        with (
            patch.object(store_type, "_delete_selected", fail),
            self.assertRaises(OSError),
        ):
            self.prune(preview.prune_sha256, apply=True)
        self.assertEqual(self.rows(), before)
        self.assert_saved()

    def test_commit_failure_is_not_reported_as_success(self) -> None:
        original = prune_module.conversation_transaction
        before = self.rows()
        preview = self.prune()

        @contextmanager
        def fail_commit(
            db: sqlite3.Connection, *, write: bool = False
        ) -> Generator[None]:
            with original(db, write=write):
                yield
                if write:
                    raise sqlite3.OperationalError("PRIVATE commit failure")

        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.object(prune_module, "conversation_transaction", fail_commit),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            status = main(
                [*self.cli_args(), "--apply", "--expected-sha256", preview.prune_sha256]
            )
        self.assertEqual(status, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("PRIVATE", errors.getvalue())
        self.assertEqual(self.rows(), before)

    def test_final_verification_blocks_other_sqlite_writers(self) -> None:
        preview = self.prune()
        original = SQLiteConversationStore._load  # pyright: ignore[reportPrivateUsage]
        write_verifications = 0

        def verified(
            store: SQLiteConversationStore, db: sqlite3.Connection
        ) -> ConversationSnapshot:
            nonlocal write_verifications
            snapshot = original(store, db)
            with sqlite3.connect(self.storage / DATABASE, timeout=0) as writer:
                try:
                    writer.execute("BEGIN IMMEDIATE")
                except sqlite3.OperationalError:
                    write_verifications += 1
                else:
                    writer.rollback()
            return snapshot

        with patch.object(SQLiteConversationStore, "_load", verified):
            result = self.prune(preview.prune_sha256, apply=True)
        self.assertEqual(result.status, "deleted")
        self.assertEqual(write_verifications, 1)

    def test_actual_crash_before_commit_requires_recovery_and_preserves_state(
        self,
    ) -> None:
        preview = self.prune()
        result = self.crash(preview.prune_sha256, "before")
        self.assertEqual(result.returncode, 77, result.stderr)
        before = self.files()
        self.assertIn(DATABASE + "-journal", before)
        for apply in (False, True):
            with self.assertRaises(ValueError):
                self.prune(preview.prune_sha256, apply=apply)
        self.assertEqual(self.files(), before)
        with SQLiteConversationStore(
            self.storage, self.sid, self.root, create=False
        ) as recovered:
            self.assertEqual(recovered.inspect_snapshot()[0].state, self.state)
        self.assertEqual(self.prune().prune_sha256, preview.prune_sha256)

    def test_actual_crash_after_commit_leaves_no_false_retry_success(self) -> None:
        preview = self.prune()
        result = self.crash(preview.prune_sha256, "after")
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertFalse(any(row[0] == self.sid for row in self.rows()["sessions"]))
        with self.assertRaises(ValueError):
            self.prune(preview.prune_sha256, apply=True)
        self.assertTrue((self.storage / f"{self.sid}.json").exists())
        self.assertTrue((self.storage / f"{self.sid}.lock").exists())

    def crash(self, expected: str, boundary: str) -> subprocess.CompletedProcess[str]:
        code = """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.run.conversation_prune import _PruneStore, prune_session
original_delete = _PruneStore._delete_selected
original_apply = _PruneStore.apply
def before(store, db):
    db.execute("PRAGMA cache_size=1")
    original_delete(store, db)
    os._exit(77)
def after(store, plan):
    original_apply(store, plan)
    os._exit(77)
method, replacement = (
    ("_delete_selected", before) if sys.argv[5] == "before" else ("apply", after)
)
with patch.object(_PruneStore, method, replacement):
    prune_session(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3],
                  before_ns=int(sys.argv[6]), keep_newest=1,
                  expected_sha256=sys.argv[4], apply=True)
"""
        return subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                str(self.storage),
                str(self.root),
                self.sid,
                expected,
                boundary,
                str(CUTOFF),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_completed_review_evidence_is_verified_then_deleted_atomically(
        self,
    ) -> None:
        brief, recording = demo_inputs()
        fresh = self.fresh.model_copy(update={"session_id": f"{4:032x}"})
        chat = ConversationController(fresh, self.cassette, lambda state: None)
        chat.submit_review(ConversationReviewPacket(brief=brief, cassette=recording))
        asyncio.run(chat.step())
        self.seed(chat.state, CUTOFF - 1)
        preview = prune_session(
            self.storage, self.root, fresh.session_id, before_ns=CUTOFF, keep_newest=1
        )
        self.assertGreaterEqual(preview.plan.artifacts, 2)
        result = prune_session(
            self.storage,
            self.root,
            fresh.session_id,
            before_ns=CUTOFF,
            keep_newest=1,
            expected_sha256=preview.prune_sha256,
            apply=True,
        )
        self.assertEqual(result.removed_messages, 1)
        self.assertEqual(result.removed_artifacts, preview.plan.artifacts)
        self.assert_saved()

    def test_bad_inputs_workspace_and_permissions_never_create_or_delete(self) -> None:
        preview = self.prune()
        before_files = self.files()
        for mode in (0, 1, "yes"):
            with self.assertRaisesRegex(ValueError, "apply mode"):
                prune_session(
                    self.storage,
                    self.root,
                    self.sid,
                    before_ns=CUTOFF,
                    keep_newest=1,
                    expected_sha256=preview.prune_sha256,
                    apply=mode,  # pyright: ignore[reportArgumentType]
                )
        self.assertEqual(self.files(), before_files)
        for sid, before, keep in (
            ("PRIVATE", CUTOFF, 1),
            (self.sid, -1, 1),
            (self.sid, True, 1),
            (self.sid, CUTOFF, -1),
            (self.sid, CUTOFF, True),
        ):
            with self.assertRaises(ValueError):
                prune_session(
                    self.root / "absent",
                    self.root,
                    sid,
                    before_ns=before,
                    keep_newest=keep,
                )
        self.assertFalse((self.root / "absent").exists())
        with self.assertRaises(ValueError):
            prune_session(
                self.storage,
                self.root / "other-workspace",
                self.sid,
                before_ns=CUTOFF,
                keep_newest=1,
            )
        for path in (
            self.storage,
            self.storage / DATABASE,
            self.storage / f"{self.sid}.lock",
        ):
            mode = path.stat().st_mode & 0o777
            path.chmod(0o755 if path.is_dir() else 0o644)
            with self.assertRaises(ValueError):
                self.prune()
            path.chmod(mode)
        self.assert_saved()

    def test_receipt_and_selection_contracts_reject_tampering(self) -> None:
        preview = self.prune()
        for field, value in (
            ("session_id", f"{2:032x}"),
            ("snapshot_sha256", "0" * 64),
            ("artifact_bytes", 0),
            ("verification", "index_metadata"),
        ):
            changed = preview.plan.model_dump(mode="json")
            changed[field] = value
            with self.assertRaises(ValueError):
                PrunePlan.model_validate_json(json.dumps(changed))
        for field, value in (
            ("prune_sha256", "0" * 64),
            ("removed_sessions", 1),
            ("removed_messages", 1),
            ("removed_artifacts", 1),
            ("removed_artifact_bytes", 1),
            ("removed_snapshot_bytes", 1),
            ("status", "deleted"),
            ("published_json_untouched", False),
        ):
            changed = preview.model_dump(mode="json")
            changed[field] = value
            with self.assertRaises(ValueError):
                PruneReceipt.model_validate_json(json.dumps(changed))

    def test_cli_preview_and_apply_with_separate_prune_hash(self) -> None:
        args = [sys.executable, "-m", "mos_eisley.cli", *self.cli_args()]
        preview = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        payload = json.loads(preview.stdout)
        self.assertEqual(payload["type"], "conversation.prune")
        self.assertEqual(payload["status"], "planned")
        self.assertNotIn("PRIVATE", preview.stdout + preview.stderr)
        result = subprocess.run(
            [*args, "--apply", "--expected-sha256", payload["prune_sha256"]],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "deleted")
        missing = subprocess.run(
            [*args, "--apply", "--expected-sha256", payload["prune_sha256"]],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(missing.returncode, 2)
