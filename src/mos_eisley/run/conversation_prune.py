"""Full-state-verified, single-session retention deletion in one transaction."""

import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from mos_eisley.conversation_limits import MAX_SNAPSHOT_BYTES
from mos_eisley.conversation_state import SessionID
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.conversation_retention import (
    RetentionPlan,
    RetentionPolicy,
    read_retention_plan,
    retention_session_active,
)
from mos_eisley.run.conversation_sqlite import (
    DATABASE,
    SQLiteConversationStore,
    conversation_transaction,
)
from mos_eisley.run.conversation_store import (
    ConversationSummary,
    validate_private_storage,
)
from mos_eisley.run.conversation_transfer import (
    TransferLocation,
    inspect_storage_location,
)


class PruneFileIdentity(Contract):
    device: Annotated[int, Field(ge=0)]
    inode: Annotated[int, Field(ge=0)]


class PrunePlan(Contract):
    schema_version: Literal[1] = 1
    operation: Literal["delete_sqlite_session"] = "delete_sqlite_session"
    verification: Literal["selected_full_state"] = "selected_full_state"
    retention: RetentionPlan
    session_id: SessionID
    snapshot_sha256: Digest
    database: PruneFileIdentity
    lock: PruneFileIdentity
    artifacts: Annotated[int, Field(ge=0, le=50)]
    artifact_bytes: Annotated[int, Field(ge=0, le=MAX_SNAPSHOT_BYTES)]

    @property
    def selection(self) -> ConversationSummary:
        for entry in self.retention.sessions:
            if entry.summary.session_id == self.session_id:
                if entry.disposition != "candidate":
                    raise ValueError(
                        "selected session is protected by retention policy"
                    )
                return entry.summary
        raise ValueError("selected session is not in this workspace retention plan")

    @model_validator(mode="after")
    def exact_selection(self) -> Self:
        if self.selection.snapshot_sha256 != self.snapshot_sha256:
            raise ValueError("prune state does not match the retention selection")
        if (self.artifacts == 0) != (self.artifact_bytes == 0):
            raise ValueError("invalid prune artifact counts")
        return self


class PruneReceipt(Contract):
    schema_version: Literal[1] = 1
    status: Literal["planned", "deleted"]
    prune_sha256: Digest
    plan: PrunePlan
    removed_sessions: Annotated[int, Field(ge=0, le=1)]
    removed_messages: Annotated[int, Field(ge=0, le=16)]
    removed_artifacts: Annotated[int, Field(ge=0, le=50)]
    removed_artifact_bytes: Annotated[int, Field(ge=0, le=MAX_SNAPSHOT_BYTES)]
    removed_snapshot_bytes: Annotated[int, Field(ge=0, le=MAX_SNAPSHOT_BYTES)]
    published_json_untouched: Literal[True] = True

    @model_validator(mode="after")
    def exact_result(self) -> Self:
        factor = int(self.status == "deleted")
        if (
            self.prune_sha256 != digest(canonical_bytes(self.plan))
            or self.removed_sessions != factor
            or self.removed_messages != factor * self.plan.selection.messages
            or self.removed_artifacts != factor * self.plan.artifacts
            or self.removed_artifact_bytes != factor * self.plan.artifact_bytes
            or self.removed_snapshot_bytes
            != factor * self.plan.selection.snapshot_bytes
        ):
            raise ValueError("prune receipt does not match its selected state")
        return self


def _file_identity(root: int, name: str) -> PruneFileIdentity:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
    try:
        validate_private_storage(fd)
        info = os.fstat(fd)
        return PruneFileIdentity(device=info.st_dev, inode=info.st_ino)
    finally:
        os.close(fd)


class PruneStore(SQLiteConversationStore):
    _selected_database: PruneFileIdentity | None = None

    @property
    def database_identity(self) -> PruneFileIdentity:
        if self._selected_database is None:
            raise ValueError("selected prune database is unavailable")
        return self._selected_database

    def session_active(self, session_id: str) -> bool:
        return retention_session_active(self._root, session_id)

    @contextmanager
    def transaction(self, *, write: bool = False) -> Generator[sqlite3.Connection]:
        """Keep a shared prune transaction on this handle; caller owns consent."""
        if write:
            self._open_database(create=False, writable=True)
        db = self._connection()
        with conversation_transaction(db, write=write):
            yield db

    def _open_database(self, *, create: bool, writable: bool) -> None:
        if create:
            raise ValueError("pruning cannot create conversation storage")
        before = _file_identity(self._root, DATABASE)
        if self._selected_database is not None and before != self._selected_database:
            raise ValueError("selected prune database changed")
        super()._open_database(create=False, writable=writable)
        if _file_identity(self._root, DATABASE) != before:
            raise ValueError("selected prune database changed")
        self._selected_database = before

    def validate_location(self, location: TransferLocation) -> PruneFileIdentity:
        validate_private_storage(self._root, directory=True)
        validate_private_storage(self._lock)
        if inspect_storage_location(Path(location.path)) != location:
            raise ValueError("selected prune directory changed")
        if _file_identity(self._root, DATABASE) != self._selected_database:
            raise ValueError("selected prune database changed")
        info = os.fstat(self._lock)
        lock = PruneFileIdentity(device=info.st_dev, inode=info.st_ino)
        if _file_identity(self._root, f"{self.session_id}.lock") != lock:
            raise ValueError("selected prune session lock changed")
        return lock

    def _read_plan(
        self,
        db: sqlite3.Connection,
        location: TransferLocation,
        policy: RetentionPolicy,
        *,
        expected: PrunePlan | None = None,
    ) -> PrunePlan:
        self.validate_location(location)
        retention = read_retention_plan(
            db,
            location,
            self.workspace,
            policy,
            activity=lambda sid: (
                False
                if sid == self.session_id
                else retention_session_active(self._root, sid)
            ),
        )
        if expected is not None and retention != expected.retention:
            raise ValueError("prune selection changed; preview again")
        return self.verify_selection(db, retention)

    def verify_selection(
        self, db: sqlite3.Connection, retention: RetentionPlan
    ) -> PrunePlan:
        """Verify one selection in the caller's locked metadata transaction."""
        location = retention.storage
        lock = self.validate_location(location)
        selected = next(
            (
                entry
                for entry in retention.sessions
                if entry.summary.session_id == self.session_id
            ),
            None,
        )
        if selected is None or selected.disposition != "candidate":
            raise ValueError(
                "selected session is absent or protected by retention policy"
            )
        snapshot = self._load(db)
        sizes = db.execute(
            "SELECT length(payload) FROM artifacts WHERE sid=? LIMIT 51",
            (self.session_id,),
        ).fetchall()
        if self._selected_database is None:
            raise ValueError("selected prune database is unavailable")
        result = PrunePlan(
            retention=retention,
            session_id=self.session_id,
            snapshot_sha256=snapshot.sha256,
            database=self._selected_database,
            lock=lock,
            artifacts=len(sizes),
            artifact_bytes=sum(size for (size,) in sizes),
        )
        self.validate_location(location)
        return result

    def plan(self, location: TransferLocation, policy: RetentionPolicy) -> PrunePlan:
        db = self._connection()
        with conversation_transaction(db):
            return self._read_plan(db, location, policy)

    def _delete_selected(self, db: sqlite3.Connection) -> None:
        db.execute("DELETE FROM sessions WHERE sid=?", (self.session_id,))
        db.execute("UPDATE metadata SET generation=generation+1 WHERE id=1")

    def apply(self, plan: PrunePlan) -> None:
        self.validate_location(plan.retention.storage)
        self._open_database(create=False, writable=True)
        db = self._connection()
        with conversation_transaction(db, write=True):
            current = self._read_plan(
                db, plan.retention.storage, plan.retention.policy, expected=plan
            )
            if current != plan:
                raise ValueError("prune selection changed; preview again")
            self._delete_selected(db)
            self.validate_location(plan.retention.storage)
        self._deleted = True


def prune_session(
    root: Path,
    workspace: Path,
    session_id: str,
    *,
    before_ns: int,
    keep_newest: int = 20,
    expected_sha256: str | None = None,
    apply: bool = False,
) -> PruneReceipt:
    """Preview a full-state selection, or explicitly delete it after revalidation.

    Both modes start read-only under the selected session lock. Only exact prune
    consent allows a writable reopen; policy and state are checked again under
    BEGIN IMMEDIATE before the session and its cascading records are removed.
    """
    if type(apply) is not bool:
        raise ValueError("invalid prune apply mode")
    try:
        sid = TypeAdapter[str](SessionID).validate_python(session_id)
        expected = (
            None
            if expected_sha256 is None
            else TypeAdapter[str](Digest).validate_python(expected_sha256)
        )
        policy = RetentionPolicy(before_ns=before_ns, keep_newest=keep_newest)
    except ValueError:
        raise ValueError("invalid prune session ID, policy or expected hash") from None
    if apply and expected is None:
        raise ValueError(
            "--apply requires --expected-sha256 from a session-prune preview"
        )
    location = inspect_storage_location(root)
    with PruneStore(
        root,
        sid,
        workspace,
        create=False,
        require_workspace=False,
        writable=False,
        expected_root_identity=location.identity,
    ) as store:
        plan = store.plan(location, policy)
        prune_hash = digest(canonical_bytes(plan))
        if expected is not None and prune_hash != expected:
            raise ValueError("prune selection changed; preview again")
        if apply:
            store.apply(plan)
    factor = int(apply)
    return PruneReceipt(
        status="deleted" if apply else "planned",
        prune_sha256=prune_hash,
        plan=plan,
        removed_sessions=factor,
        removed_messages=factor * plan.selection.messages,
        removed_artifacts=factor * plan.artifacts,
        removed_artifact_bytes=factor * plan.artifact_bytes,
        removed_snapshot_bytes=factor * plan.selection.snapshot_bytes,
    )
