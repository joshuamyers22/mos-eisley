"""Reverse migration preserves full state and publishes only validated JSON."""

import asyncio
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation import ConversationController, ConversationEntry
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.demo import demo_inputs
from mos_eisley.run import conversation_export as export_module
from mos_eisley.run import conversation_store as json_backend
from mos_eisley.run.conversation_export import (
    ConversationExportReceipt,
    export_conversation,
)
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore
from mos_eisley.run.conversation_transfer import transfer_conversation


class ConversationExportTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.target = self.root / "target"
        self.target.mkdir(mode=0o700)
        cassette = demo_cassette()
        state = ConversationController.fresh(self.root, cassette)
        self.sid = state.session_id
        with SQLiteConversationStore(self.source, self.sid, self.root) as store:
            store.save(state)
            chat = ConversationController(state, cassette, store.save)
            chat.refresh_memory(None, cassette)
            chat.submit(DEMO_PROMPTS[0])
            asyncio.run(chat.step())
            chat.submit(DEMO_PROMPTS[1])
            self.state = chat.state
            self.modified_ns = store.inspect_snapshot()[1]
        self.destination = self.target / f"{self.sid}.json"

    def export(
        self, expected: str | None = None, *, apply: bool = False
    ) -> ConversationExportReceipt:
        return export_conversation(
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
        with ConversationStore(self.target, self.sid, self.root, create=False) as store:
            self.assertEqual(canonical_bytes(store.load()), canonical_bytes(self.state))

    def test_preview_apply_retry_preserves_exact_state_timestamp_and_source_database(
        self,
    ) -> None:
        before = self.files(self.source)
        preview = self.export()
        self.assertEqual(preview.status, "planned")
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertEqual(preview.export_sha256, digest(canonical_bytes(preview.plan)))
        self.assertNotIn(DEMO_PROMPTS[0], preview.model_dump_json())
        self.assertEqual(
            preview,
            ConversationExportReceipt.model_validate_json(preview.model_dump_json()),
        )
        self.assertEqual(
            self.export(preview.export_sha256, apply=True).status, "exported"
        )
        self.assert_destination()
        self.assertEqual(self.destination.stat().st_mtime_ns, self.modified_ns)
        self.assertEqual(self.destination.stat().st_size, preview.plan.snapshot_bytes)
        target = self.files(self.target)
        for apply in (False, True):
            result = self.export(preview.export_sha256, apply=apply)
            self.assertEqual(result.status, "already_present")
            self.assertEqual(result.export_sha256, preview.export_sha256)
        self.assertEqual(self.files(self.target), target)
        self.assertEqual(self.files(self.source), before)
        self.assertFalse((self.target / DATABASE).exists())

    def test_review_and_admission_round_trip_back_to_sqlite(self) -> None:
        with SQLiteConversationStore(
            self.source, self.sid, self.root, create=False
        ) as store:
            chat = ConversationController(store.load(), demo_cassette(), store.save)
            asyncio.run(chat.step())
            brief, recording = demo_inputs()
            chat.submit_review(
                ConversationReviewPacket(brief=brief, cassette=recording)
            )
            asyncio.run(chat.step())
            self.state = chat.state
        self.export(self.export().export_sha256, apply=True)
        self.assert_destination()
        final = self.root / "round-trip"
        final.mkdir(mode=0o700)
        selected = transfer_conversation(self.target, final, self.sid, self.root)
        transfer_conversation(
            self.target,
            final,
            self.sid,
            self.root,
            expected_sha256=selected.transfer_sha256,
            apply=True,
        )
        with SQLiteConversationStore(final, self.sid, self.root, create=False) as store:
            self.assertEqual(canonical_bytes(store.load()), canonical_bytes(self.state))

    def test_running_entries_are_not_recovered_or_retried(self) -> None:
        with SQLiteConversationStore(
            self.source, self.sid, self.root, create=False
        ) as store:
            state = store.load()
            self.state = state.model_copy(
                update={
                    "revision": state.revision + 1,
                    "exchanges_consumed": state.exchanges_consumed + 1,
                    "entries": (
                        *state.entries[:-1],
                        ConversationEntry(text="PRIVATE", status="running"),
                    ),
                }
            )
            store.save(self.state)
        self.export(self.export().export_sha256, apply=True)
        self.assert_destination()

    def test_invalid_hash_changed_source_and_wrong_workspace_precede_destination_writes(
        self,
    ) -> None:
        preview = self.export()
        for expected in (None, "PRIVATE", "0" * 64):
            with self.assertRaises(ValueError):
                self.export(expected, apply=True)
        with self.assertRaises(ValueError):
            export_conversation(self.source, self.target, self.sid, self.target)
        with SQLiteConversationStore(
            self.source, self.sid, self.root, create=False
        ) as store:
            state = store.load()
            store.save(state.model_copy(update={"revision": state.revision + 1}))
        with self.assertRaisesRegex(ValueError, "selection changed"):
            self.export(preview.export_sha256, apply=True)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_advanced_or_invalid_destination_is_never_overwritten(self) -> None:
        preview = self.export()
        self.export(preview.export_sha256, apply=True)
        with ConversationStore(self.target, self.sid, self.root, create=False) as store:
            state = store.load()
            store.save(state.model_copy(update={"revision": state.revision + 1}))
        for contents in (self.destination.read_bytes(), b'{"PRIVATE": "invalid"}'):
            self.destination.write_bytes(contents)
            before = self.files(self.target)
            for apply in (False, True):
                with self.assertRaises(ValueError):
                    self.export(preview.export_sha256, apply=apply)
            self.assertEqual(self.files(self.target), before)

    def test_locks_and_missing_destination_lock(self) -> None:
        preview = self.export()
        with (
            SQLiteConversationStore(self.source, self.sid, self.root, create=False),
            self.assertRaises(BlockingIOError),
        ):
            self.export(preview.export_sha256, apply=True)
        self.assertEqual(list(self.target.iterdir()), [])
        with ConversationStore(self.target, self.sid, self.root):
            for apply in (False, True):
                with self.assertRaises(BlockingIOError):
                    self.export(preview.export_sha256, apply=apply)
        self.assertEqual(self.export().status, "planned")
        self.export(preview.export_sha256, apply=True)
        (self.target / f"{self.sid}.lock").unlink()
        before = self.files(self.target)
        with self.assertRaisesRegex(ValueError, "lock is missing"):
            self.export()
        self.assertEqual(self.files(self.target), before)

    def test_root_identity_privacy_same_root_and_symlink_guards(self) -> None:
        preview = self.export()
        for root in (self.source, self.target):
            old = self.root / "old"
            root.rename(old)
            shutil.copytree(old, root)
            with self.assertRaisesRegex(ValueError, "selection changed"):
                self.export(preview.export_sha256, apply=True)
            shutil.rmtree(root)
            old.rename(root)
        with self.assertRaisesRegex(ValueError, "different storage"):
            export_conversation(self.source, self.source, self.sid, self.root)
        self.target.chmod(0o755)
        with self.assertRaises(ValueError):
            self.export()
        self.target.chmod(0o700)
        linked = self.root / "link"
        linked.symlink_to(self.target, target_is_directory=True)
        with self.assertRaises(OSError):
            export_conversation(self.source, linked, self.sid, self.root)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_destination_replaced_before_open_has_no_metadata_writes(self) -> None:
        preview = self.export()
        original = export_module.ConversationStore

        def replace(*args: object, **kwargs: object) -> ConversationStore:
            self.target.rename(self.root / "old-target")
            self.target.mkdir(mode=0o700)
            return original(*args, **kwargs)  # type: ignore[arg-type]

        with (
            patch.object(export_module, "ConversationStore", replace),
            self.assertRaisesRegex(ValueError, "directory changed"),
        ):
            self.export(preview.export_sha256, apply=True)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_source_directory_replaced_before_publication_leaves_no_snapshot(
        self,
    ) -> None:
        preview = self.export()
        original = os.fsync

        def replace(fd: int) -> None:
            original(fd)
            if stat.S_ISREG(os.fstat(fd).st_mode):
                old = self.root / "old-source"
                self.source.rename(old)
                shutil.copytree(old, self.source)

        with (
            patch.object(json_backend.os, "fsync", replace),
            self.assertRaisesRegex(ValueError, "directory changed"),
        ):
            self.export(preview.export_sha256, apply=True)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.target.glob("*.tmp")), [])

    def test_source_change_at_final_validation_leaves_no_snapshot(self) -> None:
        preview = self.export()
        original = SQLiteConversationStore.inspect_snapshot
        count = 0

        def changed(store: SQLiteConversationStore) -> tuple[ConversationSnapshot, int]:
            nonlocal count
            snapshot, timestamp = original(store)
            count += 1
            if count == 2:
                state = snapshot.state.model_copy(
                    update={"revision": snapshot.state.revision + 1}
                )
                snapshot = ConversationSnapshot(
                    state=state, sha256=digest(canonical_bytes(state))
                )
            return snapshot, timestamp

        with (
            patch.object(SQLiteConversationStore, "inspect_snapshot", changed),
            self.assertRaisesRegex(ValueError, "source changed"),
        ):
            self.export(preview.export_sha256, apply=True)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.target.glob("*.tmp")), [])

    def test_destination_appearing_during_write_is_retained(self) -> None:
        preview = self.export()
        original = os.fsync
        conflicting = b"PRIVATE new destination"

        def appear(fd: int) -> None:
            original(fd)
            if stat.S_ISREG(os.fstat(fd).st_mode):
                self.destination.write_bytes(conflicting)
                self.destination.chmod(0o600)

        with (
            patch.object(json_backend.os, "fsync", appear),
            self.assertRaisesRegex(ValueError, "appeared during export"),
        ):
            self.export(preview.export_sha256, apply=True)
        self.assertEqual(self.destination.read_bytes(), conflicting)
        self.assertEqual(list(self.target.glob("*.tmp")), [])

    def test_file_sync_failure_cleans_temporary_and_directory_sync_retry_verifies_copy(
        self,
    ) -> None:
        preview = self.export()
        with (
            patch.object(json_backend.os, "fsync", side_effect=OSError("disk full")),
            self.assertRaises(OSError),
        ):
            self.export(preview.export_sha256, apply=True)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.target.glob("*.tmp")), [])
        original = os.fsync

        def fail_directory(fd: int) -> None:
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("directory sync failed")
            original(fd)

        with (
            patch.object(json_backend.os, "fsync", fail_directory),
            self.assertRaises(OSError),
        ):
            self.export(preview.export_sha256, apply=True)
        self.assert_destination()
        with patch.object(json_backend.os, "fsync", wraps=original) as synced:
            self.assertEqual(
                self.export(preview.export_sha256, apply=True).status, "already_present"
            )
        self.assertEqual(synced.call_count, 1)

    def test_process_exit_before_and_after_publication_retries_safely(self) -> None:
        preview = self.export()
        before = self.files(self.source)
        for boundary in ("before", "after"):
            crashed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    """
import os, sys
from pathlib import Path
from unittest.mock import patch
from mos_eisley.run import conversation_store as backend
from mos_eisley.run.conversation_export import export_conversation
source, target, sid, workspace, selected, boundary = sys.argv[1:]
original = os.replace
def crash(*args, **kwargs):
    if boundary == "after":
        original(*args, **kwargs)
    os._exit(77)
with patch.object(backend.os, "replace", crash):
    export_conversation(Path(source), Path(target), sid, Path(workspace),
                        expected_sha256=selected, apply=True)
""",
                    str(self.source),
                    str(self.target),
                    self.sid,
                    str(self.root),
                    preview.export_sha256,
                    boundary,
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(crashed.returncode, 77, crashed.stderr)
            self.assertEqual(self.destination.exists(), boundary == "after")
            expected = "already_present" if boundary == "after" else "planned"
            self.assertEqual(self.export().status, expected)
        self.assertEqual(
            self.export(preview.export_sha256, apply=True).status, "already_present"
        )
        self.assert_destination()
        self.assertEqual(self.files(self.source), before)

    def test_hot_source_journal_is_never_recovered_by_export(self) -> None:
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
            with self.assertRaises(ValueError):
                self.export(preview.export_sha256, apply=apply)
        self.assertEqual(self.files(self.source), before)
        self.assertEqual(list(self.target.iterdir()), [])
        with SQLiteConversationStore(
            self.source, self.sid, self.root, create=False
        ) as store:
            self.assertEqual(store.load(), self.state)
        self.assertEqual(
            self.export(preview.export_sha256, apply=True).status, "exported"
        )

    def test_cli_preview_apply_retry_and_safe_schema_failure(self) -> None:
        command = [
            sys.executable,
            "-m",
            "mos_eisley.cli",
            "session-export",
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
        result = json.loads(preview.stdout)
        self.assertEqual(result["type"], "conversation.export")
        for status in ("exported", "already_present"):
            applied = invoke("--apply", "--expected-sha256", result["export_sha256"])
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(json.loads(applied.stdout)["status"], status)
        self.destination.write_bytes(b'{"PRIVATE": "invalid source"}')
        failed = invoke()
        self.assertEqual(failed.returncode, 2)
        self.assertNotIn("PRIVATE", failed.stdout + failed.stderr)

    def test_receipt_rejects_modified_hash(self) -> None:
        payload = self.export().model_dump(mode="json")
        payload["export_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            ConversationExportReceipt.model_validate_json(json.dumps(payload))
