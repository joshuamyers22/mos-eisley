"""Bounded text pages with verified records and unexpanded artifact references."""

import base64
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from mos_eisley.conversation import SessionID, Status
from mos_eisley.core.agent import AgentUsage
from mos_eisley.core.models import Contract, Digest, Text, canonical_bytes, digest
from mos_eisley.run.conversation_sqlite import (
    MAX_RECORD_BYTES,
    PackedPart,
    read_sqlite_session_index,
    sqlite_read_transaction,
)

MAX_TRANSCRIPT_PAGE_BYTES = 512_000
ArtifactField = Literal["memory_context", "review_packet", "review_result"]


class TranscriptText(Contract):
    text: Text
    status: Status = "queued"
    answer: Text | None = None
    usage: AgentUsage | None = None
    steering_for: Annotated[int | None, Field(ge=0, le=15)] = None


class TranscriptArtifact(Contract):
    field: ArtifactField
    sha256: Digest
    bytes: Annotated[int, Field(ge=1, le=32_000_000)]


class TranscriptEntry(Contract):
    position: Annotated[int, Field(ge=0, le=15)]
    content: TranscriptText
    artifacts: tuple[TranscriptArtifact, ...]


class TranscriptCursor(Contract):
    store_id: SessionID
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    session_id: SessionID
    snapshot_sha256: Digest
    generation: Annotated[int, Field(ge=0)]
    position: Annotated[int, Field(ge=1, le=15)]


class TranscriptPage(Contract):
    session_id: SessionID
    snapshot_sha256: Digest
    revision: Annotated[int, Field(ge=0)]
    total_messages: Annotated[int, Field(ge=0, le=16)]
    entries: tuple[TranscriptEntry, ...]
    record_bytes: Annotated[int, Field(ge=0, le=MAX_TRANSCRIPT_PAGE_BYTES)]
    next_cursor: str | None = None


def read_sqlite_transcript(
    root: Path,
    session_id: str,
    workspace: Path,
    *,
    limit: int = 4,
    cursor: str | None = None,
) -> TranscriptPage:
    sid = TypeAdapter[str](SessionID).validate_python(session_id)
    if type(limit) is not int or not 1 <= limit <= 16:
        raise ValueError("transcript page size must be between 1 and 16")
    if workspace.exists() and not workspace.is_dir():
        raise ValueError("conversation workspace must be a directory")
    selected_workspace = str(workspace.resolve())
    selected = None
    if cursor is not None:
        if len(cursor) > 32_000:
            raise ValueError("invalid transcript cursor")
        try:
            selected = TranscriptCursor.model_validate_json(
                base64.b64decode(cursor, altchars=b"-_", validate=True)
            )
        except (ValueError, UnicodeError):
            raise ValueError("invalid transcript cursor") from None
    with sqlite_read_transaction(root) as (db, store_id, generation):
        index = read_sqlite_session_index(db, sid, selected_workspace)
        summary = index.summary
        if index.entry_sha256 is None:
            raise ValueError(
                "transcript index is unavailable; use session-transcript --prepare "
                "--expected-sha256 with the hash from sessions --storage-backend sqlite"
            )
        if len(index.entry_sha256) != summary.messages:
            raise ValueError("invalid transcript index count")
        if selected is not None and (
            selected.store_id != store_id
            or selected.owner_uid != index.owner_uid
            or selected.workspace != selected_workspace
            or selected.session_id != sid
            or selected.snapshot_sha256 != summary.snapshot_sha256
            or selected.generation != generation
            or selected.position >= summary.messages
        ):
            raise ValueError("transcript cursor is stale or foreign; restart reading")
        start = 0 if selected is None else selected.position
        # Only row lengths are read ahead. Payloads are fetched after admission to
        # the independent page byte budget; no header or artifact value is loaded.
        rows = db.execute(
            "SELECT position, length(payload), revision FROM entries WHERE sid=? "
            "AND position>=? ORDER BY position LIMIT ?",
            (sid, start, limit),
        ).fetchall()
        if len(rows) != min(limit, summary.messages - start):
            raise ValueError("missing transcript records")
        entries: list[TranscriptEntry] = []
        consumed = 0
        for offset, (position, size, revision) in enumerate(rows):
            if (
                position != start + offset
                or type(size) is not int
                or not 1 <= size <= MAX_RECORD_BYTES
                or type(revision) is not int
                or not 0 <= revision <= summary.revision
            ):
                raise ValueError("invalid transcript record bounds")
            if consumed + size > MAX_TRANSCRIPT_PAGE_BYTES:
                break
            payload = db.execute(
                "SELECT CASE WHEN length(payload)=? THEN payload END "
                "FROM entries WHERE sid=? AND position=?",
                (size, sid, position),
            ).fetchone()[0]
            if (
                not isinstance(payload, bytes)
                or digest(payload) != index.entry_sha256[position]
            ):
                raise ValueError("transcript record integrity mismatch")
            packed = PackedPart.model_validate_json(payload)
            content = TranscriptText.model_validate(packed.body)
            artifacts: list[TranscriptArtifact] = []
            for field, sha in sorted(packed.refs.items()):
                field = TypeAdapter[ArtifactField](ArtifactField).validate_python(field)
                artifact = db.execute(
                    "SELECT length(payload) FROM artifacts WHERE sid=? AND sha=?",
                    (sid, sha),
                ).fetchone()
                if artifact is None:
                    raise ValueError("missing transcript artifact")
                artifacts.append(
                    TranscriptArtifact(field=field, sha256=sha, bytes=artifact[0])
                )
            entries.append(
                TranscriptEntry(
                    position=position, content=content, artifacts=tuple(artifacts)
                )
            )
            consumed += size
        next_position = start + len(entries)
        token = None
        if next_position < summary.messages:
            token = base64.urlsafe_b64encode(
                canonical_bytes(
                    TranscriptCursor(
                        store_id=store_id,
                        owner_uid=index.owner_uid,
                        workspace=selected_workspace,
                        session_id=sid,
                        snapshot_sha256=summary.snapshot_sha256,
                        generation=generation,
                        position=next_position,
                    )
                )
            ).decode()
        return TranscriptPage(
            session_id=sid,
            snapshot_sha256=summary.snapshot_sha256,
            revision=summary.revision,
            total_messages=summary.messages,
            entries=tuple(entries),
            record_bytes=consumed,
            next_cursor=token,
        )
