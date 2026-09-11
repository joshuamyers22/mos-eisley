"""Workspace retention policy, bounded metadata reads and no deletion authority."""

import asyncio
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import weakref
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
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run import conversation_retention as retention
from mos_eisley.run.conversation_retention import (
    RetentionPlan,
    RetentionPreview,
    preview_retention,
    retention_cutoff,
)
from mos_eisley.run.conversation_sqlite import (
    DATABASE,
    SessionIndex,
    SQLiteConversationStore,
)
from mos_eisley.run.conversation_store import ConversationStore

CUTOFF = retention_cutoff("2026-08-01T00:00:00Z")


class RetentionPreviewTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = self.root / "sessions"
        self.cassette = demo_cassette()
        self.fresh = ConversationController.fresh(self.root, self.cassette)
        chat = ConversationController(self.fresh, self.cassette, lambda state: None)
        chat.refresh_memory(None, self.cassette)
        chat.submit(DEMO_PROMPTS[0])
        asyncio.run(chat.step())
        self.completed = chat.state
        self.seed(1, state=self.completed, modified_ns=CUTOFF - 100)
        self.seed(2, modified_ns=CUTOFF - 50)
        self.seed(3, state=self.completed, modified_ns=CUTOFF)
        for index, status in enumerate(
            ("queued", "running", "failed", "interrupted", "cancelled"), 4
        ):
            self.seed(index, status=status, modified_ns=CUTOFF - index)

    def seed(
        self,
        index: int,
        *,
        state: ConversationState | None = None,
        status: Status | None = None,
        modified_ns: int = CUTOFF - 1,
        workspace: Path | None = None,
    ) -> str:
        selected = self.fresh if state is None else state
        selected = selected.model_copy(
            update={
                "session_id": f"{index:032x}",
                "workspace": str((workspace or self.root).resolve()),
            }
        )
        if status is not None:
            selected = selected.model_copy(
                update={
                    "entries": (
                        ConversationEntry(text="PRIVATE retained work", status=status),
                    ),
                    "exchanges_consumed": 0 if status in {"queued", "cancelled"} else 1,
                }
            )
        with SQLiteConversationStore(
            self.storage, selected.session_id, workspace or self.root
        ) as store:
            store.import_snapshot(selected, modified_ns, validate_source=lambda: None)
        return selected.session_id

    def preview(self, *, keep: int = 1, before: int = CUTOFF) -> RetentionPreview:
        return preview_retention(
            self.storage, self.root, before_ns=before, keep_newest=keep
        )

    def files(self) -> dict[str, tuple[bytes, int, int]]:
        return {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino)
            for path in self.storage.iterdir()
            if path.is_file()
        }

    def test_policy_is_deterministic_and_read_only_with_exact_counts(self) -> None:
        before = self.files()
        with (
            patch.object(retention.os, "unlink", side_effect=AssertionError("deleted")),
            patch.object(retention.os, "fsync", side_effect=AssertionError("synced")),
        ):
            result = self.preview()
            self.assertEqual(self.preview(), result)
        self.assertEqual(self.files(), before)
        self.assertEqual(result.plan_sha256, digest(canonical_bytes(result.plan)))
        self.assertFalse(result.deletion_authorized)
        self.assertEqual(result.verification, "index_metadata")
        self.assertEqual((result.candidate_sessions, result.retained_sessions), (2, 6))
        self.assertEqual(
            result, RetentionPreview.model_validate_json(result.model_dump_json())
        )
        by_id = {
            int(item.summary.session_id, 16): item for item in result.plan.sessions
        }
        self.assertEqual(by_id[1].disposition, "candidate")
        self.assertEqual(by_id[2].disposition, "candidate")
        self.assertEqual(by_id[3].reasons, ("keep_newest", "not_before_cutoff"))
        for index in range(4, 9):
            self.assertEqual(by_id[index].reasons, ("noncompleted_messages",))
        self.assertEqual(
            result.candidate_snapshot_bytes,
            sum(by_id[index].summary.snapshot_bytes for index in (1, 2)),
        )
        self.assertNotIn("PRIVATE", result.model_dump_json())
        self.assertEqual(self.preview(keep=1000).candidate_sessions, 0)

    def test_cutoff_equality_and_recency_ties_have_stable_policy_order(self) -> None:
        sid = self.seed(9, state=self.completed, modified_ns=CUTOFF)
        result = self.preview(keep=1, before=CUTOFF + 1)
        self.assertEqual(result.plan.sessions[0].summary.session_id, sid)
        self.assertEqual(result.plan.sessions[0].reasons, ("keep_newest",))
        self.assertEqual(result.plan.sessions[1].summary.session_id, f"{3:032x}")
        self.assertEqual(result.plan.sessions[1].disposition, "candidate")
        equality = self.preview(keep=0)
        self.assertEqual(equality.plan.sessions[0].reasons, ("not_before_cutoff",))
        self.assertNotEqual(equality.plan_sha256, result.plan_sha256)

    def test_active_json_or_sqlite_handles_retain_otherwise_eligible_session(
        self,
    ) -> None:
        for backend in (ConversationStore, SQLiteConversationStore):
            with backend(self.storage, f"{1:032x}", self.root, create=False):
                result = self.preview()
                entry = next(
                    item
                    for item in result.plan.sessions
                    if item.summary.session_id == f"{1:032x}"
                )
                self.assertEqual(entry.reasons, ("active",))
                self.assertEqual(result.candidate_sessions, 1)
        self.assertEqual(self.preview().candidate_sessions, 2)

    def test_workspace_filter_excludes_foreign_indexes_and_missing_workspace_is_empty(
        self,
    ) -> None:
        other = self.root / "other-project"
        other.mkdir()
        sid = self.seed(9, workspace=other)
        with sqlite3.connect(self.storage / DATABASE) as db:
            db.execute(
                "UPDATE sessions SET record=? WHERE sid=?",
                (b"PRIVATE corrupt foreign index", sid),
            )
        before = self.files()
        result = self.preview()
        self.assertEqual(len(result.plan.sessions), 8)
        self.assertNotIn(
            sid, [item.summary.session_id for item in result.plan.sessions]
        )
        missing = self.root / "removed-project"
        empty = preview_retention(self.storage, missing, before_ns=CUTOFF)
        self.assertEqual(empty.plan.sessions, ())
        self.assertEqual(empty.candidate_snapshot_bytes, 0)
        self.assertFalse(missing.exists())
        self.assertEqual(self.files(), before)

    def test_metadata_transaction_never_reads_bodies_or_claims_full_verification(
        self,
    ) -> None:
        with sqlite3.connect(self.storage / DATABASE) as db:
            db.execute("UPDATE sessions SET header=?", (b"PRIVATE broken header",))
        before = self.files()
        read_transaction = retention.sqlite_read_transaction
        connections = 0
        queries: list[str] = []

        @contextmanager
        def guarded(root: Path) -> Generator[tuple[sqlite3.Connection, str, int]]:
            nonlocal connections
            connections += 1
            with read_transaction(root) as source:
                db = source[0]
                self.assertTrue(db.in_transaction)
                db.set_trace_callback(queries.append)

                def authorize(
                    action: int,
                    table: str | None,
                    column: str | None,
                    database: str | None,
                    trigger: str | None,
                ) -> int:
                    if action == sqlite3.SQLITE_READ and (
                        column == "header" or table in {"entries", "artifacts"}
                    ):
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK

                db.set_authorizer(authorize)
                yield source

        with patch.object(retention, "sqlite_read_transaction", side_effect=guarded):
            result = self.preview()
        self.assertEqual(connections, 1)
        self.assertEqual(result.candidate_sessions, 2)
        self.assertFalse(result.deletion_authorized)
        self.assertEqual(result.verification, "index_metadata")
        self.assertFalse(
            any("SELECT" in query and "header" in query for query in queries)
        )
        self.assertEqual(self.files(), before)
        with (
            SQLiteConversationStore(
                self.storage, f"{1:032x}", self.root, create=False, writable=False
            ) as store,
            self.assertRaises(ValueError),
        ):
            store.inspect_snapshot()

    def test_corrupt_selected_index_aborts_without_partial_report_or_content_echo(
        self,
    ) -> None:
        with sqlite3.connect(self.storage / DATABASE) as db:
            db.execute(
                "UPDATE sessions SET record=? WHERE sid=?",
                (b"PRIVATE invalid index", f"{1:032x}"),
            )
        before = self.files()
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(self.cli_args())
        self.assertEqual(status, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("PRIVATE", errors.getvalue())
        self.assertEqual(self.files(), before)
        with sqlite3.connect(self.storage / DATABASE) as db:
            invalid = b'{"PRIVATE": "schema failure"}'
            db.execute(
                "UPDATE sessions SET record=?, record_sha=? WHERE sid=?",
                (invalid, digest(invalid), f"{1:032x}"),
            )
        with redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(main(self.cli_args()), 2)
        self.assertNotIn("PRIVATE", output.getvalue() + errors.getvalue())

    def test_invalid_policy_timestamp_and_paths_do_not_create_storage(self) -> None:
        missing = self.root / "absent"
        for before, keep in (
            (-1, 1),
            (True, 1),
            (2**63, 1),
            (CUTOFF, -1),
            (CUTOFF, 1001),
            (CUTOFF, True),
        ):
            with self.assertRaises(ValueError):
                preview_retention(
                    missing, self.root, before_ns=before, keep_newest=keep
                )
        with self.assertRaises(FileNotFoundError):
            preview_retention(missing, self.root, before_ns=CUTOFF)
        self.assertFalse(missing.exists())
        for timestamp in (
            "PRIVATE",
            "2026-08-01",
            "2026-08-01T00:00:00+00:00",
            "2026-8-01T00:00:00Z",
            "2026-02-30T00:00:00Z",
            "1969-12-31T23:59:59Z",
            "2300-01-01T00:00:00Z",
        ):
            with self.assertRaises(ValueError):
                retention_cutoff(timestamp)
        self.assertEqual(retention_cutoff("1970-01-01T00:00:00Z"), 0)
        self.assertEqual(retention_cutoff("1970-01-01T00:00:01Z"), 1_000_000_000)
        workspace_file = self.root / "file"
        workspace_file.write_text("file")
        with self.assertRaises(ValueError):
            preview_retention(self.storage, workspace_file, before_ns=CUTOFF)

    def test_private_storage_and_missing_or_unsafe_lock_fail_closed(self) -> None:
        lock = self.storage / f"{1:032x}.lock"
        for path in (self.storage, self.storage / DATABASE, lock):
            mode = path.stat().st_mode & 0o777
            path.chmod(0o755 if path.is_dir() else 0o644)
            with self.assertRaises(ValueError):
                self.preview()
            path.chmod(mode)
        lock.rename(self.storage / "saved.lock")
        with self.assertRaises(FileNotFoundError):
            self.preview()
        self.assertFalse(lock.exists())
        lock.symlink_to(self.storage / "saved.lock")
        with self.assertRaises(OSError):
            self.preview()
        lock.unlink()
        os.link(self.storage / "saved.lock", lock)
        with self.assertRaises(ValueError):
            self.preview()
        lock.unlink()
        os.mkfifo(lock, mode=0o600)
        with self.assertRaises(ValueError):
            self.preview()

    def test_directory_replacement_during_index_reads_is_rejected(self) -> None:
        original = retention.read_sqlite_session_index
        replaced = False

        def swap(db: sqlite3.Connection, sid: str, workspace: str) -> SessionIndex:
            nonlocal replaced
            index = original(db, sid, workspace)
            if not replaced:
                replaced = True
                self.storage.rename(self.root / "previous")
                shutil.copytree(self.root / "previous", self.storage)
            return index

        with (
            patch.object(retention, "read_sqlite_session_index", side_effect=swap),
            self.assertRaisesRegex(ValueError, "directory changed"),
        ):
            self.preview()
        self.assertEqual(
            self.files()[DATABASE][0], (self.root / "previous" / DATABASE).read_bytes()
        )

    def test_hot_journal_is_not_recovered_by_preview(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import os, sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.execute("PRAGMA cache_size=1")
db.execute("BEGIN IMMEDIATE")
db.execute("UPDATE sessions SET header=zeroblob(100000)")
os._exit(77)
""",
                str(self.storage / DATABASE),
            ],
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 77, result.stderr.decode())
        before = self.files()
        self.assertIn(DATABASE + "-journal", before)
        with self.assertRaises(ValueError):
            self.preview()
        self.assertEqual(self.files(), before)

    def test_full_thousand_session_metadata_bound_and_no_silent_partial_selection(
        self,
    ) -> None:
        with sqlite3.connect(self.storage / DATABASE) as db:
            payload, header = db.execute(
                "SELECT record, header FROM sessions WHERE sid=?", (f"{2:032x}",)
            ).fetchone()
            template = SessionIndex.model_validate_json(payload)
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("DELETE FROM sessions")
            for index in range(1000):
                sid = f"{index:032x}"
                record = template.model_copy(
                    update={
                        "summary": template.summary.model_copy(
                            update={"session_id": sid}
                        )
                    }
                )
                encoded = canonical_bytes(record)
                db.execute(
                    "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        sid,
                        record.workspace,
                        record.summary.modified_ns,
                        encoded,
                        digest(encoded),
                        header,
                    ),
                )
                (self.storage / f"{sid}.lock").touch(mode=0o600, exist_ok=True)
            db.execute("UPDATE metadata SET generation=generation+1")
        result = self.preview(keep=20)
        self.assertEqual(
            (result.candidate_sessions, result.retained_sessions), (980, 20)
        )
        self.assertEqual(len(result.plan.sessions), 1000)
        self.seed(1001)
        with (
            patch.object(
                retention,
                "read_sqlite_session_index",
                side_effect=AssertionError("read indexes before count bound"),
            ),
            self.assertRaisesRegex(ValueError, "1000-session"),
        ):
            self.preview()

    def test_preview_hash_changes_with_policy_generation_and_activity(self) -> None:
        initial = self.preview()
        self.assertNotEqual(initial.plan_sha256, self.preview(keep=0).plan_sha256)
        with ConversationStore(self.storage, f"{1:032x}", self.root, create=False):
            self.assertNotEqual(initial.plan_sha256, self.preview().plan_sha256)
        self.assertEqual(initial.plan_sha256, self.preview().plan_sha256)
        other = self.root / "other"
        other.mkdir()
        self.seed(9, workspace=other)
        changed = self.preview()
        self.assertEqual(changed.plan.sessions, initial.plan.sessions)
        self.assertGreater(changed.plan.generation, initial.plan.generation)
        self.assertNotEqual(changed.plan_sha256, initial.plan_sha256)

    def test_full_indexes_are_released_between_reads(self) -> None:
        original = retention.read_sqlite_session_index
        references: list[weakref.ReferenceType[SessionIndex]] = []

        def observed(db: sqlite3.Connection, sid: str, workspace: str) -> SessionIndex:
            self.assertTrue(all(reference() is None for reference in references))
            result = original(db, sid, workspace)
            references.append(weakref.ref(result))
            return result

        with patch.object(retention, "read_sqlite_session_index", side_effect=observed):
            self.assertEqual(len(self.preview().plan.sessions), 8)
        self.assertEqual(len(references), 8)
        self.assertTrue(all(reference() is None for reference in references))

    def test_oversized_catalog_ids_and_checksums_fail_before_index_reads(self) -> None:
        sid = f"{1:032x}"
        with sqlite3.connect(self.storage / DATABASE) as db:
            original_sha = db.execute(
                "SELECT record_sha FROM sessions WHERE sid=?", (sid,)
            ).fetchone()[0]
        for field in ("sid", "record_sha"):
            with sqlite3.connect(self.storage / DATABASE) as db:
                db.execute("PRAGMA ignore_check_constraints=ON")
                db.execute(
                    f"UPDATE sessions SET {field}=? WHERE sid=?", ("x" * 128_000, sid)
                )
            with (
                patch.object(
                    retention,
                    "read_sqlite_session_index",
                    side_effect=AssertionError("read invalid metadata"),
                ),
                self.assertRaisesRegex(ValueError, "identity or checksum size"),
            ):
                self.preview()
            with sqlite3.connect(self.storage / DATABASE) as db:
                db.execute(
                    f"UPDATE sessions SET {field}=? WHERE sid=?",
                    (
                        sid if field == "sid" else original_sha,
                        "x" * 128_000 if field == "sid" else sid,
                    ),
                )

    def test_oversized_foreign_owner_and_inconsistent_index_records_fail_closed(
        self,
    ) -> None:
        sid = f"{1:032x}"
        with sqlite3.connect(self.storage / DATABASE) as db:
            payload = db.execute(
                "SELECT record FROM sessions WHERE sid=?", (sid,)
            ).fetchone()[0]
        template = json.loads(payload)
        wrong_owner = {**template, "owner_uid": os.getuid() + 1}
        wrong_counts = {**template, "summary": {**template["summary"], "pending": 1}}
        for encoded in (
            json.dumps(wrong_owner).encode(),
            json.dumps(wrong_counts).encode(),
            b" " * 32_001,
        ):
            with sqlite3.connect(self.storage / DATABASE) as db:
                db.execute("PRAGMA ignore_check_constraints=ON")
                db.execute(
                    "UPDATE sessions SET record=?, record_sha=? WHERE sid=?",
                    (encoded, digest(encoded), sid),
                )
            before = self.files()
            with self.assertRaises(ValueError):
                self.preview()
            self.assertEqual(self.files(), before)

    def test_contracts_reject_policy_order_counts_and_authority_tampering(self) -> None:
        initial = self.preview()
        for field, value in (
            (
                "sessions",
                list(reversed(initial.plan.model_dump(mode="json")["sessions"])),
            ),
            ("policy", {"before_ns": CUTOFF, "keep_newest": 0}),
        ):
            changed = initial.plan.model_dump(mode="json")
            changed[field] = value
            with self.assertRaises(ValueError):
                RetentionPlan.model_validate_json(json.dumps(changed))
        for field, value in (
            ("plan_sha256", "0" * 64),
            ("candidate_sessions", 1000),
            ("retained_sessions", 0),
            ("candidate_snapshot_bytes", 0),
            ("retained_snapshot_bytes", 0),
            ("deletion_authorized", True),
            ("verification", "full_state"),
            ("mode", "apply"),
        ):
            changed = initial.model_dump(mode="json")
            changed[field] = value
            with self.assertRaises(ValueError):
                RetentionPreview.model_validate_json(json.dumps(changed))

    def cli_args(self) -> list[str]:
        return [
            "session-retention",
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

    def test_cli_reports_preview_and_has_no_apply_or_deletion_hash_option(self) -> None:
        before = self.files()
        args = [sys.executable, "-m", "mos_eisley.cli", *self.cli_args()]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["type"], "conversation.retention")
        self.assertEqual(payload["candidate_sessions"], 2)
        self.assertFalse(payload["deletion_authorized"])
        for extra in (("--apply",), ("--expected-sha256", payload["plan_sha256"])):
            invalid = subprocess.run(
                [*args, *extra], capture_output=True, text=True, timeout=30
            )
            self.assertEqual(invalid.returncode, 2)
        self.assertEqual(self.files(), before)
