"""Explicit batch selection, bounded reads, interruption and exact retry checks."""

import asyncio
import json
import shutil
import sqlite3
import subprocess
import sys
import weakref
from collections.abc import Generator
from contextlib import contextmanager
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
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.demo import demo_inputs
from mos_eisley.run import conversation_batch_migration as batch_module
from mos_eisley.run import conversation_sqlite as sqlite_backend
from mos_eisley.run.conversation_batch_migration import (
    BatchMigrationError,
    BatchMigrationReceipt,
    migrate_batch,
)
from mos_eisley.run.conversation_migration import (
    ConversationMigration,
    ConversationMigrationReceipt,
    MigrationSelection,
)
from mos_eisley.run.conversation_sqlite import (
    DATABASE,
    SQLiteConversationStore,
    list_sqlite_conversations,
)
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore


class BatchMigrationTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = self.root / "sessions"
        self.ids = tuple(f"{value:032x}" for value in (1, 2, 3))
        self.states: dict[str, ConversationState] = {}
        for index, sid in enumerate(self.ids):
            cassette = demo_cassette()
            state = ConversationController.fresh(self.root, cassette).model_copy(
                update={"session_id": sid}
            )
            with ConversationStore(self.storage, sid, self.root) as store:
                store.save(state)
                chat = ConversationController(state, cassette, store.save)
                if index == 0:
                    chat.refresh_memory(None, cassette)
                    chat.submit(DEMO_PROMPTS[0])
                    asyncio.run(chat.step())
                    chat.submit(DEMO_PROMPTS[1])
                    state = chat.state
                elif index == 1:
                    state = state.model_copy(
                        update={
                            "revision": 1,
                            "exchanges_consumed": 1,
                            "entries": (
                                ConversationEntry(
                                    text="PRIVATE running prompt", status="running"
                                ),
                            ),
                        }
                    )
                    store.save(state)
                else:
                    brief, recording = demo_inputs()
                    chat.submit_review(
                        ConversationReviewPacket(brief=brief, cassette=recording)
                    )
                    asyncio.run(chat.step())
                    state = chat.state
                self.states[sid] = state

    def files(self) -> dict[str, tuple[bytes, int]]:
        return {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.storage.iterdir()
            if path.is_file()
        }

    def apply(self, expected: str) -> BatchMigrationReceipt:
        return migrate_batch(
            self.storage, self.ids, self.root, expected_sha256=expected, apply=True
        )

    def assert_destinations(self) -> None:
        for sid, expected in self.states.items():
            with SQLiteConversationStore(
                self.storage, sid, self.root, create=False
            ) as store:
                self.assertEqual(
                    canonical_bytes(store.load()), canonical_bytes(expected)
                )

    def test_preview_is_read_only_sorted_and_reports_exact_sizes_and_hashes(
        self,
    ) -> None:
        before = self.files()
        preview = migrate_batch(self.storage, tuple(reversed(self.ids)), self.root)
        self.assertEqual(preview.status, "planned")
        self.assertEqual(
            tuple(entry.session_id for entry in preview.plan.entries), self.ids
        )
        self.assertEqual(
            preview.plan.source_bytes,
            sum(len(before[f"{sid}.json"][0]) for sid in self.ids),
        )
        self.assertEqual(
            preview.plan.logical_bytes,
            sum(receipt.logical_bytes for receipt in preview.receipts),
        )
        self.assertEqual(
            preview.plan.messages,
            sum(len(state.entries) for state in self.states.values()),
        )
        self.assertEqual(preview.batch_sha256, digest(canonical_bytes(preview.plan)))
        self.assertEqual(
            preview,
            BatchMigrationReceipt.model_validate_json(preview.model_dump_json()),
        )
        self.assertNotIn("PRIVATE", preview.model_dump_json())
        self.assertEqual(self.files(), before)
        self.assertFalse((self.storage / DATABASE).exists())

    def test_apply_preserves_sources_exact_state_and_hash_stable_retry(self) -> None:
        before = self.files()
        preview = migrate_batch(self.storage, self.ids, self.root)
        result = self.apply(preview.batch_sha256)
        self.assertEqual(
            (result.status, result.imported, result.already_present),
            ("completed", 3, 0),
        )
        self.assert_destinations()
        after = self.files()
        for name, source in before.items():
            self.assertEqual(after[name], source)
        repeated = self.apply(preview.batch_sha256)
        self.assertEqual((repeated.imported, repeated.already_present), (0, 3))
        self.assertEqual(repeated.batch_sha256, preview.batch_sha256)
        self.assertEqual(self.files(), after)
        again = migrate_batch(self.storage, self.ids, self.root)
        self.assertEqual(again.batch_sha256, preview.batch_sha256)
        self.assertEqual(again.already_present, 3)

    def test_bad_selection_hash_duplicate_and_bounds_reject_before_writes(self) -> None:
        before = self.files()
        for ids in (
            (),
            self.ids + (self.ids[0],),
            tuple(f"{n:032x}" for n in range(33)),
            ("PRIVATE",),
        ):
            with self.subTest(ids=ids), self.assertRaises(ValueError) as caught:
                migrate_batch(self.storage, ids, self.root)
            self.assertNotIn("PRIVATE", str(caught.exception))
        for expected in (None, "not-a-hash", "0" * 64):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                migrate_batch(
                    self.storage,
                    self.ids,
                    self.root,
                    apply=True,
                    expected_sha256=expected,
                )
        preview = migrate_batch(self.storage, self.ids, self.root)
        with self.assertRaisesRegex(ValueError, "selection changed"):
            migrate_batch(
                self.storage,
                self.ids[:2],
                self.root,
                apply=True,
                expected_sha256=preview.batch_sha256,
            )
        self.assertEqual(self.files(), before)

    def test_all_sources_checked_before_import_when_last_source_changes(self) -> None:
        preview = migrate_batch(self.storage, self.ids, self.root)
        sid = self.ids[-1]
        with ConversationStore(self.storage, sid, self.root, create=False) as store:
            state = store.load()
            store.save(state.model_copy(update={"revision": state.revision + 1}))
        before = self.files()
        with self.assertRaisesRegex(ValueError, "selection changed"):
            self.apply(preview.batch_sha256)
        self.assertEqual(self.files(), before)

    def test_mid_batch_failure_reports_committed_prefix_and_retry_finishes(
        self,
    ) -> None:
        preview = migrate_batch(self.storage, self.ids, self.root)
        original = ConversationMigration.migrate

        def fail_second(
            migration: ConversationMigration, **kwargs: object
        ) -> ConversationMigrationReceipt:
            if migration.session_id == self.ids[1]:
                raise OSError("PRIVATE simulated disk full")
            return original(migration, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(ConversationMigration, "migrate", fail_second),
            self.assertRaises(BatchMigrationError) as caught,
        ):
            self.apply(preview.batch_sha256)
        result = caught.exception.receipt
        self.assertEqual(
            (result.status, result.imported, result.failed_session_id),
            ("stopped", 1, self.ids[1]),
        )
        self.assertNotIn("PRIVATE", result.model_dump_json() + str(caught.exception))
        self.assertEqual(result.failure, "storage_unavailable")
        self.assertEqual(
            len(list_sqlite_conversations(self.storage, self.root).sessions), 1
        )
        retry = self.apply(preview.batch_sha256)
        self.assertEqual((retry.imported, retry.already_present), (2, 1))
        self.assert_destinations()

    def test_failure_after_commit_is_resolved_by_retry_verification(self) -> None:
        preview = migrate_batch(self.storage, self.ids, self.root)
        original = ConversationMigration.migrate

        def lose_ack(
            migration: ConversationMigration, **kwargs: object
        ) -> ConversationMigrationReceipt:
            result = original(migration, **kwargs)  # type: ignore[arg-type]
            if migration.session_id == self.ids[1]:
                raise OSError("lost receipt after commit")
            return result

        with (
            patch.object(ConversationMigration, "migrate", lose_ack),
            self.assertRaises(BatchMigrationError),
        ):
            self.apply(preview.batch_sha256)
        retry = self.apply(preview.batch_sha256)
        self.assertEqual((retry.imported, retry.already_present), (1, 2))
        self.assert_destinations()

    def test_destination_conflict_is_reported_without_overwrite(self) -> None:
        preview = migrate_batch(self.storage, self.ids, self.root)
        sid = self.ids[1]
        with ConversationMigration(self.storage, sid, self.root) as migration:
            migration.migrate(
                apply=True, expected_sha256=digest(canonical_bytes(self.states[sid]))
            )
        changed = self.states[sid].model_copy(
            update={"revision": self.states[sid].revision + 1}
        )
        with SQLiteConversationStore(
            self.storage, sid, self.root, create=False
        ) as store:
            store.load()
            store.save(changed)
        before = self.files()
        with self.assertRaises(BatchMigrationError) as caught:
            migrate_batch(self.storage, self.ids, self.root)
        self.assertEqual(caught.exception.receipt.mode, "preview")
        self.assertEqual(self.files(), before)
        with self.assertRaises(BatchMigrationError) as caught:
            self.apply(preview.batch_sha256)
        self.assertEqual(caught.exception.receipt.imported, 1)
        with SQLiteConversationStore(
            self.storage, sid, self.root, create=False
        ) as store:
            self.assertEqual(store.load(), changed)

    def test_source_read_budget_rejects_before_destination_access(self) -> None:
        first = (self.storage / f"{self.ids[0]}.json").stat().st_size
        observed: list[int] = []
        original = ConversationMigration.inspect_selection

        def inspect(
            migration: ConversationMigration, *, source_max_bytes: int
        ) -> MigrationSelection:
            observed.append(source_max_bytes)
            return original(migration, source_max_bytes=source_max_bytes)

        with (
            patch.object(batch_module, "MAX_BATCH_SOURCE_BYTES", first + 1),
            patch.object(ConversationMigration, "inspect_selection", inspect),
            patch.object(
                ConversationMigration,
                "migrate",
                side_effect=AssertionError("destination accessed"),
            ),
            self.assertRaisesRegex(ValueError, "source preflight"),
        ):
            migrate_batch(self.storage, self.ids, self.root)
        self.assertEqual(observed, [first + 1, 1])
        self.assertFalse((self.storage / DATABASE).exists())

    def test_plan_releases_each_decoded_snapshot_before_reading_the_next(self) -> None:
        previous: list[weakref.ReferenceType[ConversationSnapshot]] = []
        original = ConversationMigration.inspect_selection
        read = ConversationMigration.inspect_json_snapshot

        def inspect(
            migration: ConversationMigration, *, source_max_bytes: int
        ) -> MigrationSelection:
            self.assertTrue(all(ref() is None for ref in previous))
            return original(migration, source_max_bytes=source_max_bytes)

        def snapshot(
            migration: ConversationMigration, *, byte_limit: int = 32_000_000
        ) -> tuple[ConversationSnapshot, int, int]:
            result = read(migration, byte_limit=byte_limit)
            previous.append(weakref.ref(result[0]))
            return result

        with (
            patch.object(ConversationMigration, "inspect_selection", inspect),
            patch.object(ConversationMigration, "inspect_json_snapshot", snapshot),
        ):
            migrate_batch(self.storage, self.ids, self.root)
        self.assertTrue(all(ref() is None for ref in previous))

    def test_storage_identity_and_workspace_bind_the_batch(self) -> None:
        preview = migrate_batch(self.storage, self.ids, self.root)
        copied = self.root / "copied"
        shutil.copytree(self.storage, copied)
        with self.assertRaisesRegex(ValueError, "selection changed"):
            migrate_batch(
                copied,
                self.ids,
                self.root,
                apply=True,
                expected_sha256=preview.batch_sha256,
            )
        self.assertFalse((copied / DATABASE).exists())
        wrong = self.root / "wrong-workspace"
        wrong.mkdir()
        with self.assertRaisesRegex(ValueError, "preflight"):
            migrate_batch(self.storage, self.ids, wrong)
        with (
            ConversationStore(self.storage, self.ids[-1], self.root, create=False),
            self.assertRaisesRegex(ValueError, "preflight"),
        ):
            migrate_batch(self.storage, self.ids, self.root)
        self.assertFalse((self.storage / DATABASE).exists())

    def test_replaced_storage_directory_after_source_preflight_is_rejected(
        self,
    ) -> None:
        preview = migrate_batch(self.storage, self.ids, self.root)
        original = ConversationMigration.inspect_selection
        archived = self.root / "old-storage"

        def replace(
            migration: ConversationMigration, *, source_max_bytes: int
        ) -> MigrationSelection:
            selected = original(migration, source_max_bytes=source_max_bytes)
            if migration.session_id == self.ids[-1]:
                self.storage.rename(archived)
                shutil.copytree(archived, self.storage)
            return selected

        with (
            patch.object(ConversationMigration, "inspect_selection", replace),
            self.assertRaises(BatchMigrationError) as caught,
        ):
            self.apply(preview.batch_sha256)
        self.assertEqual(caught.exception.receipt.receipts, ())
        self.assertFalse((self.storage / DATABASE).exists())
        self.assertFalse((archived / DATABASE).exists())

    def test_maximum_thirty_two_explicit_sources_can_be_previewed(self) -> None:
        for number in range(4, 33):
            sid = f"{number:032x}"
            state = ConversationController.fresh(self.root, demo_cassette()).model_copy(
                update={"session_id": sid}
            )
            with ConversationStore(self.storage, sid, self.root) as store:
                store.save(state)
        ids = tuple(f"{number:032x}" for number in range(1, 33))
        result = migrate_batch(self.storage, ids, self.root)
        self.assertEqual(len(result.plan.entries), 32)
        self.assertEqual(len(result.receipts), 32)
        self.assertFalse((self.storage / DATABASE).exists())

    def test_source_change_after_preflight_is_rejected_before_its_import(self) -> None:
        preview = migrate_batch(self.storage, self.ids, self.root)
        original = ConversationMigration.migrate

        def change(
            migration: ConversationMigration, **kwargs: object
        ) -> ConversationMigrationReceipt:
            if migration.session_id == self.ids[1]:
                path = self.storage / f"{migration.session_id}.json"
                path.write_bytes(path.read_bytes() + b" ")
            return original(migration, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(ConversationMigration, "migrate", change),
            self.assertRaises(BatchMigrationError) as caught,
        ):
            self.apply(preview.batch_sha256)
        self.assertEqual(caught.exception.receipt.imported, 1)
        self.assertEqual(
            len(list_sqlite_conversations(self.storage, self.root).sessions), 1
        )

    def test_invalid_receipt_totals_and_selection_are_rejected(self) -> None:
        preview = migrate_batch(self.storage, self.ids, self.root)
        changes: tuple[dict[str, object], ...] = (
            {"imported": 1},
            {"batch_sha256": "0" * 64},
            {"receipts": []},
            {"status": "stopped"},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                BatchMigrationReceipt.model_validate_json(
                    json.dumps({**preview.model_dump(mode="json"), **change})
                )

    def test_source_size_change_inside_transaction_rolls_back_even_with_same_hash(
        self,
    ) -> None:
        first = self.ids[0]
        with ConversationMigration(self.storage, first, self.root) as migration:
            migration.migrate(
                apply=True, expected_sha256=digest(canonical_bytes(self.states[first]))
            )
        source = self.storage / f"{self.ids[1]}.json"
        selected_bytes = source.read_bytes() + b" "
        source.write_bytes(selected_bytes)
        preview = migrate_batch(self.storage, self.ids, self.root)
        original = sqlite_backend.conversation_transaction

        @contextmanager
        def change_encoding(
            db: sqlite3.Connection, *, write: bool = False
        ) -> Generator[None]:
            with original(db, write=write):
                if write:
                    source.write_bytes(selected_bytes[:-1])
                yield

        with (
            patch.object(sqlite_backend, "conversation_transaction", change_encoding),
            self.assertRaises(BatchMigrationError) as caught,
        ):
            self.apply(preview.batch_sha256)
        self.assertEqual(caught.exception.receipt.failed_session_id, self.ids[1])
        self.assertEqual(caught.exception.receipt.imported, 0)
        self.assertEqual(caught.exception.receipt.already_present, 1)
        self.assertEqual(
            len(list_sqlite_conversations(self.storage, self.root).sessions), 1
        )
        source.write_bytes(selected_bytes)
        self.assertEqual(self.apply(preview.batch_sha256).imported, 2)

    def test_process_exit_hot_journal_preview_read_only_apply_recovers(self) -> None:
        first = self.ids[0]
        with ConversationMigration(self.storage, first, self.root) as migration:
            migration.migrate(
                apply=True, expected_sha256=digest(canonical_bytes(self.states[first]))
            )
        preview = migrate_batch(self.storage, self.ids, self.root)
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
from mos_eisley.run.conversation_batch_migration import migrate_batch
original = backend.conversation_transaction
@contextmanager
def crash(db, *, write=False):
    with original(db, write=write):
        yield
        if write:
            db.execute("PRAGMA cache_size=1")
            db.execute("UPDATE sessions SET header=zeroblob(100000)")
            os._exit(77)
storage, workspace, selected, *ids = sys.argv[1:]
with patch.object(backend, "conversation_transaction", crash):
    migrate_batch(
        Path(storage), tuple(ids), Path(workspace),
        apply=True, expected_sha256=selected,
    )
""",
                str(self.storage),
                str(self.root),
                preview.batch_sha256,
                *self.ids,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(crashed.returncode, 77, crashed.stderr)
        self.assertTrue((self.storage / (DATABASE + "-journal")).exists())
        before = self.files()
        with self.assertRaises(BatchMigrationError):
            migrate_batch(self.storage, self.ids, self.root)
        self.assertEqual(self.files(), before)
        recovered = self.apply(preview.batch_sha256)
        self.assertEqual((recovered.imported, recovered.already_present), (2, 1))
        self.assert_destinations()
        self.assertFalse((self.storage / (DATABASE + "-journal")).exists())

    def test_cli_preview_apply_retry_and_safe_source_failure(self) -> None:
        command = [
            sys.executable,
            "-m",
            "mos_eisley.cli",
            "session-migrate-batch",
            *self.ids,
            "--storage",
            str(self.storage),
            "-C",
            str(self.root),
            "--json",
        ]

        def invoke(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [*command, *args], capture_output=True, text=True, timeout=30
            )

        preview = invoke()
        self.assertEqual(preview.returncode, 0, preview.stderr)
        report = json.loads(preview.stdout)
        self.assertEqual(report["type"], "conversation.migration_batch")
        applied = invoke("--apply", "--expected-sha256", report["batch_sha256"])
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(json.loads(applied.stdout)["imported"], 3)
        repeated = invoke("--apply", "--expected-sha256", report["batch_sha256"])
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout)["already_present"], 3)
        with SQLiteConversationStore(
            self.storage, self.ids[-1], self.root, create=False
        ) as store:
            state = store.load()
            store.save(state.model_copy(update={"revision": state.revision + 1}))
        conflict = invoke()
        self.assertEqual(conflict.returncode, 2, conflict.stderr)
        stopped = json.loads(conflict.stdout)
        self.assertEqual(stopped["status"], "stopped")
        self.assertEqual(stopped["already_present"], 2)
        self.assertEqual(stopped["failed_session_id"], self.ids[-1])
        self.assertNotIn("PRIVATE", conflict.stdout + conflict.stderr)
        (self.storage / f"{self.ids[-1]}.json").write_bytes(
            b'{"PRIVATE": "bad source"}'
        )
        failed = invoke()
        self.assertEqual(failed.returncode, 2)
        self.assertNotIn("PRIVATE", failed.stdout + failed.stderr)
