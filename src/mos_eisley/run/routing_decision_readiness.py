"""G605-06 metadata-only decision-readiness screen; grants no G6 authority."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.routing_host_drills import HostDrillEvidenceIndex, HostDrillProtocol
from mos_eisley.run.routing_qualification import (
    OfflineQualificationEvidence,
    OfflineQualificationPacket,
    OfflineQualificationReviewTrust,
    SignedOfflineQualificationReview,
    validate_offline_qualification_packet,
)
from mos_eisley.run.routing_source_handoff import (
    G605SourceEvidenceHandoff,
    validate_g605_source_handoff,
)

ReviewerRole = Literal["operations", "owner", "security", "statistical"]
DecisionStatus = Literal["accept", "reject", "unavailable"]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("decision-readiness time must use explicit UTC")
    return value


class SourceInspectionOutcome(Contract):
    source_id: Identifier
    source_sha256: Digest
    inspection_record_sha256: Digest
    checker_id: Identifier
    status: DecisionStatus
    inspected_at: datetime
    valid_until: datetime

    @field_validator("inspected_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_until <= self.inspected_at:
            raise ValueError("source inspection window is invalid")
        return self


class RequiredDecision(Contract):
    decision_id: Identifier
    subject_sha256: Digest
    reviewer_role: ReviewerRole


class DecisionDisposition(RequiredDecision):
    decision_record_sha256: Digest
    reviewer_id: Identifier
    producer_id: Identifier
    status: DecisionStatus
    recorded_at: datetime
    valid_until: datetime

    @field_validator("recorded_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_window_and_separation(self) -> Self:
        if self.valid_until <= self.recorded_at or self.reviewer_id == self.producer_id:
            raise ValueError("decision disposition window or reviewer is invalid")
        return self


def signed_reviews_sha256(
    reviews: tuple[SignedOfflineQualificationReview, ...],
) -> str:
    """Hash a role-ordered Q7 review set without opening its source evidence."""
    ordered = sorted(reviews, key=lambda item: item.review.role)
    encoded = json.dumps(
        [item.model_dump(mode="json") for item in ordered],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return digest(b"g605-q7-review-set-v1\0" + encoded)


class G605DecisionReadinessPacket(Contract):
    schema_version: Literal[1] = 1
    qualification_packet_sha256: Digest
    qualification_evidence_sha256: Digest
    drill_protocol_sha256: Digest
    drill_index_sha256: Digest
    source_handoff_sha256: Digest
    review_trust_sha256: Digest
    signed_reviews_sha256: Digest
    technical_review_sha256: Digest
    assembled_at: datetime
    valid_until: datetime
    decision_state: Literal["pending"] = "pending"
    source_inspections: Annotated[
        tuple[SourceInspectionOutcome, ...], Field(min_length=1, max_length=4096)
    ]
    dispositions: Annotated[
        tuple[DecisionDisposition, ...], Field(min_length=1, max_length=64)
    ]
    unresolved_findings: Annotated[tuple[Identifier, ...], Field(max_length=64)] = ()

    @field_validator("assembled_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def canonical_entries(self) -> Self:
        inspection_ids = tuple(item.source_id for item in self.source_inspections)
        decision_ids = tuple(item.decision_id for item in self.dispositions)
        if (
            self.valid_until <= self.assembled_at
            or inspection_ids != tuple(sorted(set(inspection_ids)))
            or decision_ids != tuple(sorted(set(decision_ids)))
            or self.unresolved_findings != tuple(sorted(set(self.unresolved_findings)))
        ):
            raise ValueError("decision-readiness entries or window are invalid")
        return self

    @property
    def readiness_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G605DecisionReadinessAssessment(Contract):
    schema_version: Literal[1] = 1
    readiness_sha256: Digest
    required_source_count: Annotated[int, Field(ge=0)]
    required_decision_count: Annotated[int, Field(ge=0)]
    ready_for_owner_decision: bool
    reasons: tuple[Identifier, ...]
    source_authenticated: Literal[False] = False
    target_host_verified: Literal[False] = False
    g5_qualified: Literal[False] = False
    qualification_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False


def required_decisions(
    *,
    packet: OfflineQualificationPacket,
    evidence: OfflineQualificationEvidence,
    drill_index: HostDrillEvidenceIndex,
    handoff: G605SourceEvidenceHandoff,
    technical_review_sha256: Digest,
) -> tuple[RequiredDecision, ...]:
    """Enumerate named decision subjects from frozen metadata only."""
    expected: dict[str, RequiredDecision] = {}

    def add(decision_id: str, subject_sha256: str, role: ReviewerRole) -> None:
        if decision_id in expected:
            raise ValueError("duplicate decision requirement")
        expected[decision_id] = RequiredDecision(
            decision_id=decision_id,
            subject_sha256=subject_sha256,
            reviewer_role=role,
        )

    add("G5-audit", packet.candidate.g5_claim_sha256, "statistical")
    records = {item.evidence_id: item for item in evidence.records}
    for evidence_id in (
        *(item.milestone for item in packet.prerequisites if item.required),
        "G6-01",
        "G6-02",
        "G6-03",
        "G6-04",
        *(f"Q{number}" for number in range(1, 7)),
    ):
        record = records.get(evidence_id)
        if record is None or record.source_sha256 is None:
            continue
        role: ReviewerRole = "statistical" if evidence_id == "Q1" else "security"
        add(evidence_id, record.source_sha256, role)
    add("G605-01", packet.packet_sha256, "security")
    for finding in ("G605-02", "G605-03", "G605-04"):
        add(finding, technical_review_sha256, "security")
    add("G605-05", handoff.handoff_sha256, "security")
    add("promotion", packet.authority.promotion_receipt_sha256, "security")
    add("activation", packet.authority.activation_eligibility_sha256, "security")
    add("exact-route", packet.candidate.candidate_policy_sha256, "security")
    add("target-host", packet.runtime.broker_build_sha256, "security")
    add("witness-custody", packet.witness.enrollment_sha256, "security")
    add("host-drills", drill_index.evidence_sha256, "security")
    add("operations-runbook", packet.runtime.stop_runbook_sha256, "operations")
    return tuple(expected[key] for key in sorted(expected))


def validate_g605_decision_readiness(
    *,
    readiness: G605DecisionReadinessPacket,
    packet: OfflineQualificationPacket,
    evidence: OfflineQualificationEvidence,
    drill_protocol: HostDrillProtocol,
    drill_index: HostDrillEvidenceIndex,
    handoff: G605SourceEvidenceHandoff,
    trust: OfflineQualificationReviewTrust,
    reviews: tuple[SignedOfflineQualificationReview, ...],
    expected_inspection_protocol_sha256: Digest,
    expected_reviewer_roster_sha256: Digest,
    expected_review_trust_sha256: Digest,
    expected_technical_review_sha256: Digest,
    now: datetime,
) -> G605DecisionReadinessAssessment:
    """Screen a Q7 queue; actual source decisions and owner go stay external."""
    _utc(now)
    reasons: set[str] = set()
    handoff_assessment = validate_g605_source_handoff(
        handoff=handoff,
        packet=packet,
        evidence=evidence,
        drill_protocol=drill_protocol,
        drill_index=drill_index,
        expected_inspection_protocol_sha256=expected_inspection_protocol_sha256,
        expected_reviewer_roster_sha256=expected_reviewer_roster_sha256,
        now=now,
    )
    if not handoff_assessment.handoff_ready:
        reasons.add("source_handoff_invalid")
    qualification = validate_offline_qualification_packet(
        packet=packet,
        evidence=evidence,
        reviews=reviews,
        trust=trust,
        drill_protocol=drill_protocol,
        drill_index=drill_index,
        now=now,
    )
    if not qualification.reviewable:
        reasons.add("qualification_metadata_invalid")
    if (
        readiness.qualification_packet_sha256 != packet.packet_sha256
        or readiness.qualification_evidence_sha256 != evidence.evidence_sha256
        or readiness.drill_protocol_sha256 != drill_protocol.protocol_sha256
        or readiness.drill_index_sha256 != drill_index.evidence_sha256
        or readiness.source_handoff_sha256 != handoff.handoff_sha256
        or readiness.review_trust_sha256 != digest(canonical_bytes(trust))
        or readiness.review_trust_sha256 != expected_review_trust_sha256
        or readiness.signed_reviews_sha256 != signed_reviews_sha256(reviews)
        or readiness.technical_review_sha256 != expected_technical_review_sha256
    ):
        reasons.add("readiness_binding_mismatch")
    if (
        not packet.frozen_at <= readiness.assembled_at <= now
        or not readiness.assembled_at <= now < readiness.valid_until
        or readiness.valid_until > packet.decision_deadline
        or readiness.valid_until > packet.scope.valid_until
        or readiness.assembled_at < handoff.assembled_at
    ):
        reasons.add("readiness_window_invalid")
    inspections = {item.source_id: item for item in readiness.source_inspections}
    references = {item.source_id: item for item in handoff.references}
    if set(inspections) != set(references):
        reasons.add("inspection_coverage_invalid")
    latest_inspection = handoff.assembled_at
    for source_id, item in inspections.items():
        source = references.get(source_id)
        if source is None:
            continue
        if (
            item.source_sha256 != source.source_sha256
            or item.checker_id != source.checker_id
        ):
            reasons.add("inspection_binding_mismatch")
        if item.status != "accept":
            reasons.add("inspection_not_accepted")
        if (
            item.inspected_at < handoff.assembled_at
            or item.inspected_at > readiness.assembled_at
            or not item.inspected_at <= now < item.valid_until
        ):
            reasons.add("inspection_window_invalid")
        latest_inspection = max(latest_inspection, item.inspected_at)
    required = required_decisions(
        packet=packet,
        evidence=evidence,
        drill_index=drill_index,
        handoff=handoff,
        technical_review_sha256=readiness.technical_review_sha256,
    )
    expected = {item.decision_id: item for item in required}
    actual = {item.decision_id: item for item in readiness.dispositions}
    if set(actual) != set(expected):
        reasons.add("decision_coverage_invalid")
    roster = {item.role: item.reviewer_id for item in trust.reviewers}
    latest_decision = handoff.assembled_at
    for decision_id, item in actual.items():
        requirement = expected.get(decision_id)
        if requirement is None:
            continue
        if (
            item.subject_sha256 != requirement.subject_sha256
            or item.reviewer_role != requirement.reviewer_role
            or item.reviewer_id != roster.get(requirement.reviewer_role)
        ):
            reasons.add("decision_binding_mismatch")
        if item.status != "accept":
            reasons.add("decision_not_accepted")
        if (
            item.recorded_at > readiness.assembled_at
            or not item.recorded_at <= now < item.valid_until
        ):
            reasons.add("decision_window_invalid")
        if decision_id == "G605-05" and item.recorded_at < latest_inspection:
            reasons.add("source_disposition_early")
        latest_decision = max(latest_decision, item.recorded_at)
    if readiness.unresolved_findings:
        reasons.add("unresolved_findings")
    if any(
        review.review.reviewed_at < max(latest_inspection, latest_decision)
        or review.review.reviewed_at > readiness.assembled_at
        for review in reviews
    ):
        reasons.add("q7_review_order_invalid")
    return G605DecisionReadinessAssessment(
        readiness_sha256=readiness.readiness_sha256,
        required_source_count=len(references),
        required_decision_count=len(required),
        ready_for_owner_decision=not reasons,
        reasons=tuple(sorted(reasons)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an offline G605-06 Q7 queue")
    for name in (
        "packet",
        "evidence",
        "drill_protocol",
        "drill_index",
        "source_handoff",
        "review_trust",
        "signed_reviews",
        "readiness",
    ):
        parser.add_argument(name, type=Path)
    parser.add_argument("--inspection-protocol-sha256", required=True)
    parser.add_argument("--reviewer-roster-sha256", required=True)
    parser.add_argument("--review-trust-sha256", required=True)
    parser.add_argument("--technical-review-sha256", required=True)
    parser.add_argument("--now", required=True, help="Explicit ISO-8601 UTC time")
    args = parser.parse_args()
    paths = (
        args.packet,
        args.evidence,
        args.drill_protocol,
        args.drill_index,
        args.source_handoff,
        args.review_trust,
        args.signed_reviews,
        args.readiness,
    )
    for path in paths:
        if path.stat().st_size > 2_000_000:
            parser.error("decision-readiness JSON exceeds the 2 MB metadata limit")
    reviews_adapter: TypeAdapter[tuple[SignedOfflineQualificationReview, ...]] = (
        TypeAdapter(tuple[SignedOfflineQualificationReview, ...])
    )
    result = validate_g605_decision_readiness(
        packet=OfflineQualificationPacket.model_validate_json(args.packet.read_bytes()),
        evidence=OfflineQualificationEvidence.model_validate_json(
            args.evidence.read_bytes()
        ),
        drill_protocol=HostDrillProtocol.model_validate_json(
            args.drill_protocol.read_bytes()
        ),
        drill_index=HostDrillEvidenceIndex.model_validate_json(
            args.drill_index.read_bytes()
        ),
        handoff=G605SourceEvidenceHandoff.model_validate_json(
            args.source_handoff.read_bytes()
        ),
        trust=OfflineQualificationReviewTrust.model_validate_json(
            args.review_trust.read_bytes()
        ),
        reviews=reviews_adapter.validate_json(args.signed_reviews.read_bytes()),
        readiness=G605DecisionReadinessPacket.model_validate_json(
            args.readiness.read_bytes()
        ),
        expected_inspection_protocol_sha256=args.inspection_protocol_sha256,
        expected_reviewer_roster_sha256=args.reviewer_roster_sha256,
        expected_review_trust_sha256=args.review_trust_sha256,
        expected_technical_review_sha256=args.technical_review_sha256,
        now=datetime.fromisoformat(args.now),
    )
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    return 0 if result.ready_for_owner_decision else 1


if __name__ == "__main__":
    raise SystemExit(main())
