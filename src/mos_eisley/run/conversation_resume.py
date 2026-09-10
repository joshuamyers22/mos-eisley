"""Read-only inspection of a verified candidate working set for SQLite resume."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from mos_eisley.conversation import SessionID
from mos_eisley.conversation_limits import DEFAULT_SNAPSHOT_BYTES, SnapshotByteLimit
from mos_eisley.core.models import Contract, Digest, digest
from mos_eisley.run.conversation_checkpoint import ResumeCheckpoint
from mos_eisley.run.conversation_sqlite import (
    PackedPart,
    read_sqlite_session_index,
    sqlite_read_transaction,
)
from mos_eisley.run.conversation_transcript import (
    TranscriptEntry,
    decode_transcript_entry,
)

MAX_RESUME_INSPECTION_BYTES = 512_000


class ResumeHeader(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["recorded_conversation"] = "recorded_conversation"
    session_id: SessionID
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    cassette_sha256: Digest
    revision: Annotated[int, Field(ge=0)] = 0
    exchanges_consumed: Annotated[int, Field(ge=0, le=16)] = 0
    memory_disabled: bool = False
    builtin_recording: bool = False
    snapshot_max_bytes: SnapshotByteLimit | None = None


class HeaderArtifact(Contract):
    field: Literal["memory", "retained_cassette"]
    sha256: Digest
    bytes: Annotated[int, Field(ge=1, le=32_000_000)]


class ResumeInspection(Contract):
    session_id: SessionID
    snapshot_sha256: Digest
    generation: Annotated[int, Field(ge=0)]
    header: ResumeHeader
    header_artifacts: tuple[HeaderArtifact, ...]
    total_messages: Annotated[int, Field(ge=0, le=16)]
    omitted_messages: Annotated[int, Field(ge=0, le=16)]
    pending_positions: tuple[int, ...]
    interrupted_on_resume: tuple[int, ...]
    entries: tuple[TranscriptEntry, ...]
    record_bytes: Annotated[int, Field(ge=0, le=MAX_RESUME_INSPECTION_BYTES)]
    selection_policy: Literal["recent-4-unfinished-steering-v1"] = (
        "recent-4-unfinished-steering-v1"
    )
    read_only: Literal[True] = True
    notice: Literal[
        "Inspection only. Normal resume still loads and verifies the full state."
    ] = "Inspection only. Normal resume still loads and verifies the full state."


def selected_positions(checkpoint: ResumeCheckpoint, consumed: int) -> list[int]:
    entries = checkpoint.entries
    selected = set(range(max(0, len(entries) - 4), len(entries)))
    targets: set[int] = set()
    for position, entry in enumerate(entries):
        if entry.status in {"queued", "running"}:
            selected.add(position)
        target = entry.steering_for
        if target is not None:
            if (
                entry.review
                or target >= position
                or entries[target].status == "queued"
                or entries[target].review
            ):
                raise ValueError("invalid resume checkpoint steering")
            targets.add(target)
    started = [
        entry for entry in entries if entry.status != "queued" and not entry.review
    ]
    dispatched = sum(entry.status != "cancelled" for entry in started) + sum(
        entries[position].status == "cancelled" for position in targets
    )
    if (
        not dispatched <= consumed <= len(started)
        or sum(entry.status == "running" for entry in entries) > 1
    ):
        raise ValueError("invalid resume checkpoint progress")
    # Earlier-only links terminate; include complete ancestry for every selected
    # message, including completed targets. This is inspection, not model context.
    for position in sorted(selected, reverse=True):
        target = entries[position].steering_for
        while target is not None:
            selected.add(target)
            target = entries[target].steering_for
    return sorted(selected)


def inspect_sqlite_resume(
    root: Path,
    session_id: str,
    workspace: Path,
    *,
    expected_sha256: str | None = None,
) -> ResumeInspection:
    sid = TypeAdapter[str](SessionID).validate_python(session_id)
    expected = (
        None
        if expected_sha256 is None
        else TypeAdapter[str](Digest).validate_python(expected_sha256)
    )
    if workspace.exists() and not workspace.is_dir():
        raise ValueError("conversation workspace must be a directory")
    with sqlite_read_transaction(root) as (db, store_id, generation):
        index = read_sqlite_session_index(db, sid, str(workspace.resolve()))
        summary, checkpoint = index.summary, index.resume_checkpoint
        if expected is not None and expected != summary.snapshot_sha256:
            raise ValueError("selected conversation changed; inspect again")
        if checkpoint is None or index.entry_sha256 is None:
            raise ValueError(
                "resume checkpoint is unavailable; use session-transcript "
                f"{sid} --prepare --expected-sha256 {summary.snapshot_sha256} "
                "with this storage and workspace"
            )
        if (
            len(checkpoint.entries) != summary.messages
            or len(index.entry_sha256) != summary.messages
            or sum(e.status == "completed" for e in checkpoint.entries)
            != summary.completed
            or sum(e.status == "queued" for e in checkpoint.entries) != summary.pending
        ):
            raise ValueError("invalid resume checkpoint counts")
        row = db.execute(
            "SELECT CASE WHEN length(header)=? THEN header END FROM sessions "
            "WHERE sid=?",
            (checkpoint.header_bytes, sid),
        ).fetchone()
        if (
            row is None
            or not isinstance(row[0], bytes)
            or digest(row[0]) != checkpoint.header_sha256
        ):
            raise ValueError("resume header integrity mismatch")
        try:
            packed = PackedPart.model_validate_json(row[0])
            header = ResumeHeader.model_validate(packed.body)
        except ValueError:
            raise ValueError("invalid resume header schema") from None
        if (
            header.session_id != sid
            or header.owner_uid != index.owner_uid
            or header.workspace != index.workspace
            or header.revision != summary.revision
            or (header.snapshot_max_bytes or DEFAULT_SNAPSHOT_BYTES)
            != summary.snapshot_max_bytes
            or not packed.refs.keys() <= {"memory", "retained_cassette"}
            or (header.memory_disabled and "memory" in packed.refs)
            or (header.builtin_recording and "retained_cassette" not in packed.refs)
            or (
                "retained_cassette" in packed.refs
                and packed.refs["retained_cassette"] != header.cassette_sha256
            )
        ):
            raise ValueError("resume header identity or references mismatch")
        positions = selected_positions(checkpoint, header.exchanges_consumed)
        size = checkpoint.header_bytes + sum(
            checkpoint.entries[position].bytes for position in positions
        )
        if size > MAX_RESUME_INSPECTION_BYTES:
            raise ValueError(
                f"resume inspection needs {size} record bytes; limit is "
                f"{MAX_RESUME_INSPECTION_BYTES}. Inspect smaller transcript pages."
            )
        header_artifacts: list[HeaderArtifact] = []
        for field, sha in sorted(packed.refs.items()):
            field = TypeAdapter[Literal["memory", "retained_cassette"]](
                Literal["memory", "retained_cassette"]
            ).validate_python(field)
            row = db.execute(
                "SELECT length(payload) FROM artifacts WHERE sid=? AND sha=?",
                (sid, sha),
            ).fetchone()
            if row is None:
                raise ValueError("missing resume header artifact")
            header_artifacts.append(
                HeaderArtifact(field=field, sha256=sha, bytes=row[0])
            )
        entries: list[TranscriptEntry] = []
        for position in positions:
            detail = checkpoint.entries[position]
            row = db.execute(
                "SELECT CASE WHEN length(payload)=? THEN payload END, revision "
                "FROM entries WHERE sid=? AND position=?",
                (detail.bytes, sid, position),
            ).fetchone()
            if (
                row is None
                or not isinstance(row[0], bytes)
                or not (0 <= row[1] <= summary.revision)
            ):
                raise ValueError("resume message missing or outside record bounds")
            entry = decode_transcript_entry(
                db, index, position, row[0], store_id=store_id, generation=generation
            )
            if (
                entry.content.status != detail.status
                or entry.content.steering_for != detail.steering_for
                or any(ref.field == "review_packet" for ref in entry.artifacts)
                != detail.review
            ):
                raise ValueError("resume message disagrees with checkpoint")
            entries.append(entry)
        return ResumeInspection(
            session_id=sid,
            snapshot_sha256=summary.snapshot_sha256,
            generation=generation,
            header=header,
            header_artifacts=tuple(header_artifacts),
            total_messages=summary.messages,
            omitted_messages=summary.messages - len(entries),
            pending_positions=tuple(
                i
                for i, entry in enumerate(checkpoint.entries)
                if entry.status == "queued"
            ),
            interrupted_on_resume=tuple(
                i
                for i, entry in enumerate(checkpoint.entries)
                if entry.status == "running"
            ),
            entries=tuple(entries),
            record_bytes=size,
        )
