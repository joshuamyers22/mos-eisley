"""Metadata-only synthetic G6-06 cohort closeout packet validation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier
from mos_eisley.run.witnessed_admission import Checkpoint, WitnessedState

Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("closeout time must use explicit UTC")
    return value


class FrozenCloseoutProtocol(Contract):
    """Independently supplied registration; never inferred from the packet."""

    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    assessment_protocol_sha256: Digest
    cutoff_at: datetime
    followup_due_at: datetime

    @field_validator("cutoff_at", "followup_due_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def ordered_window(self) -> Self:
        if self.followup_due_at <= self.cutoff_at:
            raise ValueError("closeout follow-up must follow cutoff")
        return self


class AttemptCloseoutLink(Contract):
    attempt_key: Digest
    claim_id: Digest
    task_id: Identifier
    intent_sha256: Digest | None = None
    local_status: Literal["settled", "uncertain", "violation", "abandoned"] | None = (
        None
    )
    local_charged_microusd: Money | None = None

    @model_validator(mode="after")
    def local_disposition(self) -> Self:
        if (self.local_status is None) != (self.local_charged_microusd is None):
            raise ValueError("local disposition and charge must appear together")
        if self.local_status is not None and self.intent_sha256 is None:
            raise ValueError("local disposition needs a durable intent")
        return self


class TaskFollowupIndex(Contract):
    task_id: Identifier
    status: Literal["present", "pending", "missing", "disputed"]
    evidence_sha256: Digest | None = None
    observed_at: datetime | None = None

    @field_validator("observed_at")
    @classmethod
    def utc_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)

    @model_validator(mode="after")
    def evidence_shape(self) -> Self:
        if self.status == "present" and (
            self.evidence_sha256 is None or self.observed_at is None
        ):
            raise ValueError("present follow-up needs an evidence reference and time")
        if self.status != "present" and (
            self.evidence_sha256 is not None or self.observed_at is not None
        ):
            raise ValueError("unresolved follow-up cannot carry invented evidence")
        return self


class CloseoutEvidenceIndex(Contract):
    """References only; an independent reviewer must verify each source."""

    route_coverage_sha256: Digest | None = None
    cap_history_sha256: Digest | None = None
    all_task_latency_sha256: Digest | None = None
    monitoring_incidents_sha256: Digest | None = None
    followup_custody_sha256: Digest | None = None
    protocol_deviations_sha256: Digest | None = None

    def complete(self) -> bool:
        return all(value is not None for value in self.model_dump().values())


class CohortCloseoutPacket(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    assessment_protocol_sha256: Digest
    release_sha256: Digest
    witness_epoch_id: Digest
    witness_generation: Annotated[int, Field(ge=0)]
    witness_state_sha256: Digest
    prepared_at: datetime
    assignment_task_ids: tuple[Identifier, ...]
    attempt_links: tuple[AttemptCloseoutLink, ...]
    followups: tuple[TaskFollowupIndex, ...]
    evidence: CloseoutEvidenceIndex

    @field_validator("prepared_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class CloseoutValidation(Contract):
    status: Literal["blocked", "provisional", "reviewable"]
    reasons: tuple[str, ...]
    assignment_count: int
    claim_count: int
    intent_count: int
    settled_microusd: Money
    retained_exposure_microusd: Money
    followup_present_count: int
    followup_unknown_count: int
    assessment_authority: Literal[False] = False
    dispatch_authority: Literal[False] = False


def validate_offline_cohort_closeout(
    packet: CohortCloseoutPacket,
    *,
    protocol: FrozenCloseoutProtocol,
    witness: WitnessedState,
    checkpoint: Checkpoint,
    now: datetime,
) -> CloseoutValidation:
    """Check a synthetic snapshot; source custody and actual outcomes stay external."""
    _utc(now)
    reasons: set[str] = set()
    cohort = witness.cohort
    if cohort is None:
        reasons.add("cohort_missing")
    if (
        checkpoint.epoch_id != witness.epoch_id
        or checkpoint.generation != witness.generation
        or checkpoint.state_sha256 != witness.state_sha256
    ):
        reasons.add("checkpoint_mismatch")
    if (
        packet.witness_epoch_id != witness.epoch_id
        or packet.witness_generation != witness.generation
        or packet.witness_state_sha256 != witness.state_sha256
    ):
        reasons.add("witness_binding_mismatch")
    if (
        packet.manifest_sha256 != protocol.manifest_sha256
        or packet.assessment_protocol_sha256 != protocol.assessment_protocol_sha256
    ):
        reasons.add("protocol_binding_mismatch")
    if packet.prepared_at > now or packet.prepared_at < protocol.cutoff_at:
        reasons.add("packet_time_invalid")

    assignments = () if cohort is None else cohort.assignments
    attempts = witness.attempts
    roster = tuple(item.task_id for item in assignments)
    if packet.assignment_task_ids != roster:
        reasons.add("roster_mismatch")
    if cohort is not None:
        if (
            cohort.manifest.manifest_sha256 != protocol.manifest_sha256
            or packet.release_sha256 != cohort.signed_release.release.release_sha256
        ):
            reasons.add("cohort_binding_mismatch")
        if any(item.assigned_at > protocol.cutoff_at for item in assignments):
            reasons.add("post_cutoff_assignment")

    assigned = {item.task_id: item for item in assignments}
    seen_tasks: set[str] = set()
    for row in attempts:
        attempt = row.attempt
        assignment = assigned.get(attempt.task_id)
        if (
            assignment is None
            or assignment.session_id != attempt.session_id
            or assignment.stage_id != attempt.stage_id
            or assignment.assigned_generation >= row.admitted_generation
            or attempt.task_id in seen_tasks
        ):
            reasons.add("attempt_roster_mismatch")
        seen_tasks.add(attempt.task_id)

    links = {item.attempt_key: item for item in packet.attempt_links}
    if len(links) != len(packet.attempt_links) or set(links) != {
        row.attempt.attempt_key for row in attempts
    }:
        reasons.add("attempt_index_mismatch")
    for row in attempts:
        link = links.get(row.attempt.attempt_key)
        if link is None:
            continue
        if link.claim_id != row.claim_id or link.task_id != row.attempt.task_id:
            reasons.add("claim_link_mismatch")
        if row.status == "settled" and (
            link.local_status != "settled" or link.intent_sha256 is None
        ):
            reasons.add("settlement_link_mismatch")
        if row.status in ("uncertain", "violation") and link.local_status != row.status:
            reasons.add("disposition_mismatch")
        if row.status == "held" and link.local_status not in (None, "abandoned"):
            reasons.add("disposition_mismatch")
        if (
            link.local_status is not None
            and link.local_charged_microusd != row.charged_microusd
        ):
            reasons.add("charge_mismatch")

    followups = {item.task_id: item for item in packet.followups}
    if len(followups) != len(packet.followups) or set(followups) != set(roster):
        reasons.add("followup_roster_mismatch")
    for task_id, item in followups.items():
        assignment = assigned.get(task_id)
        if item.observed_at is not None and (
            assignment is None
            or item.observed_at < assignment.assigned_at
            or item.observed_at > packet.prepared_at
        ):
            reasons.add("followup_time_invalid")

    settled = sum(row.charged_microusd for row in attempts if row.status == "settled")
    retained = sum(row.charged_microusd for row in attempts if row.status != "settled")
    present = sum(
        followups[task_id].status == "present"
        for task_id in roster
        if task_id in followups
    )
    unknown = len(roster) - present
    if not packet.evidence.complete():
        reasons.add("evidence_index_incomplete")
    if cohort is not None and cohort.signed_release.release.phase != "closed":
        reasons.add("cohort_not_closed")
    if now < protocol.followup_due_at:
        reasons.add("followup_window_open")
    if unknown:
        reasons.add("followup_incomplete")
    soft = {"followup_window_open"}
    if now < protocol.followup_due_at:
        soft.update(
            {"evidence_index_incomplete", "cohort_not_closed", "followup_incomplete"}
        )
    hard = reasons - soft
    status: Literal["blocked", "provisional", "reviewable"] = (
        "blocked" if hard else "provisional" if reasons else "reviewable"
    )
    return CloseoutValidation(
        status=status,
        reasons=tuple(sorted(reasons)),
        assignment_count=len(roster),
        claim_count=len(attempts),
        intent_count=sum(
            links[row.attempt.attempt_key].intent_sha256 is not None
            for row in attempts
            if row.attempt.attempt_key in links
        ),
        settled_microusd=settled,
        retained_exposure_microusd=retained,
        followup_present_count=present,
        followup_unknown_count=unknown,
    )
