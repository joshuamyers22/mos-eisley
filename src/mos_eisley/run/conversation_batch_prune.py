"""Bounded, explicit retention selection with one atomic SQLite deletion."""

import sqlite3
from contextlib import ExitStack
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from mos_eisley.conversation_limits import MAX_SNAPSHOT_BYTES
from mos_eisley.conversation_state import SessionID
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.conversation_prune import (
    PruneFileIdentity,
    PrunePlan,
    PruneStore,
)
from mos_eisley.run.conversation_retention import (
    RetentionPlan,
    RetentionPolicy,
    read_retention_plan,
)
from mos_eisley.run.conversation_store import ConversationSummary
from mos_eisley.run.conversation_transfer import (
    TransferLocation,
    inspect_storage_location,
)

MAX_BATCH_PRUNE_SESSIONS = 32
MAX_BATCH_PRUNE_BYTES = 64 * 1024 * 1024
BatchSessionIDs = Annotated[
    tuple[SessionID, ...], Field(min_length=1, max_length=MAX_BATCH_PRUNE_SESSIONS)
]


class BatchPruneTarget(Contract):
    session_id: SessionID
    snapshot_sha256: Digest
    lock: PruneFileIdentity
    artifacts: Annotated[int, Field(ge=0, le=50)]
    artifact_bytes: Annotated[int, Field(ge=0, le=MAX_SNAPSHOT_BYTES)]


class BatchPrunePlan(Contract):
    schema_version: Literal[1] = 1
    operation: Literal["delete_sqlite_sessions"] = "delete_sqlite_sessions"
    verification: Literal["selected_full_states"] = "selected_full_states"
    retention: RetentionPlan
    database: PruneFileIdentity
    sessions: Annotated[
        tuple[BatchPruneTarget, ...],
        Field(min_length=1, max_length=MAX_BATCH_PRUNE_SESSIONS),
    ]

    @property
    def selections(self) -> tuple[ConversationSummary, ...]:
        return tuple(
            PrunePlan(
                retention=self.retention,
                database=self.database,
                **target.model_dump(),
            ).selection
            for target in self.sessions
        )

    @model_validator(mode="after")
    def exact_selection(self) -> Self:
        ids = tuple(target.session_id for target in self.sessions)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("batch prune IDs must be unique and sorted")
        if (
            sum(summary.snapshot_bytes for summary in self.selections)
            > MAX_BATCH_PRUNE_BYTES
            or sum(target.artifact_bytes for target in self.sessions)
            > MAX_BATCH_PRUNE_BYTES
        ):
            raise ValueError("batch prune exceeds the 64 MB logical byte limit")
        return self


class BatchPruneReceipt(Contract):
    schema_version: Literal[1] = 1
    status: Literal["planned", "deleted"]
    batch_prune_sha256: Digest
    plan: BatchPrunePlan
    removed_sessions: Annotated[int, Field(ge=0, le=MAX_BATCH_PRUNE_SESSIONS)]
    removed_messages: Annotated[int, Field(ge=0, le=MAX_BATCH_PRUNE_SESSIONS * 16)]
    removed_artifacts: Annotated[int, Field(ge=0, le=MAX_BATCH_PRUNE_SESSIONS * 50)]
    removed_artifact_bytes: Annotated[int, Field(ge=0, le=MAX_BATCH_PRUNE_BYTES)]
    removed_snapshot_bytes: Annotated[int, Field(ge=0, le=MAX_BATCH_PRUNE_BYTES)]
    published_json_untouched: Literal[True] = True

    @model_validator(mode="after")
    def exact_result(self) -> Self:
        factor = int(self.status == "deleted")
        if (
            self.batch_prune_sha256 != digest(canonical_bytes(self.plan))
            or self.removed_sessions != factor * len(self.plan.sessions)
            or self.removed_messages
            != factor * sum(summary.messages for summary in self.plan.selections)
            or self.removed_artifacts
            != factor * sum(target.artifacts for target in self.plan.sessions)
            or self.removed_artifact_bytes
            != factor * sum(target.artifact_bytes for target in self.plan.sessions)
            or self.removed_snapshot_bytes
            != factor * sum(summary.snapshot_bytes for summary in self.plan.selections)
        ):
            raise ValueError("batch prune receipt does not match its selection")
        return self


def validate_locations(
    stores: tuple[PruneStore, ...], location: TransferLocation
) -> None:
    for store in stores:
        store.validate_location(location)


def _read_batch_plan(
    db: sqlite3.Connection,
    stores: tuple[PruneStore, ...],
    location: TransferLocation,
    policy: RetentionPolicy,
    *,
    expected: BatchPrunePlan | None = None,
) -> BatchPrunePlan:
    validate_locations(stores, location)
    first = stores[0]
    selected_ids = frozenset(store.session_id for store in stores)
    retention = read_retention_plan(
        db,
        location,
        first.workspace,
        policy,
        activity=lambda sid: (
            False if sid in selected_ids else first.session_active(sid)
        ),
    )
    if expected is not None and retention != expected.retention:
        raise ValueError("batch prune selection changed; preview again")
    selected = tuple(
        entry
        for entry in retention.sessions
        if entry.summary.session_id in selected_ids
    )
    if len(selected) != len(stores) or any(
        entry.disposition != "candidate" for entry in selected
    ):
        raise ValueError(
            "batch prune session is absent or protected by retention policy"
        )
    if sum(entry.summary.snapshot_bytes for entry in selected) > MAX_BATCH_PRUNE_BYTES:
        raise ValueError("batch prune exceeds the 64 MB logical byte limit")
    targets: list[BatchPruneTarget] = []
    for store in stores:
        verified = store.verify_selection(db, retention)
        if verified.database != first.database_identity:
            raise ValueError("batch prune database changed")
        targets.append(
            BatchPruneTarget(
                session_id=verified.session_id,
                snapshot_sha256=verified.snapshot_sha256,
                lock=verified.lock,
                artifacts=verified.artifacts,
                artifact_bytes=verified.artifact_bytes,
            )
        )
    result = BatchPrunePlan(
        retention=retention, database=first.database_identity, sessions=tuple(targets)
    )
    validate_locations(stores, location)
    return result


def _delete_batch(db: sqlite3.Connection, plan: BatchPrunePlan) -> None:
    for target in plan.sessions:
        db.execute("DELETE FROM sessions WHERE sid=?", (target.session_id,))
    db.execute("UPDATE metadata SET generation=generation+1 WHERE id=1")


def _apply_batch(stores: tuple[PruneStore, ...], plan: BatchPrunePlan) -> None:
    location = plan.retention.storage
    validate_locations(stores, location)
    first = stores[0]
    with first.transaction(write=True) as db:
        current = _read_batch_plan(
            db, stores, location, plan.retention.policy, expected=plan
        )
        if current != plan:
            raise ValueError("batch prune selection changed; preview again")
        _delete_batch(db, plan)
        validate_locations(stores, location)


def prune_sessions(
    root: Path,
    workspace: Path,
    session_ids: tuple[str, ...],
    *,
    before_ns: int,
    keep_newest: int = 20,
    expected_sha256: str | None = None,
    apply: bool = False,
) -> BatchPruneReceipt:
    """Lock all explicit IDs and verify every selection before atomic deletion."""
    if type(apply) is not bool:
        raise ValueError("invalid batch prune apply mode")
    try:
        ids = TypeAdapter[tuple[str, ...]](BatchSessionIDs).validate_python(session_ids)
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate batch prune session ID")
        expected = (
            None
            if expected_sha256 is None
            else TypeAdapter[str](Digest).validate_python(expected_sha256)
        )
        policy = RetentionPolicy(before_ns=before_ns, keep_newest=keep_newest)
    except ValueError:
        raise ValueError("invalid batch prune IDs, policy or expected hash") from None
    if apply and expected is None:
        raise ValueError(
            "--apply requires --expected-sha256 from a session-prune-batch preview"
        )
    location = inspect_storage_location(root)
    with ExitStack() as stack:
        stores = tuple(
            stack.enter_context(
                PruneStore(
                    root,
                    sid,
                    workspace,
                    create=False,
                    require_workspace=False,
                    writable=False,
                    expected_root_identity=location.identity,
                )
            )
            for sid in sorted(ids)
        )
        with stores[0].transaction() as db:
            plan = _read_batch_plan(db, stores, location, policy)
        plan_hash = digest(canonical_bytes(plan))
        if expected is not None and plan_hash != expected:
            raise ValueError("batch prune selection changed; preview again")
        if apply:
            _apply_batch(stores, plan)
    factor = int(apply)
    return BatchPruneReceipt(
        status="deleted" if apply else "planned",
        batch_prune_sha256=plan_hash,
        plan=plan,
        removed_sessions=factor * len(plan.sessions),
        removed_messages=factor * sum(summary.messages for summary in plan.selections),
        removed_artifacts=factor * sum(target.artifacts for target in plan.sessions),
        removed_artifact_bytes=factor
        * sum(target.artifact_bytes for target in plan.sessions),
        removed_snapshot_bytes=factor
        * sum(summary.snapshot_bytes for summary in plan.selections),
    )
