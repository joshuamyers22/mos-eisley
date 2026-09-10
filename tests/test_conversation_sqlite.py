"""Incremental records, atomic recovery, private storage and bounded index pages."""

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
from typing import Any
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
from mos_eisley.run.conversation_sqlite import (
    DATABASE,
    SQLiteConversationStore,
    list_sqlite_conversations,
)


def new_session(root: Path, workspace: Path | None = None) -> str:
    workspace = workspace or root
    state = ConversationController.fresh(workspace, demo_cassette())
    with SQLiteConversationStore(root, state.session_id, workspace) as store:
        store.save(state)
    return state.session_id


class SQLiteStoreTests(TestCase):
    def test_review_artifacts_round_trip_without_ambient_memory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            memory = MemoryStore(root / "memory", root)
            memory.change("user", "set", text="PRIVATE-MEMORY-CANARY")
            selected = memory.load()
            cassette = demo_cassette(memory=selected)
            state = ConversationController.fresh(root, cassette, selected)
            brief, recording = demo_inputs()
            with SQLiteConversationStore(root, state.session_id, root) as store:
                store.save(state)
                controller = ConversationController(state, cassette, store.save)
                controller.submit_review(
                    ConversationReviewPacket(brief=brief, cassette=recording)
                )
                asyncio.run(controller.step())
                self.assertEqual(controller.state.entries[0].status, "completed")
                self.assertEqual(controller.state.exchanges_consumed, 0)
                self.assertNotIn(
                    "PRIVATE-MEMORY-CANARY",
                    controller.state.entries[0].model_dump_json(),
                )
                self.assertEqual(store.load(), controller.state)

    def test_incremental_entries_artifact_reuse_memory_refresh_and_resume(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            memory = MemoryStore(root / "memory", root)
            memory.change("user", "set", text="MEMORY-CANARY")
            selected = memory.load()
            cassette = demo_cassette(memory=selected)
            state = ConversationController.fresh(root, cassette, selected)
            with SQLiteConversationStore(root, state.session_id, root) as store:
                store.save(state)
                controller = ConversationController(state, cassette, store.save)
                runtime = ConversationMemoryRuntime(
                    controller, memory, lambda selected: demo_cassette(memory=selected)
                )
                runtime.refresh(False)
                controller.submit(DEMO_PROMPTS[0])
                asyncio.run(controller.step())
                with sqlite3.connect(root / DATABASE) as check:
                    first = check.execute(
                        "SELECT payload, revision FROM entries WHERE position=0"
                    ).fetchone()
                    artifacts = dict(check.execute("SELECT sha, rowid FROM artifacts"))
                controller.submit(DEMO_PROMPTS[1])
                asyncio.run(controller.step())
                with sqlite3.connect(root / DATABASE) as check:
                    self.assertEqual(
                        check.execute(
                            "SELECT payload, revision FROM entries WHERE position=0"
                        ).fetchone(),
                        first,
                    )
                    self.assertEqual(
                        dict(check.execute("SELECT sha, rowid FROM artifacts")),
                        artifacts,
                    )
                    self.assertEqual(
                        check.execute("SELECT count(*) FROM entries").fetchone()[0], 2
                    )
                saved = controller.state
            with SQLiteConversationStore(
                root, state.session_id, root, create=False
            ) as store:
                self.assertEqual(store.load(), saved)
                controller = ConversationController(
                    saved, controller.cassette, store.save
                )
                runtime = ConversationMemoryRuntime(
                    controller, memory, lambda selected: demo_cassette(memory=selected)
                )
                runtime.refresh(True, snapshot_max_bytes=4_000_000)
                self.assertTrue(controller.state.memory_disabled)
                self.assertEqual(controller.state.exchanges_consumed, 2)
                self.assertEqual(store.load(), controller.state)
            self.assertEqual((root / DATABASE).stat().st_mode & 0o777, 0o600)
            self.assertFalse(tuple(root.glob("*.json")))

    def test_save_and_delete_rollback_preserve_state_and_generation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sid = new_session(root)
            with SQLiteConversationStore(root, sid, root, create=False) as store:
                state = store.load()
                controller = ConversationController(state, demo_cassette(), store.save)
                original_transaction = backend.conversation_transaction

                @contextmanager
                def fail_commit(
                    db: sqlite3.Connection, *, write: bool = False
                ) -> Generator[None]:
                    with original_transaction(db, write=write):
                        yield
                        if write:
                            raise OSError("injected commit failure")

                before = list_sqlite_conversations(root, root)
                with patch.object(backend, "conversation_transaction", fail_commit):
                    with self.assertRaises(OSError):
                        controller.submit(DEMO_PROMPTS[0])
                    with self.assertRaises(OSError):
                        store.delete(digest(canonical_bytes(state)))
                self.assertEqual(store.load(), state)
                self.assertEqual(controller.state, state)
                self.assertEqual(list_sqlite_conversations(root, root), before)
                with self.assertRaisesRegex(ValueError, "persistence failed"):
                    controller.submit("must reopen")
                contender = ConversationController(state, demo_cassette(), store.save)
                with sqlite3.connect(root / DATABASE) as blocker:
                    blocker.execute("BEGIN IMMEDIATE")
                    with self.assertRaisesRegex(ValueError, "transaction failed"):
                        contender.submit("blocked before admission")
                    blocker.rollback()
                self.assertEqual(contender.state, state)
                self.assertEqual(store.load(), state)

    def test_lock_stale_handle_wrong_workspace_and_exact_delete(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sid = new_session(root)
            other = root / "other"
            other.mkdir()
            with SQLiteConversationStore(root, sid, root, create=False) as store:
                state = store.load()
                self.assertTrue(
                    list_sqlite_conversations(root, root).sessions[0].active
                )
                with self.assertRaises(BlockingIOError):
                    SQLiteConversationStore(root, sid, root, create=False)
                with self.assertRaisesRegex(ValueError, "changed"):
                    store.delete("0" * 64)
                changed = state.model_copy(update={"revision": 1})
                store.save(changed)
                with self.assertRaisesRegex(ValueError, "revision"):
                    store.save(changed)
            with (
                SQLiteConversationStore(root, sid, other, create=False) as store,
                self.assertRaisesRegex(ValueError, "workspace"),
            ):
                store.load()
            with SQLiteConversationStore(root, sid, root, create=False) as store:
                current = store.load()
                receipt = store.delete(digest(canonical_bytes(current)))
                self.assertEqual(receipt.session_id, sid)
                with self.assertRaisesRegex(ValueError, "deleted"):
                    store.load()
            self.assertEqual(list_sqlite_conversations(root, root).sessions, ())
            self.assertTrue((root / f"{sid}.lock").exists())
            with sqlite3.connect(root / DATABASE) as check:
                for table in ("sessions", "entries", "artifacts"):
                    self.assertEqual(
                        check.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0
                    )

    def test_invalid_permissions_links_schema_and_owner_reject_open(self) -> None:
        for damage in (
            "public",
            "symlink",
            "hardlink",
            "fifo",
            "journal",
            "schema",
            "owner",
            "missing",
            "wal",
        ):
            with self.subTest(damage=damage), TemporaryDirectory() as directory:
                root = Path(directory)
                sid = new_session(root)
                path = root / DATABASE
                if damage == "public":
                    path.chmod(0o644)
                elif damage == "symlink":
                    path.rename(root / "target")
                    path.symlink_to(root / "target")
                elif damage == "hardlink":
                    os.link(path, root / "target")
                elif damage == "fifo":
                    path.unlink()
                    os.mkfifo(path, 0o600)
                elif damage == "journal":
                    (root / (DATABASE + "-journal")).symlink_to(root / "target")
                elif damage == "missing":
                    path.unlink()
                elif damage == "wal":
                    with sqlite3.connect(path) as change:
                        change.execute("PRAGMA journal_mode=WAL")
                    change.close()
                else:
                    with sqlite3.connect(path) as change:
                        if damage == "schema":
                            change.execute("CREATE TABLE sqlitex_extra (payload TEXT)")
                        else:
                            change.execute("UPDATE metadata SET owner_uid=owner_uid+1")
                with self.assertRaises((ValueError, OSError)):
                    SQLiteConversationStore(root, sid, root, create=False)
                with self.assertRaises((ValueError, OSError)):
                    list_sqlite_conversations(root, root)
                if damage == "wal":
                    self.assertFalse((root / (DATABASE + "-wal")).exists())
                    self.assertFalse((root / (DATABASE + "-shm")).exists())

    def test_corrupt_referenced_artifacts_rejected_on_resume_but_listing_is_metadata(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sid = new_session(root)
            with SQLiteConversationStore(root, sid, root, create=False) as store:
                controller = ConversationController(
                    store.load(), demo_cassette(), store.save
                )
                controller.refresh_memory(None, demo_cassette(), builtin=True)
            with sqlite3.connect(root / DATABASE) as change:
                change.execute("UPDATE artifacts SET payload=?", (b"{}",))
            self.assertEqual(len(list_sqlite_conversations(root, root).sessions), 1)
            with (
                SQLiteConversationStore(root, sid, root, create=False) as store,
                self.assertRaisesRegex(ValueError, "artifact integrity"),
            ):
                store.load()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            sid = new_session(root)
            artifact = json.dumps({"oversized": "x" * 2_300_000}).encode()
            sha = digest(artifact)
            entry = canonical_bytes(
                backend.PackedPart(
                    body={"text": "invalid repeated memory"},
                    refs={"memory_context": sha},
                )
            )
            with sqlite3.connect(root / DATABASE) as change:
                row = json.loads(
                    change.execute("SELECT record FROM sessions").fetchone()[0]
                )
                row["summary"].update(messages=16, pending=16)
                record = json.dumps(row).encode()
                change.execute(
                    "UPDATE sessions SET record=?, record_sha=?",
                    (record, digest(record)),
                )
                change.execute(
                    "INSERT INTO artifacts VALUES (?, ?, ?)", (sid, sha, artifact)
                )
                change.executemany(
                    "INSERT INTO entries VALUES (?, ?, ?, 0)",
                    [(sid, i, entry) for i in range(16)],
                )
            with (
                SQLiteConversationStore(root, sid, root, create=False) as store,
                patch.object(
                    backend,
                    "_unpack",
                    side_effect=AssertionError("must bound expansion first"),
                ),
                self.assertRaisesRegex(ValueError, "expanded"),
            ):
                store.load()

    def test_logical_budget_reduction_cannot_drop_content(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = ConversationController.fresh(root, demo_cassette()).model_copy(
                update={
                    "entries": tuple(
                        ConversationEntry(text="x" * 8000) for _ in range(16)
                    )
                }
            )
            with SQLiteConversationStore(root, state.session_id, root) as store:
                store.save(state)
                controller = ConversationController(state, demo_cassette(), store.save)
                with self.assertRaisesRegex(ValueError, "byte limit"):
                    controller.resize_storage(64_000)
                self.assertEqual(store.load(), state)
                row = list_sqlite_conversations(root, root).sessions[0]
                self.assertGreater(row.snapshot_bytes, 64_000)

    def test_crashed_sqlite_transaction_rolls_back_on_reopen(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sid = new_session(root)
            before = list_sqlite_conversations(root, root).sessions[0]
            code = (
                "import os, sqlite3, sys; db=sqlite3.connect(sys.argv[1]); "
                "db.execute('BEGIN IMMEDIATE'); "
                "db.execute('UPDATE sessions SET record_sha=?', ('0'*64,)); "
                "os._exit(17)"
            )
            child = subprocess.run(
                [sys.executable, "-c", code, str(root / DATABASE)], timeout=10
            )
            self.assertEqual(child.returncode, 17)
            with SQLiteConversationStore(root, sid, root, create=False) as store:
                state = store.load()
                self.assertEqual(digest(canonical_bytes(state)), before.snapshot_sha256)


class SQLiteNavigationTests(TestCase):
    def test_pages_exceed_legacy_catalog_count_and_never_read_transcripts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ids = {new_session(root) for _ in range(260)}
            original_connect = sqlite3.connect

            def metadata_only(*args: Any, **kwargs: Any) -> sqlite3.Connection:
                connection = original_connect(*args, **kwargs)

                def authorize(
                    action: int,
                    first: str | None,
                    second: str | None,
                    database: str | None,
                    source: str | None,
                ) -> int:
                    return (
                        sqlite3.SQLITE_DENY
                        if action == sqlite3.SQLITE_READ
                        and first in {"entries", "artifacts"}
                        else sqlite3.SQLITE_OK
                    )

                connection.set_authorizer(authorize)
                return connection

            found: list[str] = []
            cursor = None
            with patch.object(backend.sqlite3, "connect", metadata_only):
                while True:
                    page = list_sqlite_conversations(
                        root, root, limit=37, cursor=cursor
                    )
                    self.assertLessEqual(len(page.sessions), 37)
                    found.extend(row.session_id for row in page.sessions)
                    if page.next_cursor is None:
                        break
                    cursor = page.next_cursor
            self.assertEqual(set(found), ids)
            self.assertEqual(len(found), len(ids))

    def test_stale_foreign_workspace_and_database_cursors_reject(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            new_session(root)
            new_session(root)
            cursor = list_sqlite_conversations(root, root, limit=1).next_cursor
            assert cursor is not None
            other = root / "other"
            other.mkdir(mode=0o700)
            new_session(other)
            for storage, workspace in ((root, other), (other, other)):
                with self.assertRaisesRegex(ValueError, "cursor"):
                    list_sqlite_conversations(storage, workspace, cursor=cursor)
            new_session(root)
            with self.assertRaisesRegex(ValueError, "stale"):
                list_sqlite_conversations(root, root, cursor=cursor)
            for token in ("!!!", "A" * 32001):
                with self.assertRaisesRegex(ValueError, "cursor"):
                    list_sqlite_conversations(root, root, cursor=token)
            for limit in (0, 101, True):
                with self.assertRaises(ValueError):
                    list_sqlite_conversations(root, root, limit=limit)

    def test_bad_index_fails_without_partial_rows_and_missing_root_is_not_created(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                list_sqlite_conversations(root / "missing", root)
            self.assertFalse((root / "missing").exists())
            new_session(root)
            new_session(root)
            with sqlite3.connect(root / DATABASE) as change:
                change.execute("UPDATE sessions SET record_sha=?", ("0" * 64,))
            with self.assertRaisesRegex(ValueError, "index integrity"):
                list_sqlite_conversations(root, root)


class SQLiteCLITests(TestCase):
    def test_selecting_sqlite_never_migrates_or_falls_back_to_json(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.invoke(home, "--plain")
            self.assertEqual(result.returncode, 0, result.stderr)
            path = next((home / ".mos-eisley-sessions").glob("*.json"))
            before = path.read_bytes()
            result = self.invoke(
                home, "resume", "--last", "--storage-backend", "sqlite", "--plain"
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((home / ".mos-eisley-sessions" / DATABASE).exists())

    def invoke(
        self, home: Path, *args: str, text: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mos_eisley.cli", *args],
            input=text,
            text=True,
            capture_output=True,
            timeout=20,
            env={**os.environ, "HOME": str(home)},
        )

    def test_chat_resume_memory_resize_list_and_delete(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            options = ("--storage-backend", "sqlite", "--json")
            result = self.invoke(home, *options, text=DEMO_PROMPTS[0] + "\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.invoke(
                home,
                "resume",
                "--last",
                "--refresh-memory",
                "--no-memory",
                "--session-max-bytes",
                "4000000",
                *options,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.invoke(
                home, "resume", "--last", *options, text=DEMO_PROMPTS[1] + "\n"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("You gave me a boundary of ten.", result.stdout)
            result = self.invoke(home, "sessions", "--limit", "1", *options)
            self.assertEqual(result.returncode, 0, result.stderr)
            listed = json.loads(result.stdout)
            row = listed["sessions"][0]
            self.assertIsNone(listed["next_cursor"])
            self.assertEqual(row["completed"], 2)
            self.assertEqual(row["snapshot_max_bytes"], 4_000_000)
            result = self.invoke(
                home,
                "session-delete",
                row["session_id"],
                "--expected-sha256",
                row["snapshot_sha256"],
                *options,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.invoke(home, "sessions", *options)
            self.assertEqual(json.loads(result.stdout)["sessions"], [])
            self.assertFalse(tuple((home / ".mos-eisley-sessions").glob("*.json")))

    def test_cli_pagination_and_backend_options_fail_before_creating_storage(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            for args in (
                ("sessions", "--limit", "1"),
                ("sessions", "--storage-backend", "sqlite", "--limit", "101"),
                (
                    "resume",
                    "--last",
                    "--storage-backend",
                    "sqlite",
                    "--catalog-max-bytes",
                    "1000",
                ),
            ):
                result = self.invoke(home, *args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse((home / ".mos-eisley-sessions").exists())
            options = ("--storage-backend", "sqlite", "--json")
            for _ in range(3):
                result = self.invoke(home, *options)
                self.assertEqual(result.returncode, 0, result.stderr)
            result = self.invoke(home, "sessions", "--limit", "2", *options)
            self.assertEqual(result.returncode, 0, result.stderr)
            first = json.loads(result.stdout)
            result = self.invoke(
                home,
                "sessions",
                "--limit",
                "2",
                "--cursor",
                first["next_cursor"],
                *options,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            second = json.loads(result.stdout)
            self.assertEqual(len(first["sessions"]), 2)
            self.assertEqual(len(second["sessions"]), 1)
            self.assertIsNone(second["next_cursor"])
            result = self.invoke(home, "sessions", "--json")
            self.assertEqual(json.loads(result.stdout)["sessions"], [])

    def test_resume_marks_running_interrupted_and_keeps_queue_paused(self) -> None:
        with TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / ".mos-eisley-sessions"
            state = ConversationController.fresh(
                Path.cwd(), demo_cassette()
            ).model_copy(
                update={
                    "entries": (
                        ConversationEntry(text=DEMO_PROMPTS[0], status="running"),
                        ConversationEntry(text=DEMO_PROMPTS[1]),
                    ),
                    "exchanges_consumed": 1,
                }
            )
            with SQLiteConversationStore(root, state.session_id, Path.cwd()) as store:
                store.save(state)
            result = self.invoke(
                home, "resume", "--last", "--storage-backend", "sqlite", "--json"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with SQLiteConversationStore(
                root, state.session_id, Path.cwd(), create=False
            ) as store:
                saved = store.load()
            self.assertEqual(saved.exchanges_consumed, 1)
            self.assertEqual(
                [entry.status for entry in saved.entries], ["interrupted", "queued"]
            )
