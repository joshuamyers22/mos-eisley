"""Opt-in incremental SQLite sessions with bounded metadata pages.

The database and its parents are trusted owner-local paths. File checks reject
unsafe existing files; they do not defend against hostile same-user path races.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import sqlite3
import threading
import time
from collections.abc import Callable, Generator
from contextlib import closing, contextmanager, suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Self
from urllib.parse import quote
from uuid import uuid4

from pydantic import Field, TypeAdapter, model_validator

from mos_eisley.conversation import ConversationState, SessionID
from mos_eisley.conversation_inputs import ActiveInputLimits, InputField
from mos_eisley.conversation_limits import MAX_SNAPSHOT_BYTES
from mos_eisley.conversation_state import (
    ArchivedConversationEntry,
    ConversationEntry,
    RuntimeConversationState,
    WorkingConversationState,
    validate_runtime_state,
)
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.conversation_checkpoint import ResumeCheckpoint, resume_checkpoint
from mos_eisley.run.conversation_store import (
    ConversationDeletion,
    ConversationSnapshot,
    ConversationStore,
    ConversationSummary,
    validate_private_storage,
)

if TYPE_CHECKING:
    from mos_eisley.run.conversation_artifacts import ArtifactContent
    from mos_eisley.run.conversation_transcript import TranscriptPage

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
    entry_sha256: Annotated[tuple[Digest, ...] | None, Field(max_length=16)] = Field(
        default=None, exclude_if=lambda value: value is None
    )
    resume_checkpoint: ResumeCheckpoint | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


@dataclass(frozen=True)
class _SaveCheckpoint:
    index: SessionIndex
    store_id: str
    data_version: int
    total_changes: int
    artifacts: frozenset[str]
    canonical_artifacts: bool = False
    review_brief_ids: tuple[str | None, ...] | None = None


def _data_version(db: sqlite3.Connection) -> int:
    row = db.execute("PRAGMA main.data_version").fetchone()
    if row is None or type(row[0]) is not int or row[0] < 0:
        raise ValueError("SQLite data version is unavailable")
    return row[0]


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


@dataclass(frozen=True)
class _PreparedPart:
    """Canonical record bytes and proof, scoped to one storage operation."""

    part: PackedPart
    payload: bytes
    sha256: str


def _record_bytes(part: PackedPart) -> bytes:
    payload = canonical_bytes(part)
    if len(payload) > MAX_RECORD_BYTES:
        raise ValueError("SQLite conversation record exceeds byte limit")
    return payload


def _prepare_part(part: PackedPart) -> _PreparedPart:
    payload = _record_bytes(part)
    return _PreparedPart(part=part, payload=payload, sha256=digest(payload))


def _pack_part(
    body: dict[str, Any], fields: tuple[str, ...], artifacts: dict[str, bytes]
) -> PackedPart:
    refs: dict[str, str] = {}
    for field in fields:
        if body.get(field) is not None:
            payload = _json(body.pop(field))
            sha = digest(payload)
            artifacts[sha] = payload
            refs[field] = sha
    return PackedPart(body=body, refs=refs)


def _pack(
    body: dict[str, Any], fields: tuple[str, ...], artifacts: dict[str, bytes]
) -> bytes:
    return _record_bytes(_pack_part(body, fields, artifacts))


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


def _index(
    state: ConversationState, modified_ns: int, *, entry_digests: bool = True
) -> SessionIndex:
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
        entry_sha256=(
            tuple(
                digest(
                    _pack(
                        entry.model_dump(mode="json"),
                        ("memory_context", "review_packet", "review_result"),
                        {},
                    )
                )
                for entry in state.entries
            )
            if entry_digests
            else None
        ),
    )


STREAM_CHUNK_BYTES = 32_768
MAX_ACTIVE_ENTRY_BYTES = 512_000


def _working_parts(
    state: RuntimeConversationState,
) -> tuple[_PreparedPart, list[_PreparedPart], dict[str, bytes]]:
    artifacts: dict[str, bytes] = {}
    body = state.model_dump(mode="json", exclude={"entries"})
    header = _prepare_part(_pack_part(body, ("memory", "retained_cassette"), artifacts))
    parts: list[_PreparedPart] = []
    for entry in state.entries:
        if isinstance(entry, ArchivedConversationEntry):
            part = PackedPart(body=entry.record_body(), refs=dict(entry.artifact_refs))
        else:
            part = _pack_part(
                entry.model_dump(mode="json"),
                ("memory_context", "review_packet", "review_result"),
                artifacts,
            )
        parts.append(_prepare_part(part))
    return header, parts, artifacts


def _compact_working(
    state: RuntimeConversationState, parts: list[PackedPart], digests: tuple[str, ...]
) -> WorkingConversationState:
    latest = next(
        (
            i
            for i in range(len(state.entries) - 1, -1, -1)
            if "review_result" in parts[i].refs
        ),
        None,
    )
    entries: list[ConversationEntry | ArchivedConversationEntry] = []
    for position, (entry, part, sha) in enumerate(
        zip(state.entries, parts, digests, strict=True)
    ):
        if part.refs:
            entries.append(
                ArchivedConversationEntry.model_validate(
                    {
                        **part.body,
                        "artifact_refs": part.refs,
                        "source_sha256": sha,
                        "review_brief_id": entry.review_brief_id,
                        "review_result": entry.review_result
                        if position == latest
                        else None,
                    }
                )
            )
        else:
            entries.append(ConversationEntry.model_validate_json(_json(part.body)))
    return WorkingConversationState.model_validate(
        {**dict(state), "entries": tuple(entries)}
    )


def _artifact_chunks(
    db: sqlite3.Connection,
    sid: str,
    sha: str,
    artifacts: dict[str, bytes],
    retained: frozenset[str],
) -> Generator[bytes]:
    if sha in artifacts:
        payload = artifacts[sha]
        for offset in range(0, len(payload), STREAM_CHUNK_BYTES):
            yield payload[offset : offset + STREAM_CHUNK_BYTES]
        return
    if sha not in retained:
        raise ValueError("unverified archived artifact reference")
    row = db.execute(
        "SELECT rowid, length(payload) FROM artifacts WHERE sid=? AND sha=?", (sid, sha)
    ).fetchone()
    if row is None or not 1 <= row[1] <= MAX_SNAPSHOT_BYTES:
        raise ValueError("missing or oversized archived artifact")
    checksum = hashlib.sha256()
    with db.blobopen("artifacts", "payload", row[0], readonly=True) as blob:
        if len(blob) != row[1]:
            raise ValueError("archived artifact size changed")
        while chunk := blob.read(STREAM_CHUNK_BYTES):
            checksum.update(chunk)
            yield chunk
    if checksum.hexdigest() != sha:
        raise ValueError("archived artifact integrity mismatch")


def _state_chunks(
    part: PackedPart,
    read_artifact: Callable[[str], Generator[bytes]],
    *,
    entries: list[PackedPart] | None = None,
) -> Generator[bytes]:
    # Module-level recursion avoids a self-referential closure retaining the
    # artifact reader, its store and encoded active inputs until cyclic GC runs.
    yield b"{"
    keys = sorted(
        part.body.keys()
        | part.refs.keys()
        | ({"entries"} if entries is not None else set())
    )
    for position, key in enumerate(keys):
        if position:
            yield b","
        yield _json(key) + b":"
        if key in part.refs:
            yield from read_artifact(part.refs[key])
        elif entries is not None and key == "entries":
            yield b"["
            for index, entry in enumerate(entries):
                if index:
                    yield b","
                yield from _state_chunks(entry, read_artifact)
            yield b"]"
        else:
            yield _json(part.body[key])
    yield b"}"


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
        input_limits: ActiveInputLimits | None = None,
    ) -> None:
        self.input_limits = input_limits
        self._db: sqlite3.Connection | None = None
        self._verified_checkpoint: _SaveCheckpoint | None = None
        self._transcript_guard = threading.Lock()
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
        self._verified_checkpoint = None
        if self._db is not None:
            self._db.close()
            self._db = None
        self._db = _connect(self._path, self._root, create=create, writable=writable)

    def close(self) -> None:
        self._verified_checkpoint = None
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
        self._admit_stored_active_inputs(db)
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
        if self.input_limits is not None:
            self.input_limits.admit(state.memory, state.retained_cassette)
        if _index(
            state,
            record.summary.modified_ns,
            entry_digests=False,
        ) != record.model_copy(
            update={"entry_sha256": None, "resume_checkpoint": None}
        ) or (
            record.entry_sha256 is not None
            and record.entry_sha256 != tuple(digest(payload) for payload in encoded[1:])
        ):
            raise ValueError("SQLite conversation state integrity mismatch")
        if record.resume_checkpoint is not None and (
            record.resume_checkpoint
            != resume_checkpoint(state, encoded[0], encoded[1:])
        ):
            raise ValueError("SQLite resume checkpoint integrity mismatch")
        return ConversationSnapshot(state=state, sha256=record.summary.snapshot_sha256)

    def _read(self) -> ConversationSnapshot:
        self._verified_checkpoint = None
        db = self._connection()
        with conversation_transaction(db):
            store_id, _ = _identity(db)
            snapshot = self._load(db)
            checkpoint = self._capture_checkpoint(db, store_id, snapshot.sha256)
        self._verified_checkpoint = checkpoint
        return snapshot

    def _capture_checkpoint(
        self, db: sqlite3.Connection, store_id: str, expected_sha256: str
    ) -> _SaveCheckpoint:
        """Called only after full validation, inside the same transaction."""
        index = read_sqlite_session_index(db, self.session_id, self.workspace)
        if index.summary.snapshot_sha256 != expected_sha256:
            raise ValueError("SQLite verified checkpoint changed")
        rows = db.execute(
            "SELECT sha FROM artifacts WHERE sid=? LIMIT 51", (self.session_id,)
        ).fetchall()
        if len(rows) > 50:
            raise ValueError("SQLite artifact inventory exceeds checkpoint limit")
        return _SaveCheckpoint(
            index=index,
            store_id=store_id,
            data_version=_data_version(db),
            total_changes=db.total_changes,
            artifacts=frozenset(row[0] for row in rows),
        )

    def _current_checkpoint(
        self, db: sqlite3.Connection, store_id: str
    ) -> _SaveCheckpoint | None:
        # Compare versions only on this connection. BEGIN IMMEDIATE has already
        # excluded external writers; capture/publish also happens at commit boundaries.
        checkpoint = self._verified_checkpoint
        if (
            checkpoint is None
            or checkpoint.store_id != store_id
            or checkpoint.data_version != _data_version(db)
            or checkpoint.total_changes != db.total_changes
            or checkpoint.index.resume_checkpoint is None
            or checkpoint.index.entry_sha256 is None
        ):
            return None
        index = read_sqlite_session_index(db, self.session_id, self.workspace)
        return checkpoint if checkpoint.index == index else None

    def save(self, state: ConversationState) -> None:
        with self._transcript_guard:
            self._save(state)

    @property
    def snapshot_sha256(self) -> str | None:
        return self._sha256

    def load_working(self) -> RuntimeConversationState:
        """Verify current sessions one entry at a time before publishing state.

        Older indexes or noncanonical artifacts use the full-state controller
        until an ordinary save upgrades them and the user reopens the session.
        """
        with self._transcript_guard:
            self._verified_checkpoint = None
            db = self._connection()
            with conversation_transaction(db):
                store_id, _ = _identity(db)
                state = self._load_working(db)
                if state is None:
                    snapshot = self._load(db)
                    state = snapshot.state
                    sha = snapshot.sha256
                else:
                    sha = read_sqlite_session_index(
                        db, self.session_id, self.workspace
                    ).summary.snapshot_sha256
                checkpoint = self._capture_checkpoint(db, store_id, sha)
                if isinstance(state, WorkingConversationState):
                    checkpoint = replace(
                        checkpoint,
                        canonical_artifacts=True,
                        review_brief_ids=tuple(
                            entry.review_brief_id for entry in state.entries
                        ),
                    )
            self._revision = state.revision
            self._sha256 = sha
            self._verified_checkpoint = checkpoint
            return state

    def _cold_part(
        self,
        db: sqlite3.Connection,
        part: PackedPart,
        sizes: dict[str, int],
        fields: tuple[str, ...],
        limit: int,
    ) -> dict[str, Any]:
        if (
            not part.refs.keys() <= set(fields)
            or not set(part.refs.values()) <= sizes.keys()
        ):
            raise ValueError("invalid cold-resume artifact reference")
        # Count repeated field references too: each expands into a decoded value.
        size = len(canonical_bytes(part)) + sum(
            sizes[sha] for sha in part.refs.values()
        )
        if size > limit:
            raise ValueError(f"cold-resume input needs {size} bytes; limit is {limit}")
        body = dict(part.body)
        for field, sha in part.refs.items():
            with closing(
                self._artifact_chunks(db, sha, {}, frozenset(sizes))
            ) as chunks:
                payload = b"".join(chunks)
            if len(payload) != sizes[sha]:
                raise ValueError("cold-resume artifact size changed")
            body[field] = json.loads(payload)
        return body

    def _cold_entry(
        self,
        db: sqlite3.Connection,
        part: PackedPart,
        sizes: dict[str, int],
        sha: str,
        *,
        retain_result: bool,
    ) -> tuple[ConversationEntry | ArchivedConversationEntry, PackedPart] | None:
        fields = ("memory_context", "review_packet", "review_result")
        body = self._cold_part(db, part, sizes, fields, MAX_ACTIVE_ENTRY_BYTES)
        entry = ConversationEntry.model_validate_json(_json(body))
        if entry.memory_context is not None and entry.memory_context.memory is not None:
            entry.memory_context.memory.validate_identity(os.getuid(), self.workspace)
        normalized = PackedPart.model_validate_json(
            _pack(entry.model_dump(mode="json"), fields, {})
        )
        if normalized.refs != part.refs:
            return None  # Noncanonical or inline legacy artifacts need the old reader.
        if not part.refs:
            return entry, normalized
        archived = ArchivedConversationEntry.model_validate(
            {
                **normalized.body,
                "artifact_refs": normalized.refs,
                "source_sha256": sha,
                "review_brief_id": entry.review_brief_id,
                "review_result": entry.review_result if retain_result else None,
            }
        )
        return archived, normalized

    def _load_working(self, db: sqlite3.Connection) -> WorkingConversationState | None:
        """Cold verification without accumulating decoded historical artifacts.

        None selects the full-state compatibility reader, never a partial result.
        Active header values and all bounded text records remain resident.
        """
        index = read_sqlite_session_index(db, self.session_id, self.workspace)
        self._admit_stored_active_inputs(db)
        checkpoint, digests = index.resume_checkpoint, index.entry_sha256
        if checkpoint is None or digests is None:
            return None
        row = db.execute(
            "SELECT CASE WHEN length(header)<=? THEN header END "
            "FROM sessions WHERE sid=?",
            (MAX_RECORD_BYTES, self.session_id),
        ).fetchone()
        if (
            row is None
            or not isinstance(row[0], bytes)
            or len(row[0]) != checkpoint.header_bytes
            or digest(row[0]) != checkpoint.header_sha256
        ):
            raise ValueError("cold-resume header integrity mismatch")
        raw_header = row[0]
        rows = db.execute(
            "SELECT position, CASE WHEN length(payload)<=? THEN payload END "
            "FROM entries WHERE sid=? ORDER BY position LIMIT 17",
            (MAX_RECORD_BYTES, self.session_id),
        ).fetchall()
        if (
            not len(rows)
            == len(digests)
            == len(checkpoint.entries)
            == index.summary.messages
        ):
            raise ValueError("invalid cold-resume entry count")
        raw_entries: list[bytes] = []
        for expected, (position, payload) in enumerate(rows):
            if (
                position != expected
                or not isinstance(payload, bytes)
                or len(payload) != checkpoint.entries[expected].bytes
                or digest(payload) != digests[expected]
            ):
                raise ValueError("cold-resume entry integrity mismatch")
            raw_entries.append(payload)
        inventory = db.execute(
            "SELECT sha, length(payload) FROM artifacts WHERE sid=? LIMIT 51",
            (self.session_id,),
        ).fetchall()
        if (
            len(inventory) > 50
            or any(
                type(size) is not int or not 1 <= size <= MAX_SNAPSHOT_BYTES
                for _, size in inventory
            )
            or sum(size for _, size in inventory) > MAX_SNAPSHOT_BYTES
        ):
            raise ValueError("cold-resume artifacts exceed byte limit")
        sizes = dict(inventory)
        header = PackedPart.model_validate_json(raw_header)
        parts = [PackedPart.model_validate_json(payload) for payload in raw_entries]
        if {
            sha for part in (header, *parts) for sha in part.refs.values()
        } != sizes.keys():
            raise ValueError("missing or unreferenced cold-resume artifacts")
        body = self._cold_part(
            db,
            header,
            sizes,
            ("memory", "retained_cassette"),
            MAX_SNAPSHOT_BYTES + MAX_RECORD_BYTES,
        )
        latest = next(
            (
                i
                for i in range(len(parts) - 1, -1, -1)
                if "review_result" in parts[i].refs
            ),
            None,
        )
        entries: list[ConversationEntry | ArchivedConversationEntry] = []
        normalized: list[PackedPart] = []
        for position, part in enumerate(parts):
            verified = self._cold_entry(
                db, part, sizes, digests[position], retain_result=position == latest
            )
            if verified is None:
                return None
            entry, canonical = verified
            entries.append(entry)
            normalized.append(canonical)
        # JSON validation preserves legacy coercions (e.g. cassette tuple fields).
        state = WorkingConversationState.model_validate_json(
            _json(
                {
                    **body,
                    "entries": [entry.model_dump(mode="json") for entry in entries],
                }
            )
        )
        state = state.model_copy(update={"entries": tuple(entries)})
        del body
        if self.input_limits is not None:
            self.input_limits.admit(state.memory, state.retained_cassette)
        if (
            state.session_id != self.session_id
            or state.owner_uid != os.getuid()
            or state.workspace != self.workspace
        ):
            raise ValueError("cold-resume state identity mismatch")
        artifacts: dict[str, bytes] = {}
        canonical_header = _prepare_part(
            _pack_part(
                state.model_dump(mode="json", exclude={"entries"}),
                ("memory", "retained_cassette"),
                artifacts,
            )
        ).part
        if canonical_header.refs != header.refs:
            return None
        del artifacts
        if resume_checkpoint(state, raw_header, raw_entries) != checkpoint:
            raise ValueError("cold-resume checkpoint integrity mismatch")
        checksum = hashlib.sha256()
        size = len(_json({"sha256": "0" * 64, "state": None})) - len(b"null")
        with closing(
            _state_chunks(
                canonical_header,
                lambda sha: self._artifact_chunks(db, sha, {}, frozenset(sizes)),
                entries=normalized,
            )
        ) as chunks:
            for chunk in chunks:
                size += len(chunk)
                if size > state.snapshot_byte_limit:
                    raise ValueError(
                        "cold-resume snapshot exceeds its saved byte limit"
                    )
                checksum.update(chunk)
        summary = ConversationSummary(
            session_id=state.session_id,
            snapshot_sha256=checksum.hexdigest(),
            revision=state.revision,
            modified_ns=index.summary.modified_ns,
            messages=len(entries),
            completed=sum(e.status == "completed" for e in entries),
            pending=sum(e.status == "queued" for e in entries),
            active=False,
            snapshot_bytes=size,
            snapshot_max_bytes=state.snapshot_byte_limit,
        )
        if summary != index.summary:
            raise ValueError("cold-resume state integrity mismatch")
        return state

    def _admit_stored_active_inputs(self, db: sqlite3.Connection) -> None:
        """Admit both header inputs before either payload, including legacy loads."""
        if self.input_limits is None:
            return
        row = db.execute(
            "SELECT CASE WHEN length(header)<=? THEN header END "
            "FROM sessions WHERE sid=?",
            (MAX_RECORD_BYTES, self.session_id),
        ).fetchone()
        if row is None or not isinstance(row[0], bytes):
            raise ValueError("active-input header is unavailable or oversized")
        part = PackedPart.model_validate_json(row[0])
        fields: tuple[InputField, ...] = ("memory", "retained_cassette")
        if not part.refs.keys() <= set(fields):
            raise ValueError("invalid active-input artifact field")
        for field in fields:
            if field in part.refs:
                size = db.execute(
                    "SELECT length(payload) FROM artifacts WHERE sid=? AND sha=?",
                    (self.session_id, part.refs[field]),
                ).fetchone()
                if size is None or type(size[0]) is not int or size[0] < 1:
                    raise ValueError("active-input artifact is unavailable")
                self.input_limits.admit_size(field, size[0])
            elif part.body.get(field) is not None:
                self.input_limits.admit_size(field, len(_json(part.body[field])))

    def _working_checkpoint(
        self, db: sqlite3.Connection, store_id: str
    ) -> _SaveCheckpoint:
        checkpoint = self._current_checkpoint(db, store_id)
        if (
            checkpoint is None
            or not checkpoint.canonical_artifacts
            or checkpoint.review_brief_ids is None
        ):
            state = self._load_working(db)
            if state is None:
                raise ValueError("archived storage changed; reopen this session")
            sha = read_sqlite_session_index(
                db, self.session_id, self.workspace
            ).summary.snapshot_sha256
            checkpoint = self._capture_checkpoint(db, store_id, sha)
            checkpoint = replace(
                checkpoint,
                canonical_artifacts=True,
                review_brief_ids=tuple(
                    entry.review_brief_id for entry in state.entries
                ),
            )
        if (
            checkpoint.index.summary.snapshot_sha256 != self._sha256
            or checkpoint.index.summary.revision != self._revision
        ):
            raise ValueError("saved conversation changed outside this handle")
        return checkpoint

    def _admit_archive(
        self,
        db: sqlite3.Connection,
        checkpoint: _SaveCheckpoint,
        position: int,
        entry: ArchivedConversationEntry,
        prepared: _PreparedPart,
    ) -> None:
        part = prepared.part
        digests = checkpoint.index.entry_sha256
        brief_ids = checkpoint.review_brief_ids
        if (
            digests is None
            or brief_ids is None
            or type(position) is not int
            or not 0 <= position < len(digests)
            or entry.source_sha256 != digests[position]
            or entry.review_brief_id != brief_ids[position]
            or not set(part.refs.values()) <= checkpoint.artifacts
        ):
            raise ValueError("archived message does not match the verified checkpoint")
        if prepared.sha256 == entry.source_sha256:
            return
        row = db.execute(
            "SELECT CASE WHEN length(payload)<=? THEN payload END FROM entries "
            "WHERE sid=? AND position=?",
            (MAX_RECORD_BYTES, self.session_id, position),
        ).fetchone()
        if (
            row is None
            or not isinstance(row[0], bytes)
            or digest(row[0]) != entry.source_sha256
        ):
            raise ValueError("archived message integrity mismatch")
        stored = PackedPart.model_validate_json(row[0])
        original = ArchivedConversationEntry.model_validate(
            {
                **stored.body,
                "artifact_refs": stored.refs,
                "source_sha256": entry.source_sha256,
                "review_brief_id": entry.review_brief_id,
            }
        )
        expected = original.record_body()
        if entry.status != original.status:
            if (original.status, entry.status) not in {
                ("running", "interrupted"),
                ("queued", "cancelled"),
            }:
                raise ValueError("invalid archived message transition")
            expected["status"] = entry.status
        if stored.refs != part.refs or expected != part.body:
            raise ValueError("archived message content changed")

    def load_working_entry(
        self, position: int, entry: ArchivedConversationEntry
    ) -> ConversationEntry:
        """Hydrate one admitted entry, under a separate aggregate input bound."""
        with self._transcript_guard:
            db = self._connection()
            with conversation_transaction(db):
                store_id, _ = _identity(db)
                checkpoint = self._working_checkpoint(db, store_id)
                part = PackedPart(
                    body=entry.record_body(), refs=dict(entry.artifact_refs)
                )
                prepared = _prepare_part(part)
                self._admit_archive(db, checkpoint, position, entry, prepared)
                sizes: dict[str, int] = {}
                for sha in set(part.refs.values()):
                    row = db.execute(
                        "SELECT length(payload) FROM artifacts WHERE sid=? AND sha=?",
                        (self.session_id, sha),
                    ).fetchone()
                    if (
                        row is None
                        or type(row[0]) is not int
                        or not 1 <= row[0] <= MAX_ACTIVE_ENTRY_BYTES
                    ):
                        raise ValueError(
                            "active entry artifact is unavailable or oversized"
                        )
                    sizes[sha] = row[0]
                total = len(prepared.payload) + sum(sizes.values())
                if total > MAX_ACTIVE_ENTRY_BYTES:
                    raise ValueError(
                        f"active entry needs {total} bytes; "
                        f"limit is {MAX_ACTIVE_ENTRY_BYTES}"
                    )
                artifacts: dict[str, bytes] = {}
                for sha in sizes:
                    payload = b"".join(
                        self._artifact_chunks(db, sha, {}, checkpoint.artifacts)
                    )
                    if len(payload) != sizes[sha]:
                        raise ValueError("active entry artifact size changed")
                    artifacts[sha] = payload
                body = _unpack(
                    part,
                    ("memory_context", "review_packet", "review_result"),
                    artifacts,
                    set(),
                )
                result = ConversationEntry.model_validate_json(_json(body))
            self._verified_checkpoint = checkpoint
            return result

    def save_working(self, state: WorkingConversationState) -> WorkingConversationState:
        with self._transcript_guard:
            try:
                return self._write_working(state)
            except BaseException:
                self._verified_checkpoint = None
                raise

    def _write_working(
        self, state: WorkingConversationState
    ) -> WorkingConversationState:
        if self.input_limits is not None:
            self.input_limits.admit(state.memory, state.retained_cassette)
        state = validate_runtime_state(state)
        if (
            state.owner_uid != os.getuid()
            or state.session_id != self.session_id
            or state.workspace != self.workspace
            or state.revision != self._revision + 1
        ):
            raise ValueError("invalid conversation save identity or revision")
        prepared_header, prepared_entries, artifacts = _working_parts(state)
        header = prepared_header.part
        parts = [prepared.part for prepared in prepared_entries]
        header_bytes = prepared_header.payload
        payloads = [prepared.payload for prepared in prepared_entries]
        digests = tuple(prepared.sha256 for prepared in prepared_entries)
        db = self._connection()
        with conversation_transaction(db, write=True):
            store_id, _ = _identity(db)
            previous = self._working_checkpoint(db, store_id)
            for position, entry in enumerate(state.entries):
                if isinstance(entry, ArchivedConversationEntry):
                    self._admit_archive(
                        db, previous, position, entry, prepared_entries[position]
                    )
            referenced = frozenset(
                sha for part in (header, *parts) for sha in part.refs.values()
            )
            if (
                len(referenced) > 50
                or not referenced <= artifacts.keys() | previous.artifacts
            ):
                raise ValueError("invalid working artifact inventory")
            checksum = hashlib.sha256()
            size = len(_json({"sha256": "0" * 64, "state": None})) - len(b"null")
            with closing(
                _state_chunks(
                    header,
                    lambda sha: self._artifact_chunks(
                        db, sha, artifacts, previous.artifacts
                    ),
                    entries=parts,
                )
            ) as chunks:
                for chunk in chunks:
                    size += len(chunk)
                    if size > state.snapshot_byte_limit:
                        raise ValueError(
                            "conversation snapshot exceeds its saved byte limit; "
                            "resume with --session-max-bytes BYTES"
                        )
                    checksum.update(chunk)
            summary = ConversationSummary(
                session_id=self.session_id,
                snapshot_sha256=checksum.hexdigest(),
                revision=state.revision,
                modified_ns=time.time_ns(),
                messages=len(parts),
                completed=sum(entry.status == "completed" for entry in state.entries),
                pending=sum(entry.status == "queued" for entry in state.entries),
                active=False,
                snapshot_bytes=size,
                snapshot_max_bytes=state.snapshot_byte_limit,
            )
            index = SessionIndex(
                owner_uid=state.owner_uid,
                workspace=state.workspace,
                summary=summary,
                entry_sha256=digests,
                resume_checkpoint=resume_checkpoint(state, header_bytes, payloads),
            )
            record = canonical_bytes(index)
            if len(record) > MAX_INDEX_BYTES:
                raise ValueError("SQLite working index exceeds byte limit")
            working = _compact_working(state, parts, digests)
            db.execute(
                "UPDATE sessions SET modified_ns=?, record=?, record_sha=?, "
                "header=? WHERE sid=?",
                (
                    summary.modified_ns,
                    record,
                    digest(record),
                    header_bytes,
                    self.session_id,
                ),
            )
            previous_digests = previous.index.entry_sha256
            assert previous_digests is not None
            for position, payload in enumerate(payloads):
                if (
                    position < len(previous_digests)
                    and digests[position] == previous_digests[position]
                ):
                    continue
                db.execute(
                    "INSERT INTO entries VALUES (?, ?, ?, ?) ON CONFLICT(sid, "
                    "position) DO UPDATE SET payload=excluded.payload, "
                    "revision=excluded.revision",
                    (self.session_id, position, payload, state.revision),
                )
            if len(parts) < len(previous_digests):
                db.execute(
                    "DELETE FROM entries WHERE sid=? AND position>=?",
                    (self.session_id, len(parts)),
                )
            for sha, payload in artifacts.items():
                if sha not in previous.artifacts:
                    db.execute(
                        "INSERT INTO artifacts VALUES (?, ?, ?)",
                        (self.session_id, sha, payload),
                    )
            for sha in previous.artifacts - referenced:
                db.execute(
                    "DELETE FROM artifacts WHERE sid=? AND sha=?",
                    (self.session_id, sha),
                )
            db.execute("UPDATE metadata SET generation=generation+1 WHERE id=1")
            checkpoint = _SaveCheckpoint(
                index=index,
                store_id=store_id,
                data_version=_data_version(db),
                total_changes=db.total_changes,
                artifacts=referenced,
                canonical_artifacts=True,
                review_brief_ids=tuple(
                    entry.review_brief_id for entry in state.entries
                ),
            )
        self._revision = state.revision
        self._sha256 = summary.snapshot_sha256
        self._verified_checkpoint = checkpoint
        return working

    def _artifact_chunks(
        self,
        db: sqlite3.Connection,
        sha: str,
        artifacts: dict[str, bytes],
        retained: frozenset[str],
    ) -> Generator[bytes]:
        yield from _artifact_chunks(db, self.session_id, sha, artifacts, retained)

    def transcript_page(self, cursor: str | None) -> TranscriptPage:
        """Read with a separate connection, excluding this handle's session saves."""
        from mos_eisley.run.conversation_transcript import read_sqlite_transcript

        with self._transcript_guard:
            return read_sqlite_transcript(
                self._path,
                self.session_id,
                Path(self.workspace),
                limit=4,
                cursor=cursor,
            )

    def transcript_artifact(self, selection: str) -> ArtifactContent:
        """Expand one selection with the terminal's read/save coordination."""
        from mos_eisley.run.conversation_artifacts import read_sqlite_artifact

        with self._transcript_guard:
            return read_sqlite_artifact(
                self._path,
                Path(self.workspace),
                selection,
                expected_session_id=self.session_id,
            )

    def prepare_transcript(self, expected_sha256: str) -> ConversationSummary:
        """Verify full state and prepare page/resume indexes without changing it."""
        expected = TypeAdapter[str](Digest).validate_python(expected_sha256)
        self._verified_checkpoint = None
        db = self._connection()
        with conversation_transaction(db, write=True):
            _identity(db)
            snapshot = self._load(db)
            if snapshot.sha256 != expected:
                raise ValueError("conversation changed since transcript was selected")
            row = db.execute(
                "SELECT sid, workspace, modified_ns, record, record_sha "
                "FROM sessions WHERE sid=?",
                (self.session_id,),
            ).fetchone()
            current = _read_index(row)
            if current.entry_sha256 is None or current.resume_checkpoint is None:
                payloads = db.execute(
                    "SELECT payload FROM entries WHERE sid=? "
                    "ORDER BY position LIMIT 16",
                    (self.session_id,),
                ).fetchall()
                # _load already bounded and verified these rows in this transaction.
                # Hash their actual representation, including valid legacy whitespace.
                header = db.execute(
                    "SELECT header FROM sessions WHERE sid=?", (self.session_id,)
                ).fetchone()[0]
                index = current.model_copy(
                    update={
                        "entry_sha256": tuple(
                            digest(payload) for (payload,) in payloads
                        ),
                        "resume_checkpoint": resume_checkpoint(
                            snapshot.state,
                            header,
                            [payload for (payload,) in payloads],
                        ),
                    }
                )
                record = canonical_bytes(index)
                db.execute(
                    "UPDATE sessions SET record=?, record_sha=? WHERE sid=?",
                    (record, digest(record), self.session_id),
                )
                db.execute("UPDATE metadata SET generation=generation+1 WHERE id=1")
            return current.summary

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
        try:
            return self._write_state(
                state, modified_ns=modified_ns, validate_source=validate_source
            )
        except BaseException:
            self._verified_checkpoint = None
            raise

    def _write_state(
        self,
        state: ConversationState,
        *,
        modified_ns: int | None = None,
        validate_source: Callable[[], None] | None = None,
    ) -> bool:
        if self.input_limits is not None:
            self.input_limits.admit(state.memory, state.retained_cassette)
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
        index = index.model_copy(
            update={"resume_checkpoint": resume_checkpoint(state, header, parts)}
        )
        record = canonical_bytes(index)
        with conversation_transaction(db, write=True):
            store_id, _ = _identity(db)
            previous = (
                None
                if validate_source is not None
                else self._current_checkpoint(db, store_id)
            )
            if previous is None:
                try:
                    current = self._load(db)
                except FileNotFoundError:
                    if self._revision != -1:
                        raise ValueError("saved conversation disappeared") from None
                    for table in ("entries", "artifacts"):
                        if (
                            db.execute(
                                f"SELECT 1 FROM {table} WHERE sid=? LIMIT 1",
                                (self.session_id,),
                            ).fetchone()
                            is not None
                        ):
                            raise ValueError(
                                "orphan SQLite records prevent session save"
                            ) from None
                else:
                    if validate_source is not None:
                        if current.state != state:
                            raise ValueError(
                                "SQLite destination contains a different session state"
                            )
                        validate_source()
                        return False
                    previous = self._capture_checkpoint(db, store_id, current.sha256)
            if previous is not None and (
                previous.index.summary.snapshot_sha256 != self._sha256
                or previous.index.summary.revision != self._revision
            ):
                raise ValueError("saved conversation changed outside this handle")
            retained_artifacts: frozenset[str] = (
                frozenset() if previous is None else previous.artifacts
            )
            previous_digests = None if previous is None else previous.index.entry_sha256
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
                if (
                    previous_digests is not None
                    and position < len(previous_digests)
                    and digest(payload) == previous_digests[position]
                ):
                    continue
                db.execute(
                    "INSERT INTO entries VALUES (?, ?, ?, ?) ON CONFLICT(sid, "
                    "position) DO UPDATE SET payload=excluded.payload, "
                    "revision=excluded.revision WHERE "
                    "entries.payload<>excluded.payload",
                    (self.session_id, position, payload, state.revision),
                )
            if previous is not None and previous.index.summary.messages > len(parts):
                db.execute(
                    "DELETE FROM entries WHERE sid=? AND position>=?",
                    (self.session_id, len(parts)),
                )
            for sha, payload in artifacts.items():
                if sha in retained_artifacts:
                    continue
                db.execute(
                    "INSERT INTO artifacts VALUES (?, ?, ?)",
                    (self.session_id, sha, payload),
                )
            for sha in retained_artifacts - artifacts.keys():
                db.execute(
                    "DELETE FROM artifacts WHERE sid=? AND sha=?",
                    (self.session_id, sha),
                )
            db.execute("UPDATE metadata SET generation=generation+1 WHERE id=1")
            if validate_source is not None:
                if self._load(db).state != state:
                    raise ValueError("SQLite migration verification failed")
                validate_source()
            checkpoint = _SaveCheckpoint(
                index=index,
                store_id=store_id,
                data_version=_data_version(db),
                total_changes=db.total_changes,
                artifacts=frozenset(artifacts),
            )
        self._revision = state.revision
        self._sha256 = index.summary.snapshot_sha256
        self._verified_checkpoint = checkpoint
        return True

    def delete(self, expected_sha256: str) -> ConversationDeletion:

        expected = TypeAdapter[str](Digest).validate_python(expected_sha256)
        self._verified_checkpoint = None
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


@contextmanager
def sqlite_read_transaction(
    root: Path,
) -> Generator[tuple[sqlite3.Connection, str, int]]:
    """Open one owner-validated read-only transaction without creating storage."""
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    db: sqlite3.Connection | None = None
    try:
        validate_private_storage(root_fd, directory=True)
        db = _connect(root.absolute(), root_fd, create=False, writable=False)
        with conversation_transaction(db):
            store_id, generation = _identity(db)
            yield db, store_id, generation
    finally:
        if db is not None:
            db.close()
        os.close(root_fd)


def read_sqlite_session_index(
    db: sqlite3.Connection, session_id: str, workspace: str
) -> SessionIndex:
    row = db.execute(
        "SELECT sid, workspace, modified_ns, CASE WHEN length(record)<=? "
        "THEN record END, record_sha FROM sessions WHERE sid=?",
        (MAX_INDEX_BYTES, session_id),
    ).fetchone()
    if row is None:
        raise FileNotFoundError("saved SQLite conversation is unavailable")
    record = _read_index(row)
    if record.workspace != workspace:
        raise ValueError("conversation workspace mismatch")
    return record


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
