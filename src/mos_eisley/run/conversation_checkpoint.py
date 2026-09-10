"""Derived, bounded resume metadata built only from a validated full state."""

from collections.abc import Sequence
from typing import Annotated

from pydantic import Field

from mos_eisley.conversation import ConversationState, Status
from mos_eisley.core.models import Contract, Digest, digest


class EntryCheckpoint(Contract):
    status: Status
    review: bool
    steering_for: Annotated[int | None, Field(ge=0, le=15)] = None
    bytes: Annotated[int, Field(ge=1, le=128_000)]


class ResumeCheckpoint(Contract):
    header_sha256: Digest
    header_bytes: Annotated[int, Field(ge=1, le=128_000)]
    entries: Annotated[tuple[EntryCheckpoint, ...], Field(max_length=16)]


def resume_checkpoint(
    state: ConversationState, header: bytes, entries: Sequence[bytes]
) -> ResumeCheckpoint:
    return ResumeCheckpoint(
        header_sha256=digest(header),
        header_bytes=len(header),
        entries=tuple(
            EntryCheckpoint(
                status=entry.status,
                review=entry.review_packet is not None,
                steering_for=entry.steering_for,
                bytes=len(payload),
            )
            for entry, payload in zip(state.entries, entries, strict=True)
        ),
    )
