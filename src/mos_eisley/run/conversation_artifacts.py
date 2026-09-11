"""Explicit bounded expansion of one snapshot-bound message artifact."""

import base64
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue

from mos_eisley.conversation import ConversationMemoryContext, SessionID
from mos_eisley.conversation_review import ConversationReviewPacket
from mos_eisley.core.models import Contract, Digest, ReviewResult, digest
from mos_eisley.run.conversation_sqlite import (
    MAX_RECORD_BYTES,
    PackedPart,
    read_sqlite_session_index,
    sqlite_read_transaction,
)

ArtifactField = Literal["memory_context", "review_packet", "review_result"]
DEFAULT_ARTIFACT_BYTES = 512_000
MAX_ARTIFACT_BYTES = 32_000_000


class ArtifactSelection(Contract):
    store_id: SessionID
    owner_uid: Annotated[int, Field(ge=0)]
    workspace: Annotated[str, Field(min_length=1, max_length=4096)]
    session_id: SessionID
    snapshot_sha256: Digest
    generation: Annotated[int, Field(ge=0)]
    position: Annotated[int, Field(ge=0, le=15)]
    field: ArtifactField
    sha256: Digest
    bytes: Annotated[int, Field(ge=1, le=MAX_ARTIFACT_BYTES)]


class ArtifactContent(Contract):
    session_id: SessionID
    snapshot_sha256: Digest
    revision: Annotated[int, Field(ge=0)]
    position: Annotated[int, Field(ge=0, le=15)]
    field: ArtifactField
    sha256: Digest
    bytes: Annotated[int, Field(ge=1, le=MAX_ARTIFACT_BYTES)]
    content: dict[str, JsonValue]


def read_sqlite_artifact(
    root: Path,
    workspace: Path,
    selection: str,
    *,
    max_bytes: int = DEFAULT_ARTIFACT_BYTES,
    expected_session_id: str | None = None,
) -> ArtifactContent:
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_ARTIFACT_BYTES:
        raise ValueError("artifact byte limit must be between 1 and 32000000")
    if len(selection) > 32_000:
        raise ValueError("invalid artifact selection")
    try:
        selected = ArtifactSelection.model_validate_json(
            base64.b64decode(selection, altchars=b"-_", validate=True)
        )
    except (ValueError, UnicodeError):
        raise ValueError("invalid artifact selection") from None
    if expected_session_id is not None and selected.session_id != expected_session_id:
        raise ValueError("artifact belongs to another session")
    if workspace.exists() and not workspace.is_dir():
        raise ValueError("conversation workspace must be a directory")
    with sqlite_read_transaction(root) as (db, store_id, generation):
        index = read_sqlite_session_index(
            db, selected.session_id, str(workspace.resolve())
        )
        if (
            selected.store_id != store_id
            or selected.owner_uid != index.owner_uid
            or selected.workspace != index.workspace
            or selected.generation != generation
            or selected.snapshot_sha256 != index.summary.snapshot_sha256
        ):
            raise ValueError("artifact selection is stale or foreign; reload history")
        if (
            index.entry_sha256 is None
            or len(index.entry_sha256) != index.summary.messages
            or selected.position >= index.summary.messages
        ):
            raise ValueError("artifact selection has no verified message index")
        row = db.execute(
            "SELECT CASE WHEN length(payload)<=? THEN payload END FROM entries "
            "WHERE sid=? AND position=?",
            (MAX_RECORD_BYTES, selected.session_id, selected.position),
        ).fetchone()
        if (
            row is None
            or not isinstance(row[0], bytes)
            or digest(row[0]) != index.entry_sha256[selected.position]
        ):
            raise ValueError("artifact message integrity mismatch")
        packed = PackedPart.model_validate_json(row[0])
        if packed.refs.get(selected.field) != selected.sha256:
            raise ValueError("artifact is not referenced by the selected message field")
        size = db.execute(
            "SELECT length(payload) FROM artifacts WHERE sid=? AND sha=?",
            (selected.session_id, selected.sha256),
        ).fetchone()
        if size is None or size[0] != selected.bytes:
            raise ValueError("selected artifact is missing or its size changed")
        if selected.bytes > max_bytes:
            raise ValueError(
                f"Artifact needs {selected.bytes} bytes; "
                f"expansion limit is {max_bytes}. "
                "Use session-artifact --max-bytes for an explicit larger limit."
            )
        payload = db.execute(
            "SELECT CASE WHEN length(payload)=? THEN payload END FROM artifacts "
            "WHERE sid=? AND sha=?",
            (selected.bytes, selected.session_id, selected.sha256),
        ).fetchone()[0]
        if not isinstance(payload, bytes) or digest(payload) != selected.sha256:
            raise ValueError("selected artifact integrity mismatch")
        try:
            model: ConversationMemoryContext | ConversationReviewPacket | ReviewResult
            if selected.field == "memory_context":
                model = ConversationMemoryContext.model_validate_json(payload)
                if model.memory is not None:
                    model.memory.validate_identity(
                        index.owner_uid, index.memory_project_root or index.workspace
                    )
            elif selected.field == "review_packet":
                model = ConversationReviewPacket.model_validate_json(payload)
            else:
                model = ReviewResult.model_validate_json(payload)
        except ValueError:
            raise ValueError(
                "selected artifact schema or memory identity is invalid"
            ) from None
        return ArtifactContent(
            session_id=selected.session_id,
            snapshot_sha256=selected.snapshot_sha256,
            revision=index.summary.revision,
            position=selected.position,
            field=selected.field,
            sha256=selected.sha256,
            bytes=selected.bytes,
            content=model.model_dump(mode="json"),
        )
