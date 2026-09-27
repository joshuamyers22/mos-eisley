"""Metadata-only G6-06 R6 later-window assessment handoff validation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.cohort_close_handoff import OfflineR5CloseResult
from mos_eisley.run.cohort_closeout import CohortCloseoutPacket, FrozenCloseoutProtocol

Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("R6 assessment time must use explicit UTC")
    return value


class R6RosterIndex(Contract):
    task_ids: tuple[Identifier, ...]


class R6DispatchIndex(Contract):
    """Independently supplied synthetic inert-entry attempt keys only."""

    entered_attempt_keys: tuple[Digest, ...]


class R6EvidenceReferences(Contract):
    """Digests only; no protected labels, outcomes or reviewer prose."""

    quality_review_sha256: Digest
    damage_review_sha256: Digest
    completion_review_sha256: Digest
    all_task_latency_sha256: Digest
    whole_task_cost_sha256: Digest
    stop_incident_sha256: Digest
    missingness_sha256: Digest
    independent_review_sha256: Digest


class FrozenR6AssessmentAnchor(Contract):
    """Independent registration and expected source digests for one handoff."""

    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    closeout_protocol_sha256: Digest
    closeout_packet_sha256: Digest
    r5_result_sha256: Digest
    roster_sha256: Digest
    dispatch_index_sha256: Digest
    evidence_references_sha256: Digest
    owner_signer_id: Identifier
    operator_signer_id: Identifier
    expected_reviewer_id: Identifier
    expected_review_status: Literal["accepted", "rejected", "unavailable"]
    expected_claim_type: Literal["descriptive_only", "registered_comparison"]
    expected_disposition: Literal["no_go", "continue_fixed", "propose_next_cohort"]
    incident_status: Literal["clear", "unresolved", "severe"]
    baseline_registration_sha256: Digest | None = None
    comparison_design_sha256: Digest | None = None
    comparison_registered_at: datetime | None = None
    cohort_started_at: datetime
    review_not_before: datetime
    valid_until: datetime

    @field_validator(
        "comparison_registered_at",
        "cohort_started_at",
        "review_not_before",
        "valid_until",
    )
    @classmethod
    def utc_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)

    @model_validator(mode="after")
    def ordered_window(self) -> Self:
        if self.valid_until <= self.review_not_before:
            raise ValueError("R6 review window is invalid")
        if (self.baseline_registration_sha256 is None) != (
            self.comparison_design_sha256 is None
        ) or (self.baseline_registration_sha256 is None) != (
            self.comparison_registered_at is None
        ):
            raise ValueError("R6 comparison registration fields must appear together")
        return self


class OfflineR6AssessmentPacket(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    closeout_protocol_sha256: Digest
    closeout_packet_sha256: Digest
    r5_result_sha256: Digest
    roster_sha256: Digest
    dispatch_index: R6DispatchIndex
    assignment_count: Annotated[int, Field(ge=0)]
    claim_count: Annotated[int, Field(ge=0)]
    no_dispatch_count: Annotated[int, Field(ge=0)]
    possible_transfer_count: Annotated[int, Field(ge=0)]
    followup_present_count: Annotated[int, Field(ge=0)]
    followup_unknown_count: Annotated[int, Field(ge=0)]
    settled_microusd: Money
    retained_exposure_microusd: Money
    conservative_exposure_microusd: Money
    evidence: R6EvidenceReferences
    reviewer_id: Identifier
    review_status: Literal["accepted", "rejected", "unavailable"]
    incident_status: Literal["clear", "unresolved", "severe"]
    claim_type: Literal["descriptive_only", "registered_comparison"]
    baseline_registration_sha256: Digest | None = None
    comparison_design_sha256: Digest | None = None
    proposed_disposition: Literal["no_go", "continue_fixed", "propose_next_cohort"]
    prepared_at: datetime
    reviewed_at: datetime

    @field_validator("prepared_at", "reviewed_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class OfflineR6AssessmentResult(Contract):
    status: Literal["blocked", "reviewable"]
    reasons: tuple[str, ...]
    assignment_count: Annotated[int, Field(ge=0)]
    claim_count: Annotated[int, Field(ge=0)]
    no_dispatch_count: Annotated[int, Field(ge=0)]
    possible_transfer_count: Annotated[int, Field(ge=0)]
    followup_unknown_count: Annotated[int, Field(ge=0)]
    conservative_exposure_microusd: Money
    assessment_authorized: Literal[False] = False
    comparative_claim_authorized: Literal[False] = False
    policy_promotion_authorized: Literal[False] = False
    next_cohort_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False


def validate_offline_r6_assessment_handoff(
    packet: OfflineR6AssessmentPacket,
    *,
    anchor: FrozenR6AssessmentAnchor,
    protocol: FrozenCloseoutProtocol,
    closeout_packet: CohortCloseoutPacket,
    r5_result: OfflineR5CloseResult,
    now: datetime,
) -> OfflineR6AssessmentResult:
    """Check packet structure and frozen references without protected data access."""
    _utc(now)
    reasons: set[str] = set()
    roster = closeout_packet.assignment_task_ids
    roster_sha256 = digest(canonical_bytes(R6RosterIndex(task_ids=roster)))
    assignment_count = len(roster)
    claim_count = len(closeout_packet.attempt_links)
    claimed_tasks = {item.task_id for item in closeout_packet.attempt_links}
    links = {item.attempt_key: item for item in closeout_packet.attempt_links}
    entered_keys = set(packet.dispatch_index.entered_attempt_keys)
    entered_tasks = {links[key].task_id for key in entered_keys if key in links}
    possible_tasks = {
        item.task_id
        for item in closeout_packet.attempt_links
        if item.intent_sha256 is not None and item.attempt_key not in entered_keys
    }
    no_dispatch_count = max(0, assignment_count - len(entered_tasks | possible_tasks))
    possible_transfer_count = len(possible_tasks)
    followup_present = sum(
        item.status == "present" for item in closeout_packet.followups
    )
    followup_unknown = assignment_count - followup_present
    settled = sum(
        item.local_charged_microusd or 0
        for item in closeout_packet.attempt_links
        if item.local_status == "settled"
    )
    retained = max(0, r5_result.conservative_exposure_microusd - settled)

    if (
        packet.prepared_at > packet.reviewed_at
        or packet.prepared_at < closeout_packet.prepared_at
        or packet.reviewed_at > now
        or packet.reviewed_at < anchor.review_not_before
        or packet.prepared_at < protocol.followup_due_at
        or now >= anchor.valid_until
        or anchor.review_not_before < protocol.followup_due_at
    ):
        reasons.add("review_time_invalid")
    if (
        anchor.manifest_sha256 != protocol.manifest_sha256
        or anchor.closeout_protocol_sha256 != digest(canonical_bytes(protocol))
        or anchor.closeout_packet_sha256 != digest(canonical_bytes(closeout_packet))
        or anchor.r5_result_sha256 != digest(canonical_bytes(r5_result))
        or anchor.roster_sha256 != roster_sha256
        or anchor.dispatch_index_sha256
        != digest(canonical_bytes(packet.dispatch_index))
        or packet.manifest_sha256 != anchor.manifest_sha256
        or packet.closeout_protocol_sha256 != anchor.closeout_protocol_sha256
        or packet.closeout_packet_sha256 != anchor.closeout_packet_sha256
        or packet.r5_result_sha256 != anchor.r5_result_sha256
        or packet.roster_sha256 != anchor.roster_sha256
    ):
        reasons.add("source_binding_mismatch")
    if (
        r5_result.status != "reviewable"
        or r5_result.reasons
        or r5_result.closeout_reasons
        or r5_result.followup_unknown_count
        or closeout_packet.prepared_at < protocol.followup_due_at
        or closeout_packet.manifest_sha256 != protocol.manifest_sha256
        or closeout_packet.assessment_protocol_sha256
        != protocol.assessment_protocol_sha256
    ):
        reasons.add("r5_handoff_not_mature")
    if (
        len(set(roster)) != assignment_count
        or set(item.task_id for item in closeout_packet.followups) != set(roster)
        or len(closeout_packet.followups) != assignment_count
        or not claimed_tasks <= set(roster)
        or len(claimed_tasks) != claim_count
        or len(links) != claim_count
        or len(entered_keys) != len(packet.dispatch_index.entered_attempt_keys)
        or not entered_keys <= set(links)
        or any(links[key].intent_sha256 is None for key in entered_keys if key in links)
        or any(
            item.local_status == "settled" and item.attempt_key not in entered_keys
            for item in closeout_packet.attempt_links
        )
        or followup_unknown
        or r5_result.assignment_count != assignment_count
        or r5_result.claim_count != claim_count
        or packet.assignment_count != assignment_count
        or packet.claim_count != claim_count
        or packet.no_dispatch_count != no_dispatch_count
        or packet.possible_transfer_count != possible_transfer_count
        or packet.followup_present_count != followup_present
        or packet.followup_unknown_count != followup_unknown
    ):
        reasons.add("denominator_mismatch")
    if (
        packet.settled_microusd != settled
        or packet.retained_exposure_microusd != retained
        or packet.conservative_exposure_microusd
        != r5_result.conservative_exposure_microusd
        or r5_result.conservative_exposure_microusd < settled
    ):
        reasons.add("cost_exposure_mismatch")
    if (
        digest(canonical_bytes(packet.evidence)) != anchor.evidence_references_sha256
        or packet.reviewer_id != anchor.expected_reviewer_id
        or packet.reviewer_id in (anchor.owner_signer_id, anchor.operator_signer_id)
        or packet.review_status != anchor.expected_review_status
        or packet.review_status != "accepted"
    ):
        reasons.add("independent_review_invalid")
    if (
        packet.claim_type != anchor.expected_claim_type
        or packet.proposed_disposition != anchor.expected_disposition
    ):
        reasons.add("decision_binding_mismatch")
    if packet.incident_status != anchor.incident_status:
        reasons.add("incident_status_mismatch")
    if (
        packet.incident_status in ("unresolved", "severe")
        or anchor.incident_status in ("unresolved", "severe")
    ) and packet.proposed_disposition != "no_go":
        reasons.add("incident_disposition_invalid")
    if packet.claim_type == "registered_comparison":
        if (
            anchor.baseline_registration_sha256 is None
            or anchor.comparison_design_sha256 is None
            or anchor.comparison_registered_at is None
            or anchor.comparison_registered_at >= anchor.cohort_started_at
            or packet.baseline_registration_sha256
            != anchor.baseline_registration_sha256
            or packet.comparison_design_sha256 != anchor.comparison_design_sha256
        ):
            reasons.add("comparison_unregistered")
    elif (
        packet.baseline_registration_sha256 is not None
        or packet.comparison_design_sha256 is not None
    ):
        reasons.add("comparison_unregistered")
    return OfflineR6AssessmentResult(
        status="blocked" if reasons else "reviewable",
        reasons=tuple(sorted(reasons)),
        assignment_count=assignment_count,
        claim_count=claim_count,
        no_dispatch_count=no_dispatch_count,
        possible_transfer_count=possible_transfer_count,
        followup_unknown_count=max(0, followup_unknown),
        conservative_exposure_microusd=r5_result.conservative_exposure_microusd,
    )
