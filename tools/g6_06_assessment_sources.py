"""Offline G606-05 source-review coverage screen; no outcome-store access."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.cohort_assessment_handoff import (
    FrozenR6AssessmentAnchor,
    OfflineR6AssessmentPacket,
    OfflineR6AssessmentResult,
    validate_offline_r6_assessment_handoff,
)
from mos_eisley.run.cohort_close_handoff import OfflineR5CloseResult
from mos_eisley.run.cohort_closeout import (
    CohortCloseoutPacket,
    FrozenCloseoutProtocol,
    TaskFollowupIndex,
)
from mos_eisley.run.store import private_write

BASE_KINDS: tuple[str, ...] = (
    "followup",
    "quality",
    "damage",
    "completion",
    "all_task_latency",
    "whole_task_cost",
    "stop_incident",
    "missingness",
    "independent_review",
)
COMPARISON_KINDS = ("baseline_registration", "comparison_design")
SourceKind = Literal[
    "followup",
    "quality",
    "damage",
    "completion",
    "all_task_latency",
    "whole_task_cost",
    "stop_incident",
    "missingness",
    "independent_review",
    "baseline_registration",
    "comparison_design",
]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("assessment source time must use explicit UTC")
    return value


class FollowupSourceIndex(Contract):
    schema_version: Literal[1] = 1
    followups: tuple[TaskFollowupIndex, ...]


class FrozenAssessmentSourceAnchor(Contract):
    """Separately retained expected digests and source-review roster."""

    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    r6_anchor_sha256: Digest
    r6_packet_sha256: Digest
    r6_result_sha256: Digest
    closeout_packet_sha256: Digest
    followup_index_sha256: Digest
    evidence_references_sha256: Digest
    upstream_handoff_sha256: Digest
    source_reviewer_id: Identifier
    final_reviewer_id: Identifier
    custodian_id: Identifier
    frozen_at: datetime
    valid_until: datetime

    @field_validator("frozen_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def ordered_window(self) -> Self:
        if (
            self.valid_until <= self.frozen_at
            or self.source_reviewer_id == self.final_reviewer_id
            or self.source_reviewer_id == self.custodian_id
        ):
            raise ValueError("assessment source anchor window or roles are invalid")
        return self


class SourceCoverageReview(Contract):
    kind: SourceKind
    artifact_sha256: Digest
    decision: Literal["accept", "reject", "unavailable"]
    producer_id: Identifier
    custodian_id: Identifier
    reviewer_id: Identifier
    roster_sha256: Digest
    covered_task_count: Annotated[int, Field(ge=0)]
    unknown_task_count: Annotated[int, Field(ge=0)]
    disputed_task_count: Annotated[int, Field(ge=0)]
    incident_status: Literal["clear", "unresolved", "severe"] | None = None
    reviewed_at: datetime
    valid_until: datetime

    @field_validator("reviewed_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class AssessmentSourceReviewIndex(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    r6_anchor_sha256: Digest
    r6_packet_sha256: Digest
    r6_result_sha256: Digest
    upstream_handoff_sha256: Digest
    final_reviewer_id: Identifier
    reviews: Annotated[tuple[SourceCoverageReview, ...], Field(max_length=11)]
    assembled_at: datetime

    @field_validator("assembled_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def unique_ordered_kinds(self) -> Self:
        kinds = tuple(item.kind for item in self.reviews)
        if len(kinds) != len(set(kinds)) or kinds != tuple(
            kind for kind in (*BASE_KINDS, *COMPARISON_KINDS) if kind in kinds
        ):
            raise ValueError(
                "assessment source review kinds are duplicated or unordered"
            )
        return self


class AssessmentSourceAssessment(Contract):
    schema_version: Literal[1] = 1
    status: Literal["reviewable", "blocked"]
    reasons: tuple[str, ...]
    anchor_sha256: Digest
    r6_packet_sha256: Digest
    r6_result_sha256: Digest
    review_index_sha256: Digest
    required_source_count: int
    reviewed_source_count: int
    assignment_count: int
    source_custody_verified: Literal[False] = False
    protected_outcomes_reviewed: Literal[False] = False
    comparative_claim_authorized: Literal[False] = False
    assessment_authorized: Literal[False] = False
    next_cohort_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False


def expected_source_digests(
    *, packet: OfflineR6AssessmentPacket, closeout: CohortCloseoutPacket
) -> dict[str, str]:
    """Map R6's bounded source references, never open their target artifacts."""
    evidence = packet.evidence
    sources = {
        "followup": digest(
            canonical_bytes(FollowupSourceIndex(followups=closeout.followups))
        ),
        "quality": evidence.quality_review_sha256,
        "damage": evidence.damage_review_sha256,
        "completion": evidence.completion_review_sha256,
        "all_task_latency": evidence.all_task_latency_sha256,
        "whole_task_cost": evidence.whole_task_cost_sha256,
        "stop_incident": evidence.stop_incident_sha256,
        "missingness": evidence.missingness_sha256,
        "independent_review": evidence.independent_review_sha256,
    }
    if packet.claim_type == "registered_comparison":
        if packet.baseline_registration_sha256 is not None:
            sources["baseline_registration"] = packet.baseline_registration_sha256
        if packet.comparison_design_sha256 is not None:
            sources["comparison_design"] = packet.comparison_design_sha256
    return sources


def validate_assessment_sources(
    *,
    anchor: FrozenAssessmentSourceAnchor,
    r6_anchor: FrozenR6AssessmentAnchor,
    r6_packet: OfflineR6AssessmentPacket,
    r6_result: OfflineR6AssessmentResult,
    protocol: FrozenCloseoutProtocol,
    closeout: CohortCloseoutPacket,
    r5_result: OfflineR5CloseResult,
    reviews: AssessmentSourceReviewIndex,
    now: datetime,
) -> AssessmentSourceAssessment:
    """Fail closed on source coverage gaps; issue no assessment decision."""
    _utc(now)
    reasons: set[str] = set()
    packet_sha = digest(canonical_bytes(r6_packet))
    result_sha = digest(canonical_bytes(r6_result))
    r6_anchor_sha = digest(canonical_bytes(r6_anchor))
    closeout_sha = digest(canonical_bytes(closeout))
    evidence_sha = digest(canonical_bytes(r6_packet.evidence))
    sources = expected_source_digests(packet=r6_packet, closeout=closeout)
    if (
        anchor.manifest_sha256 != r6_packet.manifest_sha256
        or anchor.r6_anchor_sha256 != r6_anchor_sha
        or anchor.r6_packet_sha256 != packet_sha
        or anchor.r6_result_sha256 != result_sha
        or anchor.closeout_packet_sha256 != closeout_sha
        or anchor.followup_index_sha256 != sources["followup"]
        or anchor.evidence_references_sha256 != evidence_sha
        or anchor.final_reviewer_id != r6_packet.reviewer_id
    ):
        reasons.add("anchor_binding_mismatch")
    if (
        reviews.manifest_sha256 != anchor.manifest_sha256
        or reviews.r6_anchor_sha256 != r6_anchor_sha
        or reviews.r6_packet_sha256 != packet_sha
        or reviews.r6_result_sha256 != result_sha
        or reviews.upstream_handoff_sha256 != anchor.upstream_handoff_sha256
        or reviews.final_reviewer_id != anchor.final_reviewer_id
    ):
        reasons.add("review_index_binding_mismatch")
    if (
        not r6_packet.reviewed_at
        <= anchor.frozen_at
        < reviews.assembled_at
        <= now
        < min(anchor.valid_until, r6_anchor.valid_until)
        or anchor.source_reviewer_id
        in (
            r6_anchor.owner_signer_id,
            r6_anchor.operator_signer_id,
            r6_packet.reviewer_id,
        )
        or anchor.custodian_id
        in (
            anchor.source_reviewer_id,
            anchor.final_reviewer_id,
        )
    ):
        reasons.add("review_window_or_roles_invalid")
    base = validate_offline_r6_assessment_handoff(
        r6_packet,
        anchor=r6_anchor,
        protocol=protocol,
        closeout_packet=closeout,
        r5_result=r5_result,
        now=now,
    )
    if (
        base.status != "reviewable"
        or r6_result.status != "reviewable"
        or r6_result != base.model_copy(update={"r5_reproduction_checked": True})
    ):
        reasons.add("r6_handoff_invalid")
    required = (
        (*BASE_KINDS, *COMPARISON_KINDS)
        if r6_packet.claim_type == "registered_comparison"
        else BASE_KINDS
    )
    if tuple(item.kind for item in reviews.reviews) != required:
        reasons.add("source_coverage_invalid")
    if len(closeout.assignment_task_ids) != r6_packet.assignment_count:
        reasons.add("roster_mismatch")
    for review in reviews.reviews:
        expected = sources.get(review.kind)
        task_scoped = review.kind in BASE_KINDS
        expected_count = r6_packet.assignment_count if task_scoped else 0
        if (
            expected is None
            or review.artifact_sha256 != expected
            or review.decision != "accept"
            or review.producer_id == review.reviewer_id
            or review.custodian_id != anchor.custodian_id
            or review.reviewer_id != anchor.source_reviewer_id
            or review.roster_sha256 != r6_packet.roster_sha256
            or review.covered_task_count != expected_count
            or review.unknown_task_count != 0
            or review.disputed_task_count != 0
            or (
                review.kind == "stop_incident"
                and review.incident_status != r6_packet.incident_status
            )
            or (review.kind != "stop_incident" and review.incident_status is not None)
            or not anchor.frozen_at < review.reviewed_at <= reviews.assembled_at
            or now >= review.valid_until
        ):
            reasons.add("source_review_invalid")
    if (
        r6_packet.incident_status != "clear"
        and r6_packet.proposed_disposition != "no_go"
    ):
        reasons.add("incident_disposition_invalid")
    if r6_packet.claim_type == "registered_comparison" and (
        r6_anchor.comparison_registered_at is None
        or r6_anchor.comparison_registered_at >= r6_anchor.cohort_started_at
        or set(COMPARISON_KINDS) - set(sources)
    ):
        reasons.add("comparison_source_invalid")
    return AssessmentSourceAssessment(
        status="blocked" if reasons else "reviewable",
        reasons=tuple(sorted(reasons)),
        anchor_sha256=digest(canonical_bytes(anchor)),
        r6_packet_sha256=packet_sha,
        r6_result_sha256=result_sha,
        review_index_sha256=digest(canonical_bytes(reviews)),
        required_source_count=len(required),
        reviewed_source_count=len(reviews.reviews),
        assignment_count=r6_packet.assignment_count,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "anchor",
        "r6_anchor",
        "r6_packet",
        "r6_result",
        "protocol",
        "closeout",
        "r5_result",
        "reviews",
        "output",
    ):
        parser.add_argument(name, type=Path)
    parser.add_argument("--now", help="explicit UTC assessment time")
    args = parser.parse_args(argv)
    try:
        anchor = FrozenAssessmentSourceAnchor.model_validate_json(
            args.anchor.read_bytes()
        )
        r6_anchor = FrozenR6AssessmentAnchor.model_validate_json(
            args.r6_anchor.read_bytes()
        )
        r6_packet = OfflineR6AssessmentPacket.model_validate_json(
            args.r6_packet.read_bytes()
        )
        r6_result = OfflineR6AssessmentResult.model_validate_json(
            args.r6_result.read_bytes()
        )
        protocol = FrozenCloseoutProtocol.model_validate_json(
            args.protocol.read_bytes()
        )
        closeout = CohortCloseoutPacket.model_validate_json(args.closeout.read_bytes())
        r5_result = OfflineR5CloseResult.model_validate_json(
            args.r5_result.read_bytes()
        )
        reviews = AssessmentSourceReviewIndex.model_validate_json(
            args.reviews.read_bytes()
        )
        now = _utc(datetime.fromisoformat(args.now)) if args.now else datetime.now(UTC)
    except (OSError, ValueError, ValidationError):
        print("blocked: invalid input")
        return 1
    result = validate_assessment_sources(
        anchor=anchor,
        r6_anchor=r6_anchor,
        r6_packet=r6_packet,
        r6_result=r6_result,
        protocol=protocol,
        closeout=closeout,
        r5_result=r5_result,
        reviews=reviews,
        now=now,
    )
    private_write(args.output, (result.model_dump_json(indent=2) + "\n").encode())
    print(f"{result.status}: {len(result.reasons)} mismatch categories")
    return 0 if result.status == "reviewable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
