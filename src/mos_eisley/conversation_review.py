"""Explicit recorded review packets; no conversation input crosses this boundary."""

import asyncio
from collections.abc import Callable
from typing import Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import (
    Brief,
    Contract,
    ReviewPolicy,
    ReviewResult,
    canonical_bytes,
)
from mos_eisley.project_guidance_review import PreparedGuidanceReview
from mos_eisley.providers.recorded import Cassette, RecordedReviewer
from mos_eisley.review.pipeline import review, validate_roster

MAX_REVIEW_PACKET_BYTES = 128_000
MAX_REVIEW_RESULT_BYTES = 256_000
REVIEW_PROMPT = "Review this change."
REVIEW_FOLLOWUP = "What should be fixed?"


class ConversationReviewPacket(Contract):
    schema_version: Literal[1, 2] = 1
    mode: Literal["recorded_conversation_review"] = "recorded_conversation_review"
    brief: Brief
    cassette: Cassette
    policy: ReviewPolicy = ReviewPolicy()
    guidance_review: PreparedGuidanceReview | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def bound_inputs(self) -> Self:
        if (self.schema_version == 2) != (self.guidance_review is not None):
            raise ValueError("Guided terminal reviews require packet schema 2.")
        if (
            self.guidance_review is not None
            and self.guidance_review.brief != self.brief
        ):
            raise ValueError("Terminal review guidance must match the exact brief.")
        if self.brief.brief_id != self.cassette.brief_id:
            raise ValueError("review cassette must match the explicit brief")
        validate_roster(tuple(r.critic for r in self.cassette.critics), self.policy)
        if self.policy.timeout_seconds > 10:
            raise ValueError("conversation review timeout cannot exceed ten seconds")
        if len(canonical_bytes(self)) > MAX_REVIEW_PACKET_BYTES:
            raise ValueError("conversation review packet exceeds byte limit")
        return self


async def run_conversation_review(
    packet: ConversationReviewPacket,
    *,
    validate_guidance: Callable[[], None] | None = None,
) -> ReviewResult:
    # Only the explicit packet is available here: never a controller or transcript.
    packet = ConversationReviewPacket.model_validate_json(packet.model_dump_json())
    if packet.guidance_review is not None:
        if validate_guidance is None:
            raise ValueError(
                "Guided review requires current policy selection for this launch."
            )
        validate_guidance()
    try:
        async with asyncio.timeout(25):
            result = await review(
                packet.brief,
                tuple(recording.critic for recording in packet.cassette.critics),
                RecordedReviewer(packet.cassette),
                packet.policy,
            )
    except Exception:
        raise ValueError("recorded conversation review failed") from None
    if len(canonical_bytes(result)) > MAX_REVIEW_RESULT_BYTES:
        raise ValueError("conversation review result exceeds byte limit")
    if packet.guidance_review is not None:
        assert validate_guidance is not None
        validate_guidance()
    return result


def review_summary(result: ReviewResult) -> str:
    """A labelled, bounded view; the complete result stays in the private snapshot."""
    verdict = result.verdict
    lines = [
        f"Recorded review for brief {verdict.brief_id}: {verdict.decision}.",
        f"Rationale: {verdict.rationale[:600]}",
        f"Required changes: {len(verdict.required_changes)}. "
        f"Findings: {len(verdict.findings)}.",
    ]
    for index, finding in enumerate(verdict.findings[:5], start=1):
        lines.extend(
            (
                f"{index}. [{finding.finding_id}] {finding.impact}: "
                f"{finding.location[:120]}",
                f"Finding: {finding.claim[:240]}",
                f"Evidence ({finding.evidence.source}): {finding.evidence.quote[:160]}",
                f"Suggested fix: {(finding.suggested_fix or 'Not supplied.')[:240]}",
            )
        )
    lines.append(
        "This summary shows at most five findings and short excerpts. "
        "The complete review is retained in the snapshot and JSON events. "
        "Recorded evidence does not establish live review quality or authorize changes."
    )
    return "\n".join(lines)
