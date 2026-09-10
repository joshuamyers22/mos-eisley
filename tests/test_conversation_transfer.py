"""Cross-root selection, immutable source, conflict and interruption guarantees."""

import asyncio
import json
import shutil
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
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.demo import demo_inputs
from mos_eisley.run import conversation_sqlite as sqlite_backend
from mos_eisley.run import conversation_transfer as transfer_module
from mos_eisley.run.conversation_migration import ConversationMigration
from mos_eisley.run.conversation_sqlite import (
    DATABASE,
    SQLiteConversationStore,
    list_sqlite_conversations,
)
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.conversation_transfer import (
    ConversationTransferPlan,
    ConversationTransferReceipt,
    transfer_conversation,
)


class ConversationTransferTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.target = self.root / "destination"
        self.target.mkdir(mode=0o700)
        cassette = demo_cassette()
        state = ConversationController.fresh(self.root, cassette)
        self.sid = state.session_id
        with ConversationStore(self.source, self.sid, self.root) as store:
            store.save(state)
            chat = ConversationController(state, cassette, store.save)
            chat.refresh_memory(None, cassette)
            chat.submit(DEMO_PROMPTS[0])
            asyncio.run(chat.step())
            chat.submit(DEMO_PROMPTS[1])
            self.state = chat.state
        self.source_file = self.source / f"{self.sid}.json"

    def transfer(
        self, expected: str | None = None, *, apply: bool = False
    ) -> ConversationTransferReceipt:
        return transfer_conversation(
            self.source,
            self.target,
            self.sid,
            self.root,
            expected_sha256=expected,
            apply=apply,
        )

    def files(self, root: Path) -> dict[str, tuple[bytes, int]]:
        return {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.iterdir()
            if path.is_file()
        }

    def assert_destination(self) -> None:
        with SQLiteConversationStore(
            self.target, self.sid, self.root, create=False, writable=False
        ) as store:
            self.assertEqual(canonical_bytes(store.load()), canonical_bytes(self.state))

    def test_preview_apply_retry_preserves_source_state_admission_and_timestamp(
        self,
    ) -> None:
        before = self.files(self.source)
        preview = self.transfer()
        self.assertEqual(preview.status, "planned")
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertEqual(
            preview.plan.selection.source_bytes, self.source_file.stat().st_size
        )
        self.assertEqual(preview.transfer_sha256, digest(canonical_bytes(preview.plan)))
        self.assertNotIn(DEMO_PROMPTS[0], preview.model_dump_json())
        self.assertEqual(
            preview,
            ConversationTransferReceipt.model_validate_json(preview.model_dump_json()),
        )
        result = self.transfer(preview.transfer_sha256, apply=True)
        self.assertEqual(result.status, "imported")
        self.assert_destination()
        self.assertIsNotNone(self.state.entries[0].request_admission)
        catalog = list_sqlite_conversations(self.target, self.root)
        self.assertEqual(
            catalog.sessions[0].modified_ns, self.source_file.stat().st_mtime_ns
        )
        destination_before = self.files(self.target)
        repeated_preview = self.transfer()
        self.assertEqual(repeated_preview.status, "already_present")
        self.assertEqual(repeated_preview.transfer_sha256, preview.transfer_sha256)
        self.assertEqual(
            self.transfer(preview.transfer_sha256, apply=True).status, "already_present"
        )
        self.assertEqual(self.files(self.target), destination_before)
        self.assertEqual(self.files(self.source), before)
        self.assertFalse((self.source / DATABASE).exists())

    def test_running_is_not_recovered_during_transfer(self) -> None:
        with ConversationStore(self.source, self.sid, self.root, create=False) as store:
            current = store.load()
            self.state = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "exchanges_consumed": current.exchanges_consumed + 1,
                    "entries": (
                        *current.entries[:-1],
                        ConversationEntry(text="PRIVATE", status="running"),
                    ),
                }
            )
            store.save(self.state)
        self.transfer(self.transfer().transfer_sha256, apply=True)
        self.assert_destination()

    def test_review_evidence_is_preserved(self) -> None:
        with ConversationStore(self.source, self.sid, self.root, create=False) as store:
            chat = ConversationController(store.load(), demo_cassette(), store.save)
            asyncio.run(chat.step())
            brief, recording = demo_inputs()
            chat.submit_review(
                ConversationReviewPacket(brief=brief, cassette=recording)
            )
            asyncio.run(chat.step())
            self.state = chat.state
        before = self.files(self.source)
        self.transfer(self.transfer().transfer_sha256, apply=True)
        self.assert_destination()
        self.assertEqual(self.files(self.source), before)

    def test_source_change_between_selection_and_apply_precedes_destination_writes(
        self,
    ) -> None:
        self.source_file.write_bytes(self.source_file.read_bytes() + b" ")
        preview = self.transfer()
        original = transfer_module._apply_transfer  # pyright: ignore[reportPrivateUsage]

        def change(
            source: ConversationMigration, plan: ConversationTransferPlan
        ) -> str:
            self.source_file.write_bytes(self.source_file.read_bytes()[:-1])
            return original(source, plan)

        with (
            patch.object(transfer_module, "_apply_transfer", change),
            self.assertRaisesRegex(ValueError, "source changed"),
        ):
            self.transfer(preview.transfer_sha256, apply=True)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_unrelated_destination_session_and_existing_empty_lock(self) -> None:
        unrelated = ConversationController.fresh(self.root, demo_cassette())
        with SQLiteConversationStore(
            self.target, unrelated.session_id, self.root
        ) as store:
            store.save(unrelated)
        before = self.files(self.target)
        plan = self.transfer()
        self.assertEqual(self.files(self.target), before)
        self.transfer(plan.transfer_sha256, apply=True)
        with SQLiteConversationStore(
            self.target, unrelated.session_id, self.root, create=False
        ) as store:
            self.assertEqual(store.load(), unrelated)
        other = self.root / "empty-lock"
        with ConversationStore(other, self.sid, self.root):
            pass
        self.target = other
        before = self.files(other)
        self.assertEqual(self.transfer().status, "planned")
        self.assertEqual(self.files(other), before)
        self.transfer(self.transfer().transfer_sha256, apply=True)
        self.assert_destination()

    def test_destination_conflict_and_missing_session_lock_fail_read_only(self) -> None:
        plan = self.transfer()
        self.transfer(plan.transfer_sha256, apply=True)
        with SQLiteConversationStore(
            self.target, self.sid, self.root, create=False
        ) as store:
            current = store.load()
            store.save(current.model_copy(update={"revision": current.revision + 1}))
        before = self.files(self.target)
        for apply in (False, True):
            with self.assertRaisesRegex(ValueError, "different session"):
                self.transfer(plan.transfer_sha256, apply=apply)
        self.assertEqual(self.files(self.target), before)
        (self.target / f"{self.sid}.lock").unlink()
        before = self.files(self.target)
        with self.assertRaisesRegex(ValueError, "lock is missing"):
            self.transfer()
        self.assertEqual(self.files(self.target), before)

    def test_hash_and_source_selection_reject_before_destination_writes(self) -> None:
        preview = self.transfer()
        for expected in (None, "bad", "0" * 64):
            with self.assertRaises(ValueError):
                self.transfer(expected, apply=True)
        self.source_file.write_bytes(self.source_file.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "selection changed"):
            self.transfer(preview.transfer_sha256, apply=True)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_identity_workspace_privacy_and_same_root_preflight(self) -> None:
        preview = self.transfer()
        replacement = self.root / "replacement"
        replacement.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "selection changed"):
            transfer_conversation(
                self.source,
                replacement,
                self.sid,
                self.root,
                expected_sha256=preview.transfer_sha256,
                apply=True,
            )
        with self.assertRaisesRegex(ValueError, "different roots"):
            transfer_conversation(self.source, self.source / ".", self.sid, self.root)
        with self.assertRaises(ValueError):
            transfer_conversation(self.source, self.target, self.sid, replacement)
        self.target.chmod(0o755)
        with self.assertRaises(ValueError):
            self.transfer()
        self.target.chmod(0o700)
        link = self.root / "link"
        link.symlink_to(self.target, target_is_directory=True)
        with self.assertRaises(OSError):
            transfer_conversation(self.source, link, self.sid, self.root)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_source_and_destination_locks_exclude_writers(self) -> None:
        preview = self.transfer()
        with (
            ConversationStore(self.source, self.sid, self.root, create=False),
            self.assertRaises(BlockingIOError),
        ):
            self.transfer(preview.transfer_sha256, apply=True)
        with ConversationStore(self.target, self.sid, self.root):
            for apply in (False, True):
                with self.assertRaises(BlockingIOError):
                    self.transfer(preview.transfer_sha256, apply=apply)
        self.assertFalse((self.target / DATABASE).exists())

    def test_constructor_identity_guard_precedes_metadata_creation(self) -> None:
        for target in (self.target, self.root / "missing"):
            with self.assertRaises((ValueError, FileNotFoundError)):
                SQLiteConversationStore(
                    target, self.sid, self.root, expected_root_identity=(0, 0)
                )
        self.assertFalse((self.root / "missing").exists())
        with self.assertRaises(ValueError):
            SQLiteConversationStore(self.target, self.sid, self.root, writable=False)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_destination_replaced_after_plan_before_open_rejects_without_artifacts(
        self,
    ) -> None:
        preview = self.transfer()
        original = transfer_module.SQLiteConversationStore

        def replace(*args: object, **kwargs: object) -> SQLiteConversationStore:
            self.target.rename(self.root / "old-target")
            self.target.mkdir(mode=0o700)
            return original(*args, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(transfer_module, "SQLiteConversationStore", replace),
            self.assertRaisesRegex(ValueError, "directory changed"),
        ):
            self.transfer(preview.transfer_sha256, apply=True)
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertEqual(list((self.root / "old-target").iterdir()), [])

    def test_source_change_inside_transaction_rolls_back_and_retries(self) -> None:
        with SQLiteConversationStore(self.target, self.sid, self.root):
            pass
        original_bytes = self.source_file.read_bytes() + b" "
        self.source_file.write_bytes(original_bytes)
        preview = self.transfer()
        original = sqlite_backend.conversation_transaction

        @contextmanager
        def change(db: sqlite3.Connection, *, write: bool = False) -> Generator[None]:
            with original(db, write=write):
                if write:
                    self.source_file.write_bytes(original_bytes[:-1])
                yield

        with (
            patch.object(sqlite_backend, "conversation_transaction", change),
            self.assertRaisesRegex(ValueError, "source changed"),
        ):
            self.transfer(preview.transfer_sha256, apply=True)
        self.assertEqual(
            len(list_sqlite_conversations(self.target, self.root).sessions), 0
        )
        self.source_file.write_bytes(original_bytes)
        self.assertEqual(
            self.transfer(preview.transfer_sha256, apply=True).status, "imported"
        )
        self.assert_destination()

    def test_source_directory_replaced_inside_transaction_rolls_back(self) -> None:
        with SQLiteConversationStore(self.target, self.sid, self.root):
            pass
        preview = self.transfer()
        original = sqlite_backend.conversation_transaction

        @contextmanager
        def replace(db: sqlite3.Connection, *, write: bool = False) -> Generator[None]:
            with original(db, write=write):
                if write:
                    old = self.root / "old-source"
                    self.source.rename(old)
                    shutil.copytree(old, self.source)
                yield

        with (
            patch.object(sqlite_backend, "conversation_transaction", replace),
            self.assertRaisesRegex(ValueError, "directory changed"),
        ):
            self.transfer(preview.transfer_sha256, apply=True)
        self.assertEqual(
            len(list_sqlite_conversations(self.target, self.root).sessions), 0
        )

    def test_lost_acknowledgment_retry_verifies_committed_copy(self) -> None:
        preview = self.transfer()
        original = SQLiteConversationStore.import_snapshot

        def lost_ack(
            store: SQLiteConversationStore, *args: object, **kwargs: object
        ) -> bool:
            original(store, *args, **kwargs)  # type: ignore[arg-type]
            raise OSError("lost acknowledgment")

        with (
            patch.object(SQLiteConversationStore, "import_snapshot", lost_ack),
            self.assertRaises(OSError),
        ):
            self.transfer(preview.transfer_sha256, apply=True)
        self.assertEqual(
            self.transfer(preview.transfer_sha256, apply=True).status, "already_present"
        )
        self.assert_destination()

    def test_process_crash_preview_does_not_recover_apply_does(self) -> None:
        unrelated = ConversationController.fresh(self.root, demo_cassette())
        with SQLiteConversationStore(
            self.target, unrelated.session_id, self.root
        ) as store:
            store.save(unrelated)
        preview = self.transfer()
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
from mos_eisley.run.conversation_transfer import transfer_conversation
original = backend.conversation_transaction
@contextmanager
def crash(db, *, write=False):
    with original(db, write=write):
        yield
        if write:
            db.execute("PRAGMA cache_size=1")
            db.execute("UPDATE sessions SET header=zeroblob(100000)")
            os._exit(77)
source, target, sid, workspace, selected = sys.argv[1:]
with patch.object(backend, "conversation_transaction", crash):
    transfer_conversation(Path(source), Path(target), sid, Path(workspace),
                          apply=True, expected_sha256=selected)
""",
                str(self.source),
                str(self.target),
                self.sid,
                str(self.root),
                preview.transfer_sha256,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(crashed.returncode, 77, crashed.stderr)
        self.assertTrue((self.target / (DATABASE + "-journal")).exists())
        before = self.files(self.target)
        with self.assertRaises(ValueError):
            self.transfer()
        self.assertEqual(self.files(self.target), before)
        self.assertEqual(
            self.transfer(preview.transfer_sha256, apply=True).status, "imported"
        )
        self.assert_destination()
        with SQLiteConversationStore(
            self.target, unrelated.session_id, self.root, create=False
        ) as store:
            self.assertEqual(store.load(), unrelated)

    def test_cli_preview_apply_retry_conflict_and_schema_errors_are_safe(self) -> None:
        command = [
            sys.executable,
            "-m",
            "mos_eisley.cli",
            "session-transfer",
            self.sid,
            "--storage",
            str(self.source),
            "--destination-storage",
            str(self.target),
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
        self.assertEqual(report["type"], "conversation.transfer")
        for status in ("imported", "already_present"):
            result = invoke("--apply", "--expected-sha256", report["transfer_sha256"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], status)
        with SQLiteConversationStore(
            self.target, self.sid, self.root, create=False
        ) as store:
            current = store.load()
            store.save(current.model_copy(update={"revision": current.revision + 1}))
        self.assertEqual(invoke().returncode, 2)
        self.source_file.write_bytes(b'{"PRIVATE": "bad source"}')
        failure = invoke()
        self.assertEqual(failure.returncode, 2)
        self.assertNotIn("PRIVATE", failure.stdout + failure.stderr)

    def test_receipt_rejects_wrong_hash(self) -> None:
        receipt = self.transfer().model_dump(mode="json")
        receipt["transfer_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            ConversationTransferReceipt.model_validate_json(json.dumps(receipt))
