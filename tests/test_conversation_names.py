"""Names remain private metadata through execution, persistence and transfers."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from mos_eisley.conversation import ConversationController, ConversationEntry
from mos_eisley.conversation_cli import DEMO_PROMPTS, demo_cassette
from mos_eisley.conversation_name import name_key, parse_name
from mos_eisley.conversation_state import ConversationState, WorkingConversationState
from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.conversation_export import export_conversation
from mos_eisley.run.conversation_migration import ConversationMigration
from mos_eisley.run.conversation_names import (
    named_sessions,
    rename_session,
    resume_catalog,
)
from mos_eisley.run.conversation_sqlite import SQLiteConversationStore
from mos_eisley.run.conversation_store import ConversationStore
from mos_eisley.run.conversation_transfer import transfer_conversation


class SessionNameTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = self.root / "sessions"
        self.cassette = demo_cassette()

    def seed(self, *, sqlite: bool, name: str | None = None) -> ConversationState:
        state = ConversationController.fresh(self.root, self.cassette).model_copy(
            update={"session_name": name}
        )
        backend = SQLiteConversationStore if sqlite else ConversationStore
        with backend(self.storage, state.session_id, self.root) as store:
            store.save(state)
        return state

    def invoke(self, *args: str, text: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *args],
            input=text,
            text=True,
            capture_output=True,
            cwd=self.root,
            env={**os.environ, "HOME": str(self.root)},
            timeout=15,
        )

    def test_normalization_and_invalid_names(self) -> None:
        self.assertEqual(parse_name("  Cafe\u0301 work  "), "Café work")
        self.assertEqual(name_key("STRASSE"), name_key("Straße"))
        self.assertEqual(parse_name("a  b"), "a  b")
        self.assertEqual(parse_name("x" * 120), "x" * 120)
        for value in (
            "",
            "   ",
            "x" * 121,
            "a\nb",
            "a\t",
            "\x1bX",
            "a\u202e",
            "\udcff",
        ):
            with (
                self.subTest(value=repr(value)),
                self.assertRaises(argparse.ArgumentTypeError),
            ):
                parse_name(value)

    def test_old_unnamed_state_bytes_and_hash_remain_identical(self) -> None:
        state = self.seed(sqlite=False)
        raw = state.model_dump(mode="json")
        self.assertNotIn("session_name", raw)
        legacy = json.dumps(
            raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        self.assertEqual(
            canonical_bytes(ConversationState.model_validate_json(legacy)), legacy
        )
        summary = resume_catalog(self.storage, self.root, sqlite=False).sessions[0]
        self.assertNotIn("session_name", summary.model_dump())
        self.assertEqual(summary.snapshot_sha256, digest(legacy))

    def test_rename_clear_noop_stale_and_content_preservation(self) -> None:
        for sqlite in (False, True):
            with self.subTest(sqlite=sqlite):
                state = self.seed(sqlite=sqlite)
                sid = state.session_id
                original = digest(canonical_bytes(state))
                receipt = rename_session(
                    self.storage,
                    self.root,
                    sid,
                    sqlite=sqlite,
                    expected_sha256=original,
                    name="Parser cleanup",
                )
                backend = SQLiteConversationStore if sqlite else ConversationStore
                with backend(self.storage, sid, self.root, create=False) as store:
                    renamed = store.load()
                self.assertEqual(renamed.session_id, sid)
                self.assertEqual(renamed.revision, state.revision + 1)
                self.assertEqual(renamed.entries, state.entries)
                self.assertEqual(renamed.exchanges_consumed, state.exchanges_consumed)
                self.assertEqual(renamed.session_name, "Parser cleanup")
                self.assertNotEqual(receipt["snapshot_sha256"], original)
                with self.assertRaisesRegex(ValueError, "changed"):
                    rename_session(
                        self.storage,
                        self.root,
                        sid,
                        sqlite=sqlite,
                        expected_sha256=original,
                        name="stale",
                    )
                current = digest(canonical_bytes(renamed))
                noop = rename_session(
                    self.storage,
                    self.root,
                    sid,
                    sqlite=sqlite,
                    expected_sha256=current,
                    name="Parser cleanup",
                )
                self.assertFalse(noop["changed"])
                self.assertEqual(noop["snapshot_sha256"], current)
                rename_session(
                    self.storage,
                    self.root,
                    sid,
                    sqlite=sqlite,
                    expected_sha256=current,
                    name=None,
                )
                with backend(self.storage, sid, self.root, create=False) as store:
                    cleared = store.load()
                self.assertIsNone(cleared.session_name)
                self.assertEqual(cleared.revision, renamed.revision + 1)

    def test_scope_duplicates_and_active_locks(self) -> None:
        for sqlite in (False, True):
            with self.subTest(sqlite=sqlite):
                first = self.seed(sqlite=sqlite, name="Straße")
                second = self.seed(sqlite=sqlite, name="STRASSE")
                catalog = resume_catalog(self.storage, self.root, sqlite=sqlite)
                self.assertEqual(
                    {s.session_id for s in named_sessions(catalog, "strasse")},
                    {first.session_id, second.session_id},
                )
                project = self.root / "project"
                project.mkdir(exist_ok=True)
                self.assertEqual(
                    resume_catalog(self.storage, project, sqlite=sqlite).sessions, ()
                )
                backend = SQLiteConversationStore if sqlite else ConversationStore
                with backend(self.storage, first.session_id, self.root, create=False):
                    catalog = resume_catalog(self.storage, self.root, sqlite=sqlite)
                    self.assertTrue(
                        next(
                            s
                            for s in catalog.sessions
                            if s.session_id == first.session_id
                        ).active
                    )
                    with self.assertRaises(BlockingIOError):
                        rename_session(
                            self.storage,
                            self.root,
                            first.session_id,
                            sqlite=sqlite,
                            expected_sha256=digest(canonical_bytes(first)),
                            name="new",
                        )
                with self.assertRaises(ValueError):
                    rename_session(
                        self.storage,
                        project,
                        first.session_id,
                        sqlite=sqlite,
                        expected_sha256=digest(canonical_bytes(first)),
                        name="new",
                    )

    def test_interrupted_running_state_cannot_be_renamed(self) -> None:
        for sqlite in (False, True):
            state = self.seed(sqlite=sqlite)
            backend = SQLiteConversationStore if sqlite else ConversationStore
            with backend(
                self.storage, state.session_id, self.root, create=False
            ) as store:
                state = store.load().model_copy(
                    update={
                        "revision": 1,
                        "exchanges_consumed": 1,
                        "entries": (
                            ConversationEntry(text=DEMO_PROMPTS[0], status="running"),
                        ),
                    }
                )
                store.save(state)
            with self.assertRaisesRegex(ValueError, "running"):
                rename_session(
                    self.storage,
                    self.root,
                    state.session_id,
                    sqlite=sqlite,
                    expected_sha256=digest(canonical_bytes(state)),
                    name="new",
                )

    def test_working_sqlite_rename_execution_and_memory_refresh_keep_name(self) -> None:
        state = self.seed(sqlite=True)
        with SQLiteConversationStore(
            self.storage, state.session_id, self.root, create=False
        ) as store:
            working = store.load_working()
            assert isinstance(working, WorkingConversationState)
            chat = ConversationController[WorkingConversationState](
                working,
                self.cassette,
                store.save_working,
                load_entry=store.load_working_entry,
            )
            chat.rename("Metadata only")
            chat.submit(DEMO_PROMPTS[0])
            asyncio.run(chat.step())
            self.assertEqual(chat.state.entries[0].status, "completed")
            chat.refresh_memory(None, self.cassette)
            self.assertEqual(chat.state.session_name, "Metadata only")
            saved = store.load()
            self.assertEqual(saved.session_name, "Metadata only")
        catalog = resume_catalog(self.storage, self.root, sqlite=True)
        self.assertEqual(
            catalog.sessions[0].snapshot_sha256, digest(canonical_bytes(saved))
        )

    def test_names_survive_migration_export_and_transfer(self) -> None:
        state = self.seed(sqlite=False, name="Retained Café")
        with ConversationMigration(
            self.storage, state.session_id, self.root
        ) as migration:
            preview = migration.migrate()
            migration.migrate(apply=True, expected_sha256=preview.snapshot_sha256)
        target = self.root / "export"
        target.mkdir(mode=0o700)
        preview = export_conversation(self.storage, target, state.session_id, self.root)
        export_conversation(
            self.storage,
            target,
            state.session_id,
            self.root,
            apply=True,
            expected_sha256=preview.export_sha256,
        )
        final = self.root / "import"
        final.mkdir(mode=0o700)
        transfer = transfer_conversation(target, final, state.session_id, self.root)
        transfer_conversation(
            target,
            final,
            state.session_id,
            self.root,
            apply=True,
            expected_sha256=transfer.transfer_sha256,
        )
        with SQLiteConversationStore(
            final, state.session_id, self.root, create=False
        ) as store:
            self.assertEqual(canonical_bytes(store.load()), canonical_bytes(state))

    def test_cli_create_resume_rename_clear_both_backends(self) -> None:
        for backend in ("snapshot", "sqlite"):
            with self.subTest(backend=backend):
                flags = (
                    "--storage",
                    str(self.storage),
                    "--storage-backend",
                    backend,
                    "--json",
                )
                created = self.invoke(
                    "chat", "--name", "  Cafe\u0301  ", *flags, DEMO_PROMPTS[0]
                )
                self.assertEqual(created.returncode, 0, created.stderr)
                opened = next(
                    json.loads(line)
                    for line in created.stdout.splitlines()
                    if json.loads(line)["type"] == "conversation.opened"
                )
                self.assertEqual(opened["session_name"], "Café")
                resumed = self.invoke(
                    "resume", "--name", "CAFÉ", *flags, text=DEMO_PROMPTS[1] + "\n"
                )
                self.assertEqual(resumed.returncode, 0, resumed.stderr)
                self.assertIn("You gave me a boundary of ten.", resumed.stdout)
                renamed = self.invoke(
                    "resume",
                    "--name",
                    "café",
                    *flags,
                    text="/rename Parser cleanup\n/quit\n",
                )
                self.assertEqual(renamed.returncode, 0, renamed.stderr)
                catalog = resume_catalog(
                    self.storage, self.root, sqlite=backend == "sqlite"
                )
                row = named_sessions(catalog, "Parser cleanup")[0]
                self.assertEqual(row.session_id, opened["session_id"])
                cleared = self.invoke(
                    "session-rename",
                    row.session_id,
                    "--clear",
                    "--expected-sha256",
                    row.snapshot_sha256,
                    *flags,
                )
                self.assertEqual(cleared.returncode, 0, cleared.stderr)
                self.assertIsNone(json.loads(cleared.stdout)["session_name"])

    def test_noninteractive_picker_and_ambiguous_name_fail_without_writes(self) -> None:
        rejected = self.invoke("resume", "--json")
        self.assertEqual(rejected.returncode, 2)
        self.assertFalse((self.root / ".mos-eisley-sessions").exists())
        self.seed(sqlite=False, name="Duplicate")
        self.seed(sqlite=False, name="duplicate")
        before = {p.name: p.read_bytes() for p in self.storage.iterdir()}
        result = self.invoke(
            "resume", "--name", "DUPLICATE", "--storage", str(self.storage), "--json"
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("ambiguous", result.stderr)
        self.assertEqual(
            {p.name: p.read_bytes() for p in self.storage.iterdir()}, before
        )

    def test_invalid_cli_name_does_not_create_storage_or_echo_content(self) -> None:
        for value in ("PRIVATE\nlabel", "PRIVATE" + "x" * 120):
            result = self.invoke("chat", "--name", value)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("PRIVATE", result.stderr)
            self.assertFalse((self.root / ".mos-eisley-sessions").exists())

    def test_catalog_limit_and_stale_page_fail_closed(self) -> None:
        self.seed(sqlite=True, name="Named")
        with (
            patch("mos_eisley.run.conversation_names.MAX_RESUME_CATALOG", 0),
            self.assertRaisesRegex(ValueError, "exceeds"),
        ):
            resume_catalog(self.storage, self.root, sqlite=True)
        with (
            patch(
                "mos_eisley.run.conversation_names.list_sqlite_conversations",
                side_effect=ValueError("stale"),
            ),
            self.assertRaisesRegex(ValueError, "stale"),
        ):
            resume_catalog(self.storage, self.root, sqlite=True)
