"""Opt-in incremental SQLite sessions with bounded metadata pages.

The database and its parents are trusted owner-local paths. File checks reject
unsafe existing files; they do not defend against hostile same-user path races.
"""

from __future__ import annotations

import base64
import fcntl
import json
import os
import sqlite3
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Annotated, Any, Self
from urllib.parse import quote
from uuid import uuid4

from pydantic import Field, TypeAdapter, model_validator

from mos_eisley.conversation import ConversationState, SessionID
from mos_eisley.conversation_limits import MAX_SNAPSHOT_BYTES
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.conversation_store import (
    ConversationDeletion,
    ConversationSnapshot,
    ConversationStore,
    ConversationSummary,
    validate_private_storage,
)

MAX_DATABASE_BYTES = 256_000_000
MAX_RECORD_BYTES = 128_000
MAX_INDEX_BYTES = 32_000
MAX_PAGE_SIZE = 100
DATABASE = "sessions.sqlite3"
SCHEMA = (
    "CREATE TABLE metadata (id INTEGER PRIMARY KEY CHECK(id=1), "
    "store_id TEXT NOT NULL CHECK(length(store_id)=32), "
    "owner_uid INTEGER NOT NULL CHECK(owner_uid>=0), "
    "generation INTEGER NOT NULL CHECK(generation>=0)) STRICT",
    "CREATE TABLE sessions (sid TEXT PRIMARY KEY CHECK(length(sid)=32), "
    "workspace TEXT NOT NULL CHECK(length(workspace) BETWEEN 1 AND 4096), "
    "modified_ns INTEGER NOT NULL CHECK(modified_ns>=0), "
    "record BLOB NOT NULL CHECK(length(record)<=32000), "
    "record_sha TEXT NOT NULL CHECK(length(record_sha)=64), "
    "header BLOB NOT NULL CHECK(length(header)<=128000)) STRICT",
    "CREATE INDEX session_workspace ON sessions(workspace, modified_ns DESC, sid DESC)",
    "CREATE TABLE entries (sid TEXT NOT NULL REFERENCES sessions(sid) "
    "ON DELETE CASCADE, position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 15), "
    "payload BLOB NOT NULL CHECK(length(payload)<=128000), "
    "revision INTEGER NOT NULL CHECK(revision>=0), PRIMARY KEY(sid, position)) STRICT",
    "CREATE TABLE artifacts (sid TEXT NOT NULL REFERENCES sessions(sid) "
    "ON DELETE CASCADE, sha TEXT NOT NULL CHECK(length(sha)=64), "
    "payload BLOB NOT NULL CHECK(length(payload) BETWEEN 1 AND 32000000), "
    "PRIMARY KEY(sid, sha)) STRICT",
)


def _json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


class PackedPart(Contract):
    body: dict[str, Any]
    refs: dict[str, Digest]

    @model_validator(mode="after")
    def disjoint(self) -> Self:
        if self.body.keys() & self.refs.keys():
            raise ValueError("duplicate SQLite artifact reference")
        return self


class SessionIndex(Contract):
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    summary: ConversationSummary


class PageCursor(Contract):
    store_id: SessionID
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    generation: Annotated[int, Field(ge=0)]
    modified_ns: Annotated[int, Field(ge=0)]
    session_id: SessionID


class ConversationPage(Contract):
    sessions: tuple[ConversationSummary, ...]
    next_cursor: str | None = None


def _pack(
    body: dict[str, Any], fields: tuple[str, ...], artifacts: dict[str, bytes]
) -> bytes:
    refs: dict[str, str] = {}
    for field in fields:
        if body.get(field) is not None:
            payload = _json(body.pop(field))
            sha = digest(payload)
            artifacts[sha] = payload
            refs[field] = sha
    payload = canonical_bytes(PackedPart(body=body, refs=refs))
    if len(payload) > MAX_RECORD_BYTES:
        raise ValueError("SQLite conversation record exceeds byte limit")
    return payload


def _unpack(
    part: PackedPart,
    fields: tuple[str, ...],
    artifacts: dict[str, bytes],
    used: set[str],
) -> dict[str, Any]:
    if not part.refs.keys() <= set(fields):
        raise ValueError("invalid SQLite artifact field")
    for field, sha in part.refs.items():
        if sha not in artifacts:
            raise ValueError("missing SQLite conversation artifact")
        used.add(sha)
        part.body[field] = json.loads(artifacts[sha])
    return part.body


def _index(state: ConversationState, modified_ns: int) -> SessionIndex:
    sha = digest(canonical_bytes(state))
    size = len(canonical_bytes(ConversationSnapshot(state=state, sha256=sha)))
    if size > state.snapshot_byte_limit:
        raise ValueError(
            "conversation snapshot exceeds its saved byte limit; resume with "
            "--session-max-bytes BYTES"
        )
    return SessionIndex(
        owner_uid=state.owner_uid,
        workspace=state.workspace,
        summary=ConversationSummary(
            session_id=state.session_id,
            snapshot_sha256=sha,
            revision=state.revision,
            modified_ns=modified_ns,
            messages=len(state.entries),
            completed=sum(entry.status == "completed" for entry in state.entries),
            pending=sum(entry.status == "queued" for entry in state.entries),
            active=False,
            snapshot_bytes=size,
            snapshot_max_bytes=state.snapshot_byte_limit,
        ),
    )


def _files(root: int) -> None:
    validate_private_storage(root, directory=True)
    for name in (DATABASE, DATABASE + "-journal", DATABASE + "-wal", DATABASE + "-shm"):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        except FileNotFoundError:
            if name == DATABASE:
                raise
            continue
        try:
            validate_private_storage(fd)
            if os.fstat(fd).st_size > MAX_DATABASE_BYTES:
                raise ValueError("SQLite conversation database exceeds file limit")
            if name == DATABASE and os.fstat(fd).st_size:
                header = os.pread(fd, 20, 0)
                if (
                    header[:16] != b"SQLite format 3\x00"
                    or header[18:20] != b"\x01\x01"
                ):
                    raise ValueError("unsupported SQLite conversation file format")
            if name.endswith(("-wal", "-shm")):
                raise ValueError("unsupported SQLite conversation journal mode")
        finally:
            os.close(fd)


def _connect(
    root: Path, root_fd: int, *, create: bool, writable: bool
) -> sqlite3.Connection:
    if sqlite3.sqlite_version_info < (3, 37, 0):
        raise ValueError("SQLite conversation storage requires SQLite 3.37 or newer")
    guard = os.open(
        "sqlite.lock",
        (os.O_RDWR | os.O_CREAT if create else os.O_RDONLY)
        | os.O_NOFOLLOW
        | os.O_NONBLOCK,
        0o600,
        dir_fd=root_fd,
    )
    db: sqlite3.Connection | None = None
    try:
        validate_private_storage(guard)
        fcntl.flock(
            guard, (fcntl.LOCK_EX if writable else fcntl.LOCK_SH) | fcntl.LOCK_NB
        )
        created = False
        if create:
            try:
                fd = os.open(
                    DATABASE,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=root_fd,
                )
            except FileExistsError:
                pass
            else:
                os.close(fd)
                created = True
        _files(root_fd)
        # SQLite opens its own descriptors; require the resolved root to match the
        # already validated directory, with trusted parents throughout this call.
        if (
            os.stat(root).st_ino != os.fstat(root_fd).st_ino
            or os.stat(root).st_dev != os.fstat(root_fd).st_dev
        ):
            raise ValueError("SQLite conversation root changed")
        mode = "rw" if writable else "ro"
        db = sqlite3.connect(
            f"file:{quote(str(root / DATABASE), safe='/')}?mode={mode}",
            uri=True,
            timeout=0,
            isolation_level=None,
        )
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA cache_size=-2048")
        if writable:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA secure_delete=ON")
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            db.execute(f"PRAGMA max_page_count={MAX_DATABASE_BYTES // page_size}")
        if created:
            with conversation_transaction(db, write=True):
                for statement in SCHEMA:
                    db.execute(statement)
                db.execute(
                    "INSERT INTO metadata VALUES (1, ?, ?, 0)",
                    (uuid4().hex, os.getuid()),
                )
                db.execute("PRAGMA user_version=1")
            os.fsync(root_fd)
        if (
            db.execute("PRAGMA journal_mode").fetchone()[0] != "delete"
            or db.execute("PRAGMA user_version").fetchone()[0] != 1
        ):
            raise ValueError("unsupported SQLite conversation schema or journal mode")
        actual = {
            row[0]
            for row in db.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE substr(name,1,7)<>'sqlite_' LIMIT 7"
            )
        }
        if actual != set(SCHEMA):
            raise ValueError("invalid SQLite conversation schema")
        _identity(db)
        _files(root_fd)
        return db
    except BaseException as error:
        if db is not None:
            db.close()
        if isinstance(error, sqlite3.Error):
            raise ValueError(
                "SQLite conversation storage could not be opened"
            ) from None
        raise
    finally:
        os.close(guard)


def _identity(db: sqlite3.Connection) -> tuple[str, int]:
    rows = db.execute(
        "SELECT CASE WHEN length(store_id)=32 THEN store_id END, "
        "owner_uid, generation FROM metadata LIMIT 2"
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("invalid SQLite conversation owner metadata")
    store_id, owner, generation = rows[0]
    if owner != os.getuid() or type(generation) is not int or generation < 0:
        raise ValueError("SQLite conversation ownership mismatch")

    return TypeAdapter[str](SessionID).validate_python(store_id), generation


@contextmanager
def conversation_transaction(
    db: sqlite3.Connection, *, write: bool = False
) -> Generator[None]:
    try:
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield
        db.execute("COMMIT")
    except BaseException as error:
        with suppress(sqlite3.Error):
            db.execute("ROLLBACK")
        if isinstance(error, sqlite3.Error):
            raise ValueError(
                "SQLite conversation transaction failed; reopen before continuing"
            ) from None
        raise


def _read_index(row: tuple[Any, ...]) -> SessionIndex:
    sid, workspace, modified_ns, payload, sha = row
    if (
        not isinstance(payload, bytes)
        or len(payload) > MAX_INDEX_BYTES
        or digest(payload) != sha
    ):
        raise ValueError("SQLite conversation index integrity mismatch")
    record = SessionIndex.model_validate_json(payload)
    summary = record.summary
    if (
        record.owner_uid != os.getuid()
        or record.workspace != workspace
        or summary.session_id != sid
        or summary.modified_ns != modified_ns
        or summary.active
    ):
        raise ValueError("SQLite conversation index identity mismatch")
    return record


class SQLiteConversationStore(ConversationStore):
    """Same logical snapshot contract; only changed entries/artifacts are written."""

    def __init__(
        self,
        root: Path,
        session_id: str,
        workspace: Path,
        *,
        create: bool = True,
        require_workspace: bool = True,
    ) -> None:
        self._db: sqlite3.Connection | None = None
        self._path = root.absolute()
        super().__init__(
            root,
            session_id,
            workspace,
            create=create,
            require_workspace=require_workspace,
        )
        try:
            self._open_database(create=create, writable=True)
        except BaseException:
            self.close()
            raise

    def _open_database(self, *, create: bool, writable: bool) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        self._db = _connect(self._path, self._root, create=create, writable=writable)

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        super().close()

    def _connection(self) -> sqlite3.Connection:
        if self._db is None or self._deleted:
            raise ValueError("SQLite conversation is closed or deleted")
        _files(self._root)
        return self._db

    def _load(self, db: sqlite3.Connection) -> ConversationSnapshot:
        row = db.execute(
            "SELECT sid, workspace, modified_ns, CASE WHEN length(record)<=? "
            "THEN record END, record_sha, CASE WHEN length(header)<=? THEN "
            "header END FROM sessions WHERE sid=?",
            (MAX_INDEX_BYTES, MAX_RECORD_BYTES, self.session_id),
        ).fetchone()
        if row is None:
            raise FileNotFoundError("saved SQLite conversation is unavailable")
        record = _read_index(row[:5])
        if record.workspace != self.workspace:
            raise ValueError("conversation workspace mismatch")
        if not isinstance(row[5], bytes):
            raise ValueError("SQLite conversation header exceeds byte limit")
        entries = db.execute(
            "SELECT position, CASE WHEN length(payload)<=? THEN payload END "
            "FROM entries WHERE sid=? ORDER BY position LIMIT 17",
            (MAX_RECORD_BYTES, self.session_id),
        ).fetchall()
        if len(entries) != record.summary.messages or any(
            position != i or not isinstance(payload, bytes)
            for i, (position, payload) in enumerate(entries)
        ):
            raise ValueError("invalid SQLite conversation entry records")
        sizes = db.execute(
            "SELECT sha, length(payload) FROM artifacts WHERE sid=? LIMIT 51",
            (self.session_id,),
        ).fetchall()
        if (
            len(sizes) > 50
            or any(
                type(size) is not int or size < 1 or size > MAX_SNAPSHOT_BYTES
                for _, size in sizes
            )
            or sum(size for _, size in sizes) > MAX_SNAPSHOT_BYTES
        ):
            raise ValueError("SQLite conversation artifacts exceed byte limit")
        artifacts: dict[str, bytes] = {}
        for sha, size in sizes:
            payload = db.execute(
                "SELECT payload FROM artifacts WHERE sid=? AND sha=?",
                (self.session_id, sha),
            ).fetchone()[0]
            if (
                not isinstance(payload, bytes)
                or len(payload) != size
                or digest(payload) != sha
            ):
                raise ValueError("SQLite conversation artifact integrity mismatch")
            artifacts[sha] = payload
        used: set[str] = set()
        encoded = [row[5], *(payload for _, payload in entries)]
        packed = [PackedPart.model_validate_json(payload) for payload in encoded]
        expanded = sum(len(payload) for payload in encoded) + sum(
            len(artifacts.get(sha, b""))
            for part in packed
            for sha in part.refs.values()
        )
        # Bound repeated references before allocating their decoded values.
        if expanded > MAX_SNAPSHOT_BYTES + 17 * MAX_RECORD_BYTES:
            raise ValueError("expanded SQLite conversation exceeds byte limit")
        body = _unpack(packed[0], ("memory", "retained_cassette"), artifacts, used)
        body["entries"] = [
            _unpack(
                part,
                ("memory_context", "review_packet", "review_result"),
                artifacts,
                used,
            )
            for part in packed[1:]
        ]
        if used != artifacts.keys():
            raise ValueError("unreferenced SQLite conversation artifacts")
        state = ConversationState.model_validate_json(_json(body))
        if _index(state, record.summary.modified_ns) != record:
            raise ValueError("SQLite conversation state integrity mismatch")
        return ConversationSnapshot(state=state, sha256=record.summary.snapshot_sha256)

    def _read(self) -> ConversationSnapshot:
        db = self._connection()
        with conversation_transaction(db):
            _identity(db)
            return self._load(db)

    def save(self, state: ConversationState) -> None:
        self._save(state)

    def import_snapshot(
        self,
        state: ConversationState,
        modified_ns: int,
        *,
        validate_source: Callable[[], None],
    ) -> bool:
        """Insert an exact legacy revision; never replace an existing conversation."""
        if self._revision != -1:
            raise ValueError("snapshot import requires a fresh destination handle")
        return self._save(
            state, modified_ns=modified_ns, validate_source=validate_source
        )

    def _save(
        self,
        state: ConversationState,
        *,
        modified_ns: int | None = None,
        validate_source: Callable[[], None] | None = None,
    ) -> bool:
        db = self._connection()
        state = ConversationState.model_validate_json(state.model_dump_json())
        if (
            state.owner_uid != os.getuid()
            or state.session_id != self.session_id
            or state.workspace != self.workspace
            or (validate_source is None and state.revision != self._revision + 1)
        ):
            raise ValueError("invalid conversation save identity or revision")
        index = _index(state, time.time_ns() if modified_ns is None else modified_ns)
        record = canonical_bytes(index)
        artifacts: dict[str, bytes] = {}
        body = state.model_dump(mode="json")
        entries = body.pop("entries")
        header = _pack(body, ("memory", "retained_cassette"), artifacts)
        parts = [
            _pack(
                entry, ("memory_context", "review_packet", "review_result"), artifacts
            )
            for entry in entries
        ]
        with conversation_transaction(db, write=True):
            _identity(db)
            try:
                current = self._load(db)
            except FileNotFoundError:
                if self._revision != -1:
                    raise ValueError("saved conversation disappeared") from None
            else:
                if validate_source is not None:
                    if current.state != state:
                        raise ValueError(
                            "SQLite destination contains a different session state"
                        )
                    validate_source()
                    return False
                if current.sha256 != self._sha256:
                    raise ValueError("saved conversation changed outside this handle")
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(sid) "
                "DO UPDATE SET workspace=excluded.workspace, "
                "modified_ns=excluded.modified_ns, record=excluded.record, "
                "record_sha=excluded.record_sha, header=excluded.header",
                (
                    self.session_id,
                    self.workspace,
                    index.summary.modified_ns,
                    record,
                    digest(record),
                    header,
                ),
            )
            for position, payload in enumerate(parts):
                db.execute(
                    "INSERT INTO entries VALUES (?, ?, ?, ?) ON CONFLICT(sid, "
                    "position) DO UPDATE SET payload=excluded.payload, "
                    "revision=excluded.revision WHERE "
                    "entries.payload<>excluded.payload",
                    (self.session_id, position, payload, state.revision),
                )
            db.execute(
                "DELETE FROM entries WHERE sid=? AND position>=?",
                (self.session_id, len(parts)),
            )
            for sha, payload in artifacts.items():
                db.execute(
                    "INSERT INTO artifacts VALUES (?, ?, ?) ON CONFLICT(sid, sha) DO "
                    "NOTHING",
                    (self.session_id, sha, payload),
                )
                retained = db.execute(
                    "SELECT CASE WHEN length(payload)<=? THEN payload END "
                    "FROM artifacts WHERE sid=? AND sha=?",
                    (MAX_SNAPSHOT_BYTES, self.session_id, sha),
                ).fetchone()[0]
                if retained != payload:
                    raise ValueError("SQLite artifact changed outside this handle")
            placeholders = ",".join("?" for _ in artifacts)
            db.execute(
                f"DELETE FROM artifacts WHERE sid=? AND sha NOT IN ({placeholders})",
                (self.session_id, *artifacts),
            )
            db.execute("UPDATE metadata SET generation=generation+1 WHERE id=1")
            if validate_source is not None:
                if self._load(db).state != state:
                    raise ValueError("SQLite migration verification failed")
                validate_source()
        self._revision = state.revision
        self._sha256 = index.summary.snapshot_sha256
        return True

    def delete(self, expected_sha256: str) -> ConversationDeletion:

        expected = TypeAdapter[str](Digest).validate_python(expected_sha256)
        db = self._connection()
        with conversation_transaction(db, write=True):
            _identity(db)
            snapshot = self._load(db)
            if snapshot.sha256 != expected:
                raise ValueError("conversation changed since deletion was selected")
            db.execute("DELETE FROM sessions WHERE sid=?", (self.session_id,))
            db.execute("UPDATE metadata SET generation=generation+1 WHERE id=1")
        self._deleted = True
        return ConversationDeletion(
            session_id=self.session_id,
            snapshot_sha256=expected,
            removed_temporary_files=0,
        )


def list_sqlite_conversations(
    root: Path, workspace: Path, *, limit: int = 50, cursor: str | None = None
) -> ConversationPage:
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError("SQLite page size must be between 1 and 100")
    selected_workspace = str(workspace.resolve())
    if workspace.exists() and not workspace.is_dir():
        raise ValueError("conversation workspace must be a directory")
    selected: PageCursor | None = None
    if cursor is not None:
        if len(cursor) > 32_000:
            raise ValueError("invalid SQLite conversation cursor")
        try:
            selected = PageCursor.model_validate_json(
                base64.b64decode(cursor, altchars=b"-_", validate=True)
            )
        except (ValueError, UnicodeError):
            raise ValueError("invalid SQLite conversation cursor") from None
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    db: sqlite3.Connection | None = None
    try:
        validate_private_storage(root_fd, directory=True)
        db = _connect(root.absolute(), root_fd, create=False, writable=False)
        with conversation_transaction(db):
            store_id, generation = _identity(db)
            if selected is not None and (
                selected.store_id != store_id
                or selected.owner_uid != os.getuid()
                or selected.workspace != selected_workspace
                or selected.generation != generation
            ):
                raise ValueError(
                    "SQLite catalog cursor is stale or belongs to another selection; "
                    "list again"
                )
            params: list[Any] = [MAX_INDEX_BYTES, selected_workspace]
            after = ""
            if selected is not None:
                after = " AND (modified_ns, sid) < (?, ?)"
                params.extend((selected.modified_ns, selected.session_id))
            params.append(limit + 1)
            rows = db.execute(
                "SELECT sid, workspace, modified_ns, CASE WHEN length(record)<=? "
                "THEN record END, record_sha FROM sessions WHERE workspace=?"
                + after
                + " ORDER BY modified_ns DESC, sid DESC LIMIT ?",
                params,
            ).fetchall()
            indexes = [_read_index(row) for row in rows]
            summaries: list[ConversationSummary] = []
            for record in indexes[:limit]:
                lock = os.open(
                    f"{record.summary.session_id}.lock",
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=root_fd,
                )
                try:
                    validate_private_storage(lock)
                    try:
                        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        active = False
                    except BlockingIOError:
                        active = True
                finally:
                    os.close(lock)
                summaries.append(record.summary.model_copy(update={"active": active}))
            next_cursor = None
            if len(indexes) > limit:
                last = summaries[-1]
                token = PageCursor(
                    store_id=store_id,
                    owner_uid=os.getuid(),
                    workspace=selected_workspace,
                    generation=generation,
                    modified_ns=last.modified_ns,
                    session_id=last.session_id,
                )
                next_cursor = base64.urlsafe_b64encode(canonical_bytes(token)).decode()
            return ConversationPage(sessions=tuple(summaries), next_cursor=next_cursor)
    finally:
        if db is not None:
            db.close()
        os.close(root_fd)
