"""Bounded batch reverse migration and safe partial-result/retry behavior."""

import asyncio
import json
import sqlite3
import subprocess
import sys
import weakref
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
from mos_eisley.run import conversation_batch_export as batch_module
from mos_eisley.run.conversation_batch_export import (
    BatchExportError,
    BatchExportPlan,
    BatchExportReceipt,
    export_batch,
)
from mos_eisley.run.conversation_export import ConversationExportReceipt
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore


class BatchExportTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.target = self.source
        self.ids = tuple(f"{n:032x}" for n in (1, 2, 3))
        self.states: dict[str, ConversationState] = {}
        for index, sid in enumerate(self.ids):
            cassette = demo_cassette()
            state = ConversationController.fresh(self.root, cassette).model_copy(
                update={"session_id": sid}
            )
            with SQLiteConversationStore(self.source, sid, self.root) as store:
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
                                    text="PRIVATE running", status="running"
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

    def export(
        self, expected: str | None = None, *, apply: bool = False
    ) -> BatchExportReceipt:
        return export_batch(
            self.source,
            self.target,
            self.ids,
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

    def assert_copies(self) -> None:
        for sid, state in self.states.items():
            with ConversationStore(self.target, sid, self.root, create=False) as store:
                self.assertEqual(canonical_bytes(store.load()), canonical_bytes(state))

    def test_same_and_cross_root_preview_apply_retry_preserve_state_and_sources(
        self,
    ) -> None:
        before = self.files(self.source)
        for different in (False, True):
            if different:
                self.target = self.root / "other"
                self.target.mkdir(mode=0o700)
            target_before = self.files(self.target)
            preview = export_batch(
                self.source, self.target, tuple(reversed(self.ids)), self.root
            )
            self.assertEqual(preview.status, "planned")
            self.assertEqual(
                tuple(entry.session_id for entry in preview.plan.entries), self.ids
            )
            self.assertTrue(
                all(
                    entry.schema_version == (1 if different else 2)
                    for entry in preview.plan.entries
                )
            )
            self.assertEqual(
                preview.plan.output_bytes,
                sum(entry.snapshot_bytes for entry in preview.plan.entries),
            )
            self.assertEqual(
                preview.batch_sha256, digest(canonical_bytes(preview.plan))
            )
            self.assertEqual(
                preview,
                BatchExportReceipt.model_validate_json(preview.model_dump_json()),
            )
            self.assertNotIn("PRIVATE", preview.model_dump_json())
            self.assertEqual(self.files(self.target), target_before)
            self.assertEqual(self.export(preview.batch_sha256, apply=True).exported, 3)
            self.assert_copies()
            after = self.files(self.target)
            for apply in (False, True):
                result = self.export(preview.batch_sha256, apply=apply)
                self.assertEqual((result.exported, result.already_present), (0, 3))
            self.assertEqual(self.files(self.target), after)
        source_after = self.files(self.source)
        self.assertEqual({name: source_after[name] for name in before}, before)

    def test_bad_selection_hash_and_changed_last_source_precede_json_publication(
        self,
    ) -> None:
        preview = self.export()
        for ids in ((), (self.ids[0], self.ids[0]), ("PRIVATE",), self.ids * 11):
            with self.assertRaises(ValueError):
                export_batch(self.source, self.target, ids, self.root)
        for expected in (None, "PRIVATE", "0" * 64):
            with self.assertRaises(ValueError):
                self.export(expected, apply=True)
        with SQLiteConversationStore(
            self.source, self.ids[-1], self.root, create=False
        ) as store:
            state = store.load()
            store.save(state.model_copy(update={"revision": state.revision + 1}))
        with self.assertRaisesRegex(ValueError, "selection changed"):
            self.export(preview.batch_sha256, apply=True)
        with sqlite3.connect(self.source / DATABASE) as db:
            db.execute(
                "UPDATE sessions SET header=? WHERE sid=?",
                (b"PRIVATE corrupt", self.ids[-1]),
            )
        with self.assertRaisesRegex(ValueError, "source preflight") as caught:
            self.export(preview.batch_sha256, apply=True)
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assertEqual(list(self.target.glob("*.json")), [])

    def test_output_budget_rejects_next_session_before_full_decode(self) -> None:
        first_size = self.export().plan.entries[0].snapshot_bytes
        decoded: list[str] = []
        original = SQLiteConversationStore._load  # pyright: ignore[reportPrivateUsage]

        def load(
            store: SQLiteConversationStore, db: sqlite3.Connection
        ) -> ConversationSnapshot:
            decoded.append(store.session_id)
            return original(store, db)

        with (
            patch.object(batch_module, "MAX_EXPORT_BYTES", first_size + 1),
            patch.object(SQLiteConversationStore, "_load", load),
            patch.object(
                batch_module,
                "export_conversation",
                side_effect=AssertionError("destination accessed"),
            ),
            self.assertRaisesRegex(ValueError, "source preflight"),
        ):
            self.export()
        self.assertEqual(decoded, [self.ids[0]])
        self.assertEqual(list(self.target.glob("*.json")), [])
        with SQLiteConversationStore(
            self.source, self.ids[0], self.root, create=False, writable=False
        ) as store:
            for limit in (0, -1, True, 32_000_001):
                with self.assertRaises(ValueError):
                    store.inspect_snapshot(snapshot_max_bytes=limit)

    def test_source_snapshots_are_released_between_selected_sessions(self) -> None:
        refs: list[weakref.ReferenceType[ConversationSnapshot]] = []
        original = SQLiteConversationStore.inspect_snapshot

        def inspect(
            store: SQLiteConversationStore, **kwargs: int
        ) -> tuple[ConversationSnapshot, int]:
            self.assertTrue(all(ref() is None for ref in refs))
            result = original(store, **kwargs)
            refs.append(weakref.ref(result[0]))
            return result

        with patch.object(SQLiteConversationStore, "inspect_snapshot", inspect):
            self.export()
        self.assertTrue(all(ref() is None for ref in refs))

    def test_source_growth_after_preflight_uses_selected_output_limit(self) -> None:
        preview = self.export()
        original = batch_module.export_conversation

        def grow(
            source: Path, target: Path, sid: str, workspace: Path, **kwargs: object
        ) -> ConversationExportReceipt:
            self.assertEqual(
                kwargs["snapshot_max_bytes"], preview.plan.entries[0].snapshot_bytes
            )
            with SQLiteConversationStore(source, sid, workspace, create=False) as store:
                state = store.load()
                store.save(
                    state.model_copy(
                        update={
                            "revision": state.revision + 1,
                            "entries": (
                                *state.entries,
                                ConversationEntry(text="extra queued text"),
                            ),
                        }
                    )
                )
            return original(source, target, sid, workspace, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(batch_module, "export_conversation", grow),
            self.assertRaises(BatchExportError) as caught,
        ):
            self.export(preview.batch_sha256, apply=True)
        self.assertEqual(caught.exception.receipt.receipts, ())
        self.assertEqual(list(self.target.glob("*.json")), [])

    def test_partial_failure_keeps_prefix_and_retry_completes_remaining_exports(
        self,
    ) -> None:
        preview = self.export()
        original = batch_module.export_conversation

        def fail(
            source: Path, target: Path, sid: str, workspace: Path, **kwargs: object
        ) -> ConversationExportReceipt:
            if sid == self.ids[1]:
                raise OSError("PRIVATE disk failure")
            return original(source, target, sid, workspace, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(batch_module, "export_conversation", fail),
            self.assertRaises(BatchExportError) as caught,
        ):
            self.export(preview.batch_sha256, apply=True)
        receipt = caught.exception.receipt
        self.assertEqual(
            (receipt.exported, receipt.failed_session_id), (1, self.ids[1])
        )
        self.assertEqual(receipt.failure, "storage_unavailable")
        self.assertNotIn("PRIVATE", receipt.model_dump_json() + str(caught.exception))
        retried = self.export(preview.batch_sha256, apply=True)
        self.assertEqual((retried.exported, retried.already_present), (2, 1))
        self.assert_copies()

    def test_lost_acknowledgment_is_resolved_by_verifying_the_copy(self) -> None:
        preview = self.export()
        original = batch_module.export_conversation

        def fail(
            source: Path, target: Path, sid: str, workspace: Path, **kwargs: object
        ) -> ConversationExportReceipt:
            result = original(source, target, sid, workspace, **kwargs)  # type: ignore[arg-type]
            if sid == self.ids[1]:
                raise OSError("lost acknowledgment")
            return result

        with (
            patch.object(batch_module, "export_conversation", fail),
            self.assertRaises(BatchExportError) as caught,
        ):
            self.export(preview.batch_sha256, apply=True)
        self.assertEqual(caught.exception.receipt.exported, 1)
        self.assertEqual(len(list(self.target.glob("*.json"))), 2)
        result = self.export(preview.batch_sha256, apply=True)
        self.assertEqual((result.exported, result.already_present), (1, 2))
        self.assert_copies()

    def test_last_conflict_has_read_only_preview_and_apply_reports_earlier_copies(
        self,
    ) -> None:
        preview = self.export()
        path = self.target / f"{self.ids[-1]}.json"
        state = self.states[self.ids[-1]].model_copy(
            update={"revision": self.states[self.ids[-1]].revision + 1}
        )
        path.write_bytes(
            canonical_bytes(
                ConversationSnapshot(state=state, sha256=digest(canonical_bytes(state)))
            )
        )
        path.chmod(0o600)
        before = self.files(self.target)
        with self.assertRaises(BatchExportError) as caught:
            self.export()
        self.assertEqual(len(caught.exception.receipt.receipts), 2)
        self.assertEqual(self.files(self.target), before)
        with self.assertRaises(BatchExportError) as caught:
            self.export(preview.batch_sha256, apply=True)
        self.assertEqual(caught.exception.receipt.exported, 2)
        self.assertEqual(self.files(self.target)[path.name], before[path.name])

    def test_root_replacement_between_exports_keeps_prefix_and_rejects_new_root(
        self,
    ) -> None:
        self.target = self.root / "target"
        self.target.mkdir(mode=0o700)
        preview = self.export()
        original = batch_module.export_conversation

        def replace(
            source: Path, target: Path, sid: str, workspace: Path, **kwargs: object
        ) -> ConversationExportReceipt:
            if sid == self.ids[1]:
                target.rename(self.root / "old-target")
                target.mkdir(mode=0o700)
            return original(source, target, sid, workspace, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(batch_module, "export_conversation", replace),
            self.assertRaises(BatchExportError) as caught,
        ):
            self.export(preview.batch_sha256, apply=True)
        self.assertEqual(caught.exception.receipt.exported, 1)
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertTrue((self.root / "old-target" / f"{self.ids[0]}.json").exists())

    def test_source_lock_and_wrong_workspace_fail_before_any_json_writes(self) -> None:
        preview = self.export()
        with (
            ConversationStore(self.source, self.ids[-1], self.root, create=False),
            self.assertRaisesRegex(ValueError, "source preflight"),
        ):
            self.export(preview.batch_sha256, apply=True)
        with self.assertRaisesRegex(ValueError, "source preflight"):
            export_batch(self.source, self.target, self.ids, self.source)
        self.assertEqual(list(self.target.glob("*.json")), [])

    def test_plan_and_receipt_reject_changed_totals_counts_prefix_and_locations(
        self,
    ) -> None:
        preview = self.export()
        changes: tuple[dict[str, object], ...] = (
            {"batch_sha256": "0" * 64},
            {"exported": 1},
            {"status": "completed"},
            {"receipts": list(reversed(preview.model_dump(mode="json")["receipts"]))},
        )
        for change in changes:
            with self.assertRaises(ValueError):
                BatchExportReceipt.model_validate_json(
                    json.dumps({**preview.model_dump(mode="json"), **change})
                )
        plan = preview.plan.model_dump(mode="json")
        plan["output_bytes"] += 1
        with self.assertRaises(ValueError):
            BatchExportPlan.model_validate_json(json.dumps(plan))
        plan = preview.plan.model_dump(mode="json")
        plan["entries"][1]["source"]["path"] += "/other"
        with self.assertRaises(ValueError):
            BatchExportPlan.model_validate_json(json.dumps(plan))

    def test_maximum_32_session_selection_exports_successfully(self) -> None:
        ids = tuple(f"{n:032x}" for n in range(1, 33))
        for sid in ids[3:]:
            state = ConversationController.fresh(self.root, demo_cassette()).model_copy(
                update={"session_id": sid}
            )
            with SQLiteConversationStore(self.source, sid, self.root) as store:
                store.save(state)
        preview = export_batch(self.source, self.target, ids, self.root)
        result = export_batch(
            self.source,
            self.target,
            ids,
            self.root,
            expected_sha256=preview.batch_sha256,
            apply=True,
        )
        self.assertEqual(result.exported, 32)
        self.assertEqual(len(list(self.target.glob("*.json"))), 32)

    def test_process_crash_after_second_publication_retry_verifies_prefix(self) -> None:
        preview = self.export()
        before = self.files(self.source)
        crashed = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.run import conversation_store as backend
from mos_eisley.run.conversation_batch_export import export_batch
source, target, workspace, selected, *ids = sys.argv[1:]
original = os.replace
count = 0
def crash(*args, **kwargs):
    global count
    original(*args, **kwargs)
    count += 1
    if count == 2:
        os._exit(77)
with patch.object(backend.os, "replace", crash):
    export_batch(Path(source), Path(target), tuple(ids), Path(workspace),
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
        result = self.export(preview.batch_sha256, apply=True)
        self.assertEqual((result.exported, result.already_present), (1, 2))
        self.assert_copies()
        after = self.files(self.source)
        self.assertEqual({name: after[name] for name in before}, before)

    def test_hot_source_journal_blocks_entire_batch_without_recovery(self) -> None:
        preview = self.export()
        crashed = subprocess.run(
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
                str(self.source / DATABASE),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(crashed.returncode, 77, crashed.stderr)
        before = self.files(self.source)
        self.assertIn(DATABASE + "-journal", before)
        for apply in (False, True):
            with self.assertRaisesRegex(ValueError, "source preflight"):
                self.export(preview.batch_sha256, apply=apply)
        self.assertEqual(self.files(self.source), before)

    def test_cli_default_preview_apply_retry_partial_conflict_and_safe_failure(
        self,
    ) -> None:
        command = [
            sys.executable,
            "-m",
            "mos_eisley.cli",
            "session-export-batch",
            *self.ids,
            "--storage",
            str(self.source),
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
        receipt = json.loads(preview.stdout)
        self.assertEqual(receipt["type"], "conversation.export_batch")
        for count in (3, 0):
            result = invoke("--apply", "--expected-sha256", receipt["batch_sha256"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["exported"], count)
        with ConversationStore(
            self.source, self.ids[-1], self.root, create=False
        ) as store:
            state = store.load()
            store.save(state.model_copy(update={"revision": state.revision + 1}))
        conflict = invoke("--apply", "--expected-sha256", receipt["batch_sha256"])
        self.assertEqual(conflict.returncode, 2, conflict.stderr)
        self.assertEqual(json.loads(conflict.stdout)["already_present"], 2)
        self.assertEqual(json.loads(conflict.stdout)["failed_session_id"], self.ids[-1])
        with sqlite3.connect(self.source / DATABASE) as db:
            db.execute(
                "UPDATE sessions SET header=? WHERE sid=?",
                (b"PRIVATE corrupt", self.ids[-1]),
            )
        failure = invoke()
        self.assertEqual(failure.returncode, 2)
        self.assertNotIn("PRIVATE", failure.stdout + failure.stderr)
