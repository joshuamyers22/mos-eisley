"""Read-only workspace retention policy over a bounded SQLite metadata snapshot."""

import fcntl
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.conversation_state import SessionID
from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.run.conversation_sqlite import (
    read_sqlite_session_index,
    sqlite_read_transaction,
)
from mos_eisley.run.conversation_store import (
    ConversationSummary,
    validate_private_storage,
)
from mos_eisley.run.conversation_transfer import (
    TransferLocation,
    inspect_storage_location,
)

MAX_RETENTION_SESSIONS = 1000
MAX_TIMESTAMP_NS = 2**63 - 1
RetentionReason = Literal[
    "keep_newest", "not_before_cutoff", "active", "noncompleted_messages"
]


def retention_cutoff(value: str) -> int:
    """Parse an explicit UTC second, without floating-point timestamp rounding."""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError
        delta = parsed - datetime(1970, 1, 1, tzinfo=UTC)
        result = (delta.days * 86_400 + delta.seconds) * 1_000_000_000
        if not 0 <= result <= MAX_TIMESTAMP_NS:
            raise ValueError
    except ValueError:
        raise ValueError(
            "--before requires a UTC timestamp: YYYY-MM-DDTHH:MM:SSZ"
        ) from None
    return result


class RetentionPolicy(Contract):
    before_ns: Annotated[int, Field(ge=0, le=MAX_TIMESTAMP_NS)]
    keep_newest: Annotated[int, Field(ge=0, le=MAX_RETENTION_SESSIONS)] = 20


def _reasons(
    summary: ConversationSummary, position: int, policy: RetentionPolicy
) -> tuple[RetentionReason, ...]:
    reasons: list[RetentionReason] = []
    if position < policy.keep_newest:
        reasons.append("keep_newest")
    if summary.modified_ns >= policy.before_ns:
        reasons.append("not_before_cutoff")
    if summary.active:
        reasons.append("active")
    if summary.completed != summary.messages:
        reasons.append("noncompleted_messages")
    return tuple(reasons)


class RetentionEntry(Contract):
    summary: ConversationSummary
    disposition: Literal["candidate", "retain"]
    reasons: Annotated[tuple[RetentionReason, ...], Field(max_length=4)]


class RetentionPlan(Contract):
    schema_version: Literal[1] = 1
    backend: Literal["sqlite"] = "sqlite"
    storage: TransferLocation
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    store_id: SessionID
    generation: Annotated[int, Field(ge=0)]
    policy: RetentionPolicy
    sessions: Annotated[
        tuple[RetentionEntry, ...], Field(max_length=MAX_RETENTION_SESSIONS)
    ]

    @model_validator(mode="after")
    def ordered_policy_results(self) -> Self:
        keys = tuple(
            (entry.summary.modified_ns, entry.summary.session_id)
            for entry in self.sessions
        )
        if keys != tuple(sorted(keys, reverse=True)) or len(
            {sid for _, sid in keys}
        ) != len(keys):
            raise ValueError("retention sessions must be unique and ordered by recency")
        for position, entry in enumerate(self.sessions):
            if entry.summary.completed + entry.summary.pending > entry.summary.messages:
                raise ValueError("inconsistent retention message counts")
            reasons = _reasons(entry.summary, position, self.policy)
            if entry.reasons != reasons or entry.disposition != (
                "retain" if reasons else "candidate"
            ):
                raise ValueError("retention result does not match its policy")
        return self


class RetentionPreview(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["preview"] = "preview"
    verification: Literal["index_metadata"] = "index_metadata"
    deletion_authorized: Literal[False] = False
    plan_sha256: Digest
    plan: RetentionPlan
    candidate_sessions: Annotated[int, Field(ge=0, le=MAX_RETENTION_SESSIONS)]
    retained_sessions: Annotated[int, Field(ge=0, le=MAX_RETENTION_SESSIONS)]
    candidate_snapshot_bytes: Annotated[int, Field(ge=0)]
    retained_snapshot_bytes: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def exact_counts(self) -> Self:
        candidates = tuple(
            item for item in self.plan.sessions if item.disposition == "candidate"
        )
        retained = tuple(
            item for item in self.plan.sessions if item.disposition == "retain"
        )
        if (
            self.plan_sha256 != digest(canonical_bytes(self.plan))
            or self.candidate_sessions != len(candidates)
            or self.retained_sessions != len(retained)
            or self.candidate_snapshot_bytes
            != sum(item.summary.snapshot_bytes for item in candidates)
            or self.retained_snapshot_bytes
            != sum(item.summary.snapshot_bytes for item in retained)
        ):
            raise ValueError("retention preview hash or counts do not match its plan")
        return self


def _active(root: int, sid: str) -> bool:
    lock = os.open(
        f"{sid}.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root
    )
    try:
        validate_private_storage(lock)
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True
    finally:
        os.close(lock)


def preview_retention(
    root: Path,
    workspace: Path,
    *,
    before_ns: int,
    keep_newest: int = 20,
) -> RetentionPreview:
    """Classify indexed sessions, never opening transcript or artifact bodies.

    The hash fingerprints this observation; it is not deletion authorization.
    Database metadata uses one read transaction. Activity probes are momentary,
    with their locks released immediately, and cannot reserve a future deletion.
    """
    policy = RetentionPolicy(before_ns=before_ns, keep_newest=keep_newest)
    if workspace.exists() and not workspace.is_dir():
        raise ValueError("conversation workspace must be a directory")
    selected_workspace = str(workspace.resolve())
    location = inspect_storage_location(root)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        validate_private_storage(directory, directory=True)
        info = os.fstat(directory)
        if (info.st_dev, info.st_ino) != location.identity:
            raise ValueError("selected retention directory changed")
        with sqlite_read_transaction(root) as (db, store_id, generation):
            if inspect_storage_location(root) != location:
                raise ValueError("selected retention directory changed")
            rows = db.execute(
                "SELECT CASE WHEN length(sid)=32 AND length(record_sha)=64 "
                "THEN sid END FROM sessions WHERE workspace=? "
                "ORDER BY modified_ns DESC, sid DESC LIMIT ?",
                (selected_workspace, MAX_RETENTION_SESSIONS + 1),
            ).fetchall()
            if len(rows) > MAX_RETENTION_SESSIONS:
                raise ValueError(
                    "retention preview exceeds the 1000-session workspace limit"
                )
            if any(type(sid) is not str or len(sid) != 32 for (sid,) in rows):
                raise ValueError("invalid retention catalog identity or checksum size")
            entries: list[RetentionEntry] = []
            for position, (sid,) in enumerate(rows):
                summary = read_sqlite_session_index(db, sid, selected_workspace).summary
                summary = summary.model_copy(update={"active": _active(directory, sid)})
                reasons = _reasons(summary, position, policy)
                entries.append(
                    RetentionEntry(
                        summary=summary,
                        disposition="retain" if reasons else "candidate",
                        reasons=reasons,
                    )
                )
            if inspect_storage_location(root) != location:
                raise ValueError("selected retention directory changed")
            plan = RetentionPlan(
                storage=location,
                owner_uid=os.getuid(),
                workspace=selected_workspace,
                store_id=store_id,
                generation=generation,
                policy=policy,
                sessions=tuple(entries),
            )
    finally:
        os.close(directory)
    return RetentionPreview(
        plan_sha256=digest(canonical_bytes(plan)),
        plan=plan,
        candidate_sessions=sum(item.disposition == "candidate" for item in entries),
        retained_sessions=sum(item.disposition == "retain" for item in entries),
        candidate_snapshot_bytes=sum(
            item.summary.snapshot_bytes
            for item in entries
            if item.disposition == "candidate"
        ),
        retained_snapshot_bytes=sum(
            item.summary.snapshot_bytes
            for item in entries
            if item.disposition == "retain"
        ),
    )
