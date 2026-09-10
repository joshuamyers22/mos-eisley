"""Exact imports, source preservation, interruption boundaries and CLI selection."""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
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
from mos_eisley.run.conversation_migration import ConversationMigration
from mos_eisley.run.conversation_sqlite import (
    DATABASE,
    SQLiteConversationStore,
    list_sqlite_conversations,
)
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore


class MigrationTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = ConversationController.fresh(self.root, demo_cassette())
        self.sid = self.state.session_id
        self.source = self.root / f"{self.sid}.json"
        with ConversationStore(self.root, self.sid, self.root) as store:
            store.save(self.state)

    def files(self) -> dict[str, tuple[bytes, int]]:
        return {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.root.iterdir()
            if path.is_file()
        }

    def apply(self) -> str:
        with ConversationMigration(self.root, self.sid, self.root) as migration:
            preview = migration.migrate()
            receipt = migration.migrate(
                apply=True, expected_sha256=preview.snapshot_sha256
            )
        self.assertEqual(receipt.snapshot_sha256, preview.snapshot_sha256)
        self.assertTrue(receipt.source_retained)
        return receipt.status

    def test_preview_and_selection_failures_do_not_create_destination(self) -> None:
        before = self.files()
        with ConversationMigration(self.root, self.sid, self.root) as migration:
            preview = migration.migrate()
            self.assertEqual(preview.status, "planned")
            self.assertEqual(preview.source_bytes, self.source.stat().st_size)
            self.assertEqual(
                preview.snapshot_sha256, digest(canonical_bytes(self.state))
            )
            self.assertEqual(preview.messages, 0)
            for expected in (None, "invalid", "0" * 64):
                with self.assertRaises(ValueError):
                    migration.migrate(apply=True, expected_sha256=expected)
        self.assertEqual(self.files(), before)

    def test_full_history_memory_review_and_retained_recording_are_exact(self) -> None:
        memory = MemoryStore(self.root / "memory", self.root)
        memory.change("user", "set", text="MIGRATION-MEMORY-CANARY")
        brief, recording = demo_inputs()
        with ConversationStore(self.root, self.sid, self.root, create=False) as store:
            controller = ConversationController(
                store.load(), demo_cassette(), store.save
            )
            runtime = ConversationMemoryRuntime(
                controller, memory, lambda selected: demo_cassette(memory=selected)
            )
            runtime.refresh(False, snapshot_max_bytes=4_000_000)
            controller.submit(DEMO_PROMPTS[0])
            asyncio.run(controller.step())
            runtime.refresh(True)
            controller.submit_review(
                ConversationReviewPacket(brief=brief, cassette=recording)
            )
            asyncio.run(controller.step())
            controller.submit("queued after review")
            state = controller.state
        before = (self.source.read_bytes(), self.source.stat().st_mtime_ns)
        self.assertGreater(state.revision, 0)
        self.assertEqual(self.apply(), "imported")
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            self.assertEqual(store.load(), state)
        row = list_sqlite_conversations(self.root, self.root).sessions[0]
        self.assertEqual(row.modified_ns, before[1])
        self.assertEqual(row.snapshot_sha256, digest(canonical_bytes(state)))
        self.assertEqual(row.messages, 3)
        self.assertEqual(row.pending, 1)
        self.assertEqual(
            (self.source.read_bytes(), self.source.stat().st_mtime_ns), before
        )
        imported = self.files()
        self.assertEqual(self.apply(), "already_present")
        self.assertEqual(self.files(), imported)

    def test_running_state_is_only_recovered_on_explicit_resume(self) -> None:
        with ConversationStore(self.root, self.sid, self.root, create=False) as store:
            state = store.load().model_copy(
                update={
                    "entries": (
                        ConversationEntry(text=DEMO_PROMPTS[0], status="running"),
                        ConversationEntry(text=DEMO_PROMPTS[1]),
                    ),
                    "revision": 1,
                    "exchanges_consumed": 1,
                }
            )
            store.save(state)
        before = self.source.read_bytes()
        self.apply()
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            self.assertEqual(store.load(), state)
            controller = ConversationController(state, demo_cassette(), store.save)
            self.assertEqual(controller.state.entries[0].status, "interrupted")
            self.assertEqual(controller.state.entries[1].status, "queued")
            self.assertEqual(controller.state.exchanges_consumed, 1)
            self.assertEqual(controller.state.revision, 2)
        self.assertEqual(self.source.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "different session state"):
            self.apply()

    def test_existing_database_preview_is_read_only_and_conflicts_fail(self) -> None:
        other = ConversationController.fresh(self.root, demo_cassette())
        with SQLiteConversationStore(self.root, other.session_id, self.root) as store:
            store.save(other)
        before = self.files()
        with ConversationMigration(self.root, self.sid, self.root) as migration:
            self.assertEqual(migration.migrate().status, "planned")
        self.assertEqual(self.files(), before)
        self.apply()
        with SQLiteConversationStore(
            self.root, self.sid, self.root, create=False
        ) as store:
            state = store.load()
            store.save(state.model_copy(update={"revision": state.revision + 1}))
        before = self.files()
        with self.assertRaisesRegex(ValueError, "different session state"):
            self.apply()
        self.assertEqual(self.files(), before)

    def test_failed_import_rolls_back_and_retry_succeeds(self) -> None:
        other = ConversationController.fresh(self.root, demo_cassette())
        with SQLiteConversationStore(self.root, other.session_id, self.root) as store:
            store.save(other)
        original = backend.conversation_transaction

        @contextmanager
        def fail_commit(
            db: sqlite3.Connection, *, write: bool = False
        ) -> Generator[None]:
            with original(db, write=write):
                yield
                if write:
                    raise OSError("injected disk-full before commit")

        before = list_sqlite_conversations(self.root, self.root)
        source = self.source.read_bytes()
        with (
            patch.object(backend, "conversation_transaction", fail_commit),
            self.assertRaisesRegex(OSError, "disk-full"),
        ):
            self.apply()
        self.assertEqual(list_sqlite_conversations(self.root, self.root), before)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(self.apply(), "imported")
        self.assertEqual(self.apply(), "already_present")

    def test_source_change_inside_transaction_rolls_back(self) -> None:
        original = backend.conversation_transaction
        changed = self.state.model_copy(update={"revision": 1})
        changed_snapshot = ConversationSnapshot(
            state=changed, sha256=digest(canonical_bytes(changed))
        )

        @contextmanager
        def change_source(
            db: sqlite3.Connection, *, write: bool = False
        ) -> Generator[None]:
            with original(db, write=write):
                if write:
                    self.source.write_bytes(canonical_bytes(changed_snapshot))
                yield

        # Initialize separately so the injection targets only the import transaction.
        other = ConversationController.fresh(self.root, demo_cassette())
        with SQLiteConversationStore(self.root, other.session_id, self.root) as store:
            store.save(other)
        before = list_sqlite_conversations(self.root, self.root)
        with (
            patch.object(backend, "conversation_transaction", change_source),
            self.assertRaisesRegex(ValueError, "source changed during"),
        ):
            self.apply()
        self.assertEqual(list_sqlite_conversations(self.root, self.root), before)
        self.assertEqual(self.apply(), "imported")

    def test_process_exit_with_hot_journal_recovers_only_on_apply(self) -> None:
        other = ConversationController.fresh(self.root, demo_cassette())
        with SQLiteConversationStore(self.root, other.session_id, self.root) as store:
            store.save(other)
        before = list_sqlite_conversations(self.root, self.root)
        source = self.source.read_bytes()
        selected = digest(canonical_bytes(self.state))
        crashed = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import os, sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from mos_eisley.run import conversation_sqlite as backend
from mos_eisley.run.conversation_migration import ConversationMigration
original = backend.conversation_transaction
@contextmanager
def crash(db, *, write=False):
    with original(db, write=write):
        yield
        if write:
            db.execute("PRAGMA cache_size=1")
            db.execute("UPDATE sessions SET header=zeroblob(100000)")
            os._exit(73)
root, sid, selected = sys.argv[1:]
with patch.object(backend, "conversation_transaction", crash):
    with ConversationMigration(Path(root), sid, Path(root)) as migration:
        migration.migrate(apply=True, expected_sha256=selected)
""",
                str(self.root),
                self.sid,
                selected,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(crashed.returncode, 73, crashed.stderr)
        journal = self.root / (DATABASE + "-journal")
        self.assertTrue(journal.exists())
        files = self.files()
        with (
            ConversationMigration(self.root, self.sid, self.root) as migration,
            self.assertRaises(ValueError),
        ):
            migration.migrate()
        self.assertEqual(self.files(), files)
        with ConversationMigration(self.root, self.sid, self.root) as migration:
            receipt = migration.migrate(apply=True, expected_sha256=selected)
        self.assertEqual(receipt.status, "imported")
        self.assertFalse(journal.exists())
        self.assertEqual(self.source.read_bytes(), source)
        with SQLiteConversationStore(
            self.root, other.session_id, self.root, create=False
        ) as store:
            self.assertEqual(store.load(), other)
        after = list_sqlite_conversations(self.root, self.root)
        self.assertEqual(len(after.sessions), len(before.sessions) + 1)
        self.assertEqual(self.apply(), "already_present")

    def test_reconstructed_destination_is_verified_before_commit(self) -> None:
        class MisreadingMigration(ConversationMigration):
            def _load(self, db: sqlite3.Connection) -> ConversationSnapshot:
                snapshot = super()._load(db)
                return snapshot.model_copy(
                    update={"state": snapshot.state.model_copy(update={"revision": 9})}
                )

        with (
            MisreadingMigration(self.root, self.sid, self.root) as migration,
            self.assertRaisesRegex(ValueError, "migration verification failed"),
        ):
            migration.migrate(
                apply=True, expected_sha256=digest(canonical_bytes(self.state))
            )
        self.assertEqual(list_sqlite_conversations(self.root, self.root).sessions, ())
        self.assertEqual(self.apply(), "imported")

    def test_source_lock_and_workspace_are_required(self) -> None:
        with (
            ConversationStore(self.root, self.sid, self.root, create=False),
            self.assertRaises(BlockingIOError),
        ):
            self.apply()
        self.apply()
        with (
            SQLiteConversationStore(self.root, self.sid, self.root, create=False),
            self.assertRaises(BlockingIOError),
        ):
            self.apply()
        other = self.root / "wrong-workspace"
        other.mkdir()
        with (
            ConversationMigration(self.root, self.sid, other) as migration,
            self.assertRaisesRegex(ValueError, "workspace"),
        ):
            migration.migrate()

    def test_missing_workspace_can_be_migrated_but_not_resumed(self) -> None:
        workspace = self.root / "removed"
        workspace.mkdir()
        state = ConversationController.fresh(workspace, demo_cassette())
        with ConversationStore(self.root, state.session_id, workspace) as store:
            store.save(state)
        workspace.rmdir()
        with ConversationMigration(self.root, state.session_id, workspace) as migration:
            preview = migration.migrate()
            self.assertEqual(
                migration.migrate(
                    apply=True, expected_sha256=preview.snapshot_sha256
                ).status,
                "imported",
            )
        with self.assertRaises((ValueError, FileNotFoundError)):
            SQLiteConversationStore(
                self.root, state.session_id, workspace, create=False
            )

    def test_untrusted_source_rejected_without_creating_database(self) -> None:
        original = self.source.read_bytes()
        for mode in ("corrupt", "public", "foreign", "symlink", "fifo"):
            with self.subTest(mode=mode):
                self.source.unlink()
                if mode == "symlink":
                    self.source.symlink_to(self.root / "absent")
                elif mode == "fifo":
                    os.mkfifo(self.source, 0o600)
                else:
                    self.source.write_bytes(original)
                    self.source.chmod(0o644 if mode == "public" else 0o600)
                    if mode == "corrupt":
                        self.source.write_bytes(b"{}")
                    elif mode == "foreign":
                        state = self.state.model_copy(
                            update={"owner_uid": os.getuid() + 1}
                        )
                        self.source.write_bytes(
                            canonical_bytes(
                                ConversationSnapshot(
                                    state=state, sha256=digest(canonical_bytes(state))
                                )
                            )
                        )
                with self.assertRaises((OSError, ValueError)):
                    self.apply()
                self.assertFalse((self.root / DATABASE).exists())

    def test_invalid_destination_preflight_retains_source(self) -> None:
        original = self.source.read_bytes()
        for name in (DATABASE, "sqlite.lock", DATABASE + "-journal", DATABASE + "-wal"):
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(b"")
                path.chmod(0o600)
                with self.assertRaises((ValueError, OSError)):
                    if name == "sqlite.lock":
                        path.chmod(0o644)
                    self.apply()
                self.assertEqual(self.source.read_bytes(), original)
                path.unlink()

    def test_cli_preview_apply_retry_and_resume_leave_json_unchanged(self) -> None:
        with ConversationStore(self.root, self.sid, self.root, create=False) as store:
            controller = ConversationController(
                store.load(), demo_cassette(), store.save
            )
            controller.submit(DEMO_PROMPTS[0])
            asyncio.run(controller.step())
        before = self.source.read_bytes()

        def invoke(*args: str, text: str = "") -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mos_eisley.cli",
                    *args,
                    "--storage",
                    str(self.root),
                    "-C",
                    str(self.root),
                    "--json",
                ],
                input=text,
                text=True,
                capture_output=True,
                timeout=20,
                env={**os.environ, "HOME": str(self.root)},
            )

        preview = invoke("session-migrate", self.sid)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        receipt = json.loads(preview.stdout)
        self.assertEqual(receipt["status"], "planned")
        self.assertNotIn(DEMO_PROMPTS[0], preview.stdout)
        missing = invoke("session-migrate", self.sid, "--apply")
        self.assertEqual(missing.returncode, 2, missing.stderr)
        self.assertFalse((self.root / DATABASE).exists())
        for status in ("imported", "already_present"):
            applied = invoke(
                "session-migrate",
                self.sid,
                "--apply",
                "--expected-sha256",
                receipt["snapshot_sha256"],
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(json.loads(applied.stdout)["status"], status)
        resumed = invoke(
            "resume",
            self.sid,
            "--storage-backend",
            "sqlite",
            text=DEMO_PROMPTS[1] + "\n",
        )
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn("You gave me a boundary of ten.", resumed.stdout)
        self.assertEqual(self.source.read_bytes(), before)
