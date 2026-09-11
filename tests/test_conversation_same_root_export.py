"""Shared-lock SQLite export, versioned plans and independent backend copies."""

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

from mos_eisley.conversation import ConversationController
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run import conversation_store as json_backend
from mos_eisley.run.conversation_export import (
    ConversationExportPlan,
    ConversationExportReceipt,
    export_conversation,
)
from mos_eisley.run.conversation_migration import ConversationMigration
from mos_eisley.run.conversation_sqlite import DATABASE, SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationSnapshot, ConversationStore


class SameRootExportTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = self.root / "sessions"
        cassette = demo_cassette()
        fresh = ConversationController.fresh(self.root, cassette)
        self.sid = fresh.session_id
        with SQLiteConversationStore(self.storage, self.sid, self.root) as store:
            store.save(fresh)
            chat = ConversationController(fresh, cassette, store.save)
            chat.refresh_memory(None, cassette)
            chat.submit(DEMO_PROMPTS[0])
            asyncio.run(chat.step())
            chat.submit(DEMO_PROMPTS[1])
            self.state = chat.state
            self.timestamp = store.inspect_snapshot()[1]
        self.json_path = self.storage / f"{self.sid}.json"

    def export(
        self, expected: str | None = None, *, apply: bool = False
    ) -> ConversationExportReceipt:
        return export_conversation(
            self.storage,
            self.storage,
            self.sid,
            self.root,
            expected_sha256=expected,
            apply=apply,
        )

    def files(self) -> dict[str, tuple[bytes, int]]:
        return {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.storage.iterdir()
            if path.is_file()
        }

    def assert_json(self) -> None:
        with ConversationStore(
            self.storage, self.sid, self.root, create=False
        ) as store:
            self.assertEqual(canonical_bytes(store.load()), canonical_bytes(self.state))

    def test_shared_lock_preview_apply_retry_preserves_sqlite_and_exact_json(
        self,
    ) -> None:
        before = self.files()
        preview = self.export()
        self.assertEqual(preview.status, "planned")
        self.assertEqual(preview.plan.schema_version, 2)
        self.assertEqual(preview.plan.source, preview.plan.destination)
        self.assertEqual(preview.export_sha256, digest(canonical_bytes(preview.plan)))
        self.assertEqual(
            preview,
            ConversationExportReceipt.model_validate_json(preview.model_dump_json()),
        )
        self.assertEqual(self.files(), before)
        self.assertEqual(
            self.export(preview.export_sha256, apply=True).status, "exported"
        )
        self.assert_json()
        self.assertEqual(self.json_path.stat().st_mtime_ns, self.timestamp)
        self.assertEqual(self.json_path.stat().st_size, preview.plan.snapshot_bytes)
        after = self.files()
        self.assertEqual({name: after[name] for name in before}, before)
        for apply in (False, True):
            result = self.export(preview.export_sha256, apply=apply)
            self.assertEqual(result.status, "already_present")
            self.assertEqual(result.export_sha256, preview.export_sha256)
        self.assertEqual(self.files(), after)

    def test_cross_root_v1_and_same_root_v2_plans_reject_swapped_versions_and_hashes(
        self,
    ) -> None:
        other = self.root / "other"
        other.mkdir(mode=0o700)
        cross = export_conversation(self.storage, other, self.sid, self.root)
        same = self.export()
        self.assertEqual(cross.plan.schema_version, 1)
        for plan, version in ((cross.plan, 2), (same.plan, 1)):
            value = plan.model_dump(mode="json")
            value["schema_version"] = version
            with self.assertRaises(ValueError):
                ConversationExportPlan.model_validate_json(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "selection changed"):
            self.export(cross.export_sha256, apply=True)
        with self.assertRaisesRegex(ValueError, "selection changed"):
            export_conversation(
                self.storage,
                other,
                self.sid,
                self.root,
                expected_sha256=same.export_sha256,
                apply=True,
            )
        self.assertFalse(self.json_path.exists())
        self.assertEqual(list(other.iterdir()), [])
        self.assertEqual(
            export_conversation(
                self.storage,
                other,
                self.sid,
                self.root,
                expected_sha256=cross.export_sha256,
                apply=True,
            ).status,
            "exported",
        )

    def test_different_paths_to_same_physical_root_share_the_lock(self) -> None:
        parent_alias = self.root / "alias"
        parent_alias.symlink_to(self.root, target_is_directory=True)
        alias = parent_alias / "sessions"
        preview = export_conversation(self.storage, alias, self.sid, self.root)
        self.assertEqual(preview.plan.schema_version, 2)
        self.assertNotEqual(preview.plan.source.path, preview.plan.destination.path)
        self.assertEqual(
            preview.plan.source.identity, preview.plan.destination.identity
        )
        result = export_conversation(
            self.storage,
            alias,
            self.sid,
            self.root,
            expected_sha256=preview.export_sha256,
            apply=True,
        )
        self.assertEqual(result.status, "exported")
        self.assert_json()

    def test_json_or_sqlite_writer_excludes_preview_and_apply(self) -> None:
        preview = self.export()
        for backend in (ConversationStore, SQLiteConversationStore):
            with backend(self.storage, self.sid, self.root, create=False):
                for apply in (False, True):
                    with self.assertRaises(BlockingIOError):
                        self.export(preview.export_sha256, apply=apply)
        self.assertFalse(self.json_path.exists())

    def test_original_json_copy_survives_different_sqlite_state(self) -> None:
        preview = self.export()
        older = self.state.model_copy(update={"revision": self.state.revision - 1})
        payload = canonical_bytes(
            ConversationSnapshot(state=older, sha256=digest(canonical_bytes(older)))
        )
        self.json_path.write_bytes(payload)
        self.json_path.chmod(0o600)
        before = self.files()
        for apply in (False, True):
            with self.assertRaisesRegex(ValueError, "different session"):
                self.export(preview.export_sha256, apply=apply)
        self.assertEqual(self.files(), before)

    def test_round_trip_back_into_existing_sqlite_verifies_without_changes(
        self,
    ) -> None:
        self.export(self.export().export_sha256, apply=True)
        before = self.files()
        with ConversationMigration(self.storage, self.sid, self.root) as migration:
            receipt = migration.migrate(
                expected_sha256=digest(canonical_bytes(self.state)), apply=True
            )
        self.assertEqual(receipt.status, "already_present")
        self.assertEqual(self.files(), before)

    def test_root_replacement_before_publication_cannot_publish_to_either_root(
        self,
    ) -> None:
        preview = self.export()
        original = os.fsync
        old = self.root / "old"

        def replace(fd: int) -> None:
            original(fd)
            if stat.S_ISREG(os.fstat(fd).st_mode):
                self.storage.rename(old)
                shutil.copytree(old, self.storage)

        with (
            patch.object(json_backend.os, "fsync", replace),
            self.assertRaisesRegex(ValueError, "directory changed"),
        ):
            self.export(preview.export_sha256, apply=True)
        self.assertFalse(self.json_path.exists())
        self.assertFalse((old / self.json_path.name).exists())
        self.assertEqual(list(old.glob("*.tmp")), [])

    def test_process_exit_before_and_after_publication_keeps_sqlite_unchanged(
        self,
    ) -> None:
        preview = self.export()
        before = self.files()
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
root, sid, workspace, selected, boundary = sys.argv[1:]
original = os.replace
def crash(*args, **kwargs):
    if boundary == "after":
        original(*args, **kwargs)
    os._exit(77)
with patch.object(backend.os, "replace", crash):
    export_conversation(Path(root), Path(root), sid, Path(workspace),
                        expected_sha256=selected, apply=True)
""",
                    str(self.storage),
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
            self.assertEqual(self.json_path.exists(), boundary == "after")
        self.assertEqual(
            self.export(preview.export_sha256, apply=True).status, "already_present"
        )
        self.assert_json()
        after = self.files()
        self.assertEqual({name: after[name] for name in before}, before)

    def test_hot_journal_blocks_same_root_export_without_json_publication(self) -> None:
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
                str(self.storage / DATABASE),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(crashed.returncode, 77, crashed.stderr)
        before = self.files()
        self.assertIn(DATABASE + "-journal", before)
        for apply in (False, True):
            with self.assertRaises(ValueError):
                self.export(preview.export_sha256, apply=apply)
        self.assertEqual(self.files(), before)

    def test_cli_default_destination_json_resume_and_sqlite_source_stays_unchanged(
        self,
    ) -> None:
        base = [sys.executable, "-m", "mos_eisley.cli"]
        storage = ["--storage", str(self.storage), "-C", str(self.root), "--json"]

        def invoke(
            args: list[str], stdin: str = ""
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [*base, *args, *storage],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=30,
            )

        preview = invoke(["session-export", self.sid])
        self.assertEqual(preview.returncode, 0, preview.stderr)
        receipt = json.loads(preview.stdout)
        self.assertEqual(receipt["plan"]["schema_version"], 2)
        command = [
            "session-export",
            self.sid,
            "--apply",
            "--expected-sha256",
            receipt["export_sha256"],
        ]
        for expected in ("exported", "already_present"):
            result = invoke(command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], expected)
        resumed = invoke(
            ["resume", self.sid, "--storage-backend", "snapshot"], "/continue\n"
        )
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        with ConversationStore(
            self.storage, self.sid, self.root, create=False
        ) as store:
            advanced = store.load()
            self.assertEqual(advanced.exchanges_consumed, 2)
            self.assertEqual(advanced.entries[-1].status, "completed")
            self.assertEqual(
                advanced.entries[0].request_admission,
                self.state.entries[0].request_admission,
            )
        before = self.files()
        self.assertEqual(invoke(command).returncode, 2)
        self.assertEqual(self.files(), before)
        with SQLiteConversationStore(
            self.storage, self.sid, self.root, create=False, writable=False
        ) as store:
            self.assertEqual(canonical_bytes(store.load()), canonical_bytes(self.state))
