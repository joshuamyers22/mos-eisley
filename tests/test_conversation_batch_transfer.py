"""Cross-root batch selection, partial success, bounded rechecks and retry tests."""

import asyncio
import json
import shutil
import subprocess
import sys
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
from mos_eisley.run import conversation_batch_migration as migration_module
from mos_eisley.run import conversation_batch_transfer as batch_module
from mos_eisley.run.conversation_batch_transfer import (
    BatchTransferError,
    BatchTransferReceipt,
    transfer_batch,
)
from mos_eisley.run.conversation_sqlite import (
    DATABASE,
    SQLiteConversationStore,
    list_sqlite_conversations,
)
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.conversation_transfer import (
    ConversationTransferReceipt,
    transfer_conversation,
)


class BatchTransferTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.target = self.root / "target"
        self.target.mkdir(mode=0o700)
        self.ids = tuple(f"{value:032x}" for value in (1, 2, 3))
        self.states: dict[str, ConversationState] = {}
        for index, sid in enumerate(self.ids):
            cassette = demo_cassette()
            state = ConversationController.fresh(self.root, cassette).model_copy(
                update={"session_id": sid}
            )
            with ConversationStore(self.source, sid, self.root) as store:
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

    def files(self, root: Path) -> dict[str, tuple[bytes, int]]:
        return {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.iterdir()
            if path.is_file()
        }

    def transfer(
        self, expected: str | None = None, *, apply: bool = False
    ) -> BatchTransferReceipt:
        return transfer_batch(
            self.source,
            self.target,
            self.ids,
            self.root,
            expected_sha256=expected,
            apply=apply,
        )

    def assert_destinations(self) -> None:
        for sid, state in self.states.items():
            with SQLiteConversationStore(
                self.target, sid, self.root, create=False, writable=False
            ) as store:
                self.assertEqual(canonical_bytes(store.load()), canonical_bytes(state))

    def test_preview_sorted_read_only_exact_metadata_and_apply_retry(self) -> None:
        before = self.files(self.source)
        preview = transfer_batch(
            self.source, self.target, tuple(reversed(self.ids)), self.root
        )
        self.assertEqual(preview.status, "planned")
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertEqual(
            tuple(entry.session_id for entry in preview.plan.sources.entries), self.ids
        )
        self.assertEqual(
            preview.plan.sources.source_bytes,
            sum(len(before[f"{sid}.json"][0]) for sid in self.ids),
        )
        self.assertEqual(preview.batch_sha256, digest(canonical_bytes(preview.plan)))
        self.assertEqual(
            preview, BatchTransferReceipt.model_validate_json(preview.model_dump_json())
        )
        self.assertNotIn("PRIVATE", preview.model_dump_json())
        applied = self.transfer(preview.batch_sha256, apply=True)
        self.assertEqual(
            (applied.status, applied.imported, applied.already_present),
            ("completed", 3, 0),
        )
        self.assert_destinations()
        destination = self.files(self.target)
        for apply in (False, True):
            result = self.transfer(preview.batch_sha256, apply=apply)
            self.assertEqual((result.imported, result.already_present), (0, 3))
            self.assertEqual(result.batch_sha256, preview.batch_sha256)
        self.assertEqual(self.files(self.source), before)
        self.assertEqual(self.files(self.target), destination)
        self.assertFalse((self.source / DATABASE).exists())

    def test_bad_ids_bounds_hash_and_changed_last_source_precede_destination_writes(
        self,
    ) -> None:
        preview = self.transfer()
        for ids in ((), (self.ids[0], self.ids[0]), ("PRIVATE",), self.ids * 11):
            with self.assertRaises(ValueError):
                transfer_batch(self.source, self.target, ids, self.root)
        for expected in (None, "PRIVATE", "0" * 64):
            with self.assertRaises(ValueError):
                self.transfer(expected, apply=True)
        last = self.source / f"{self.ids[-1]}.json"
        last.write_bytes(last.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "selection changed"):
            self.transfer(preview.batch_sha256, apply=True)
        last.write_bytes(b'{"PRIVATE": "bad source"}')
        with self.assertRaisesRegex(ValueError, "source preflight") as error:
            self.transfer()
        self.assertNotIn("PRIVATE", str(error.exception))
        self.assertEqual(list(self.target.iterdir()), [])

    def test_partial_failure_reports_prefix_and_retry_finishes(self) -> None:
        preview = self.transfer()
        original = batch_module.transfer_conversation

        def fail(
            source: Path, target: Path, sid: str, workspace: Path, **kwargs: object
        ) -> ConversationTransferReceipt:
            if sid == self.ids[1]:
                raise OSError("PRIVATE disk failure")
            return original(source, target, sid, workspace, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(batch_module, "transfer_conversation", fail),
            self.assertRaises(BatchTransferError) as caught,
        ):
            self.transfer(preview.batch_sha256, apply=True)
        stopped = caught.exception.receipt
        self.assertEqual(
            (stopped.status, stopped.imported, stopped.failed_session_id),
            ("stopped", 1, self.ids[1]),
        )
        self.assertEqual(stopped.failure, "storage_unavailable")
        self.assertNotIn("PRIVATE", str(caught.exception) + stopped.model_dump_json())
        self.assertEqual(
            len(list_sqlite_conversations(self.target, self.root).sessions), 1
        )
        retried = self.transfer(preview.batch_sha256, apply=True)
        self.assertEqual((retried.imported, retried.already_present), (2, 1))
        self.assert_destinations()

    def test_lost_commit_acknowledgment_is_resolved_on_retry(self) -> None:
        preview = self.transfer()
        original = batch_module.transfer_conversation

        def fail(
            source: Path, target: Path, sid: str, workspace: Path, **kwargs: object
        ) -> ConversationTransferReceipt:
            receipt = original(source, target, sid, workspace, **kwargs)  # type: ignore[arg-type]
            if sid == self.ids[1]:
                raise OSError("lost acknowledgment")
            return receipt

        with (
            patch.object(batch_module, "transfer_conversation", fail),
            self.assertRaises(BatchTransferError) as caught,
        ):
            self.transfer(preview.batch_sha256, apply=True)
        self.assertEqual(caught.exception.receipt.imported, 1)
        self.assertEqual(
            len(list_sqlite_conversations(self.target, self.root).sessions), 2
        )
        retried = self.transfer(preview.batch_sha256, apply=True)
        self.assertEqual((retried.imported, retried.already_present), (1, 2))
        self.assert_destinations()

    def test_conflict_preview_is_read_only_and_apply_retains_earlier_imports(
        self,
    ) -> None:
        preview = self.transfer()
        sid = self.ids[-1]
        with SQLiteConversationStore(self.target, sid, self.root) as store:
            conflicting = self.states[sid].model_copy(
                update={"revision": self.states[sid].revision + 1}
            )
            store.import_snapshot(conflicting, 1, validate_source=lambda: None)
        before = self.files(self.target)
        with self.assertRaises(BatchTransferError) as caught:
            self.transfer()
        self.assertEqual(len(caught.exception.receipt.receipts), 2)
        self.assertEqual(caught.exception.receipt.failed_session_id, sid)
        self.assertEqual(self.files(self.target), before)
        with self.assertRaises(BatchTransferError) as caught:
            self.transfer(preview.batch_sha256, apply=True)
        self.assertEqual(caught.exception.receipt.imported, 2)
        with SQLiteConversationStore(
            self.target, sid, self.root, create=False, writable=False
        ) as store:
            self.assertEqual(store.load(), conflicting)

    def test_byte_budget_preflight_and_recheck_growth_never_write_destination(
        self,
    ) -> None:
        first_size = (self.source / f"{self.ids[0]}.json").stat().st_size
        with (
            patch.object(migration_module, "MAX_BATCH_SOURCE_BYTES", first_size + 1),
            patch.object(
                batch_module,
                "inspect_transfer_destination",
                side_effect=AssertionError("destination touched"),
            ),
            self.assertRaisesRegex(ValueError, "source preflight"),
        ):
            self.transfer()
        preview = self.transfer()
        original = batch_module.transfer_conversation

        def grow(
            source: Path, target: Path, sid: str, workspace: Path, **kwargs: object
        ) -> ConversationTransferReceipt:
            selected = source / f"{sid}.json"
            self.assertEqual(kwargs["source_max_bytes"], selected.stat().st_size)
            selected.write_bytes(selected.read_bytes() + b" ")
            return original(source, target, sid, workspace, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(batch_module, "transfer_conversation", grow),
            self.assertRaises(BatchTransferError) as caught,
        ):
            self.transfer(preview.batch_sha256, apply=True)
        self.assertEqual(caught.exception.receipt.receipts, ())
        self.assertEqual(list(self.target.iterdir()), [])

    def test_both_roots_bound_to_hash_and_same_root_is_rejected(self) -> None:
        preview = self.transfer()
        for selected in (self.source, self.target):
            old = self.root / "old"
            selected.rename(old)
            shutil.copytree(old, selected)
            with self.assertRaisesRegex(ValueError, "selection changed"):
                self.transfer(preview.batch_sha256, apply=True)
            shutil.rmtree(selected)
            old.rename(selected)
        with self.assertRaises(ValueError):
            transfer_batch(self.source, self.source, self.ids, self.root)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_destination_replacement_between_sessions_stops_without_wrong_root_writes(
        self,
    ) -> None:
        preview = self.transfer()
        original = batch_module.transfer_conversation

        def replace(
            source: Path, target: Path, sid: str, workspace: Path, **kwargs: object
        ) -> ConversationTransferReceipt:
            if sid == self.ids[1]:
                target.rename(self.root / "old-target")
                target.mkdir(mode=0o700)
            return original(source, target, sid, workspace, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(batch_module, "transfer_conversation", replace),
            self.assertRaises(BatchTransferError) as caught,
        ):
            self.transfer(preview.batch_sha256, apply=True)
        self.assertEqual(caught.exception.receipt.imported, 1)
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertEqual(
            len(
                list_sqlite_conversations(self.root / "old-target", self.root).sessions
            ),
            1,
        )

    def test_source_replacement_between_sessions_stops_at_bound_identity(self) -> None:
        preview = self.transfer()
        original = batch_module.transfer_conversation

        def replace(
            source: Path, target: Path, sid: str, workspace: Path, **kwargs: object
        ) -> ConversationTransferReceipt:
            if sid == self.ids[1]:
                old = self.root / "old-source"
                source.rename(old)
                shutil.copytree(old, source)
            return original(source, target, sid, workspace, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(batch_module, "transfer_conversation", replace),
            self.assertRaises(BatchTransferError) as caught,
        ):
            self.transfer(preview.batch_sha256, apply=True)
        self.assertEqual(caught.exception.receipt.imported, 1)
        self.assertEqual(caught.exception.receipt.failed_session_id, self.ids[1])
        self.assertEqual(
            len(list_sqlite_conversations(self.target, self.root).sessions), 1
        )

    def test_destination_lock_keeps_prefix_and_source_lock_preflight_writes_nothing(
        self,
    ) -> None:
        preview = self.transfer()
        with (
            ConversationStore(self.source, self.ids[-1], self.root, create=False),
            self.assertRaisesRegex(ValueError, "source preflight"),
        ):
            self.transfer(preview.batch_sha256, apply=True)
        self.assertEqual(list(self.target.iterdir()), [])
        with (
            ConversationStore(self.target, self.ids[1], self.root),
            self.assertRaises(BatchTransferError) as caught,
        ):
            self.transfer(preview.batch_sha256, apply=True)
        self.assertEqual(caught.exception.receipt.imported, 1)
        self.assertEqual(caught.exception.receipt.failure, "storage_unavailable")
        self.assertEqual(self.transfer(preview.batch_sha256, apply=True).imported, 2)

    def test_receipt_rejects_wrong_hash_counts_prefix_mode_and_destination(
        self,
    ) -> None:
        preview = self.transfer()
        changes: tuple[dict[str, object], ...] = (
            {"batch_sha256": "0" * 64},
            {"imported": 1},
            {"receipts": list(reversed(preview.model_dump(mode="json")["receipts"]))},
            {"status": "completed"},
            {"failed_session_id": self.ids[0]},
        )
        for change in changes:
            with self.assertRaises(ValueError):
                BatchTransferReceipt.model_validate_json(
                    json.dumps({**preview.model_dump(mode="json"), **change})
                )
        payload = preview.model_dump(mode="json")
        payload["receipts"][0]["plan"]["destination"]["path"] = str(self.root / "other")
        payload["receipts"][0]["transfer_sha256"] = digest(
            canonical_bytes(
                preview.receipts[0].plan.model_copy(
                    update={
                        "destination": preview.plan.destination.model_copy(
                            update={"path": str(self.root / "other")}
                        )
                    }
                )
            )
        )
        with self.assertRaises(ValueError):
            BatchTransferReceipt.model_validate_json(json.dumps(payload))

    def test_crash_after_earlier_commit_preview_refuses_journal_retry_recovers(
        self,
    ) -> None:
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
from mos_eisley.run import conversation_batch_transfer as batch
original_transaction = backend.conversation_transaction
original_transfer = batch.transfer_conversation
source, target, workspace, selected, *ids = sys.argv[1:]
@contextmanager
def crash(db, *, write=False):
    with original_transaction(db, write=write):
        yield
        if write:
            db.execute("PRAGMA cache_size=1")
            db.execute("UPDATE sessions SET header=zeroblob(100000)")
            os._exit(77)
def transfer(source, target, sid, workspace, **kwargs):
    if sid == ids[1]:
        with patch.object(backend, "conversation_transaction", crash):
            return original_transfer(source, target, sid, workspace, **kwargs)
    return original_transfer(source, target, sid, workspace, **kwargs)
with patch.object(batch, "transfer_conversation", transfer):
    batch.transfer_batch(Path(source), Path(target), tuple(ids), Path(workspace),
                         expected_sha256=selected, apply=True)
""",
                str(self.source),
                str(self.target),
                str(self.root),
                preview.batch_sha256,
                *self.ids,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(crashed.returncode, 77, crashed.stderr)
        self.assertTrue((self.target / (DATABASE + "-journal")).exists())
        before = self.files(self.target)
        with self.assertRaises(BatchTransferError):
            self.transfer()
        self.assertEqual(self.files(self.target), before)
        retried = self.transfer(preview.batch_sha256, apply=True)
        self.assertEqual((retried.imported, retried.already_present), (2, 1))
        self.assert_destinations()

    def test_cli_preview_mixed_copy_retry_partial_result_and_safe_source_failure(
        self,
    ) -> None:
        command = [
            sys.executable,
            "-m",
            "mos_eisley.cli",
            "session-transfer-batch",
            *self.ids,
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
        result = json.loads(preview.stdout)
        self.assertEqual(result["type"], "conversation.transfer_batch")
        single = transfer_conversation(self.source, self.target, self.ids[0], self.root)
        transfer_conversation(
            self.source,
            self.target,
            self.ids[0],
            self.root,
            expected_sha256=single.transfer_sha256,
            apply=True,
        )
        applied = invoke("--apply", "--expected-sha256", result["batch_sha256"])
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(json.loads(applied.stdout)["imported"], 2)
        self.assertEqual(json.loads(applied.stdout)["already_present"], 1)
        repeated = invoke("--apply", "--expected-sha256", result["batch_sha256"])
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout)["already_present"], 3)
        with SQLiteConversationStore(
            self.target, self.ids[-1], self.root, create=False
        ) as store:
            state = store.load()
            store.save(state.model_copy(update={"revision": state.revision + 1}))
        conflict = invoke("--apply", "--expected-sha256", result["batch_sha256"])
        self.assertEqual(conflict.returncode, 2, conflict.stderr)
        self.assertEqual(json.loads(conflict.stdout)["already_present"], 2)
        self.assertEqual(json.loads(conflict.stdout)["failed_session_id"], self.ids[-1])
        (self.source / f"{self.ids[-1]}.json").write_bytes(b'{"PRIVATE": "bad source"}')
        failure = invoke()
        self.assertEqual(failure.returncode, 2)
        self.assertNotIn("PRIVATE", failure.stdout + failure.stderr)
