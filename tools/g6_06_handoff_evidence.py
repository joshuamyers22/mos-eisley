"""Signed, metadata-only G606-02 offline phase-evidence handoff checks."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.cohort_assessment_handoff import (
    FrozenR6AssessmentAnchor,
    OfflineR6AssessmentPacket,
    OfflineR6AssessmentResult,
)
from mos_eisley.run.cohort_close_handoff import (
    FrozenR5CloseAnchor,
    OfflineR4TriggerReproduction,
    OfflineR5CloseResult,
)
from mos_eisley.run.cohort_closeout import CohortCloseoutPacket
from mos_eisley.run.cohort_entry import (
    FrozenR2EntryAnchor,
    OfflineR2EntryPacket,
    OfflineR2EntryResult,
)
from mos_eisley.run.cohort_shadow import OfflineShadowDecisionBatch
from mos_eisley.run.cohort_surveillance import (
    OfflineR4SurveillancePacket,
    OfflineR4SurveillanceResult,
)
from mos_eisley.run.routing_transaction import FrozenCohortRecoveryAnchor
from mos_eisley.run.witnessed_admission import WitnessedState
from tools.g6_06_r0_offline import (
    BOUND_SOURCE_PATHS as R0_SOURCE_PATHS,
)
from tools.g6_06_r0_offline import (
    SUITES as R0_SUITES,
)
from tools.g6_06_r0_offline import R0OfflineResultIndex

Phase = Literal["R0", "R1", "ONCALL", "R5", "R6"]
_REVIEW_DOMAIN = b"mos-eisley/g606-phase-review/v1\0"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("G606 review time must use explicit UTC")
    return value


def _decode(value: str, size: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("G606 key or signature is not base64") from None
    if len(decoded) != size or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("G606 key or signature is not canonical")
    return decoded


class PhaseReviewTrust(Contract):
    phase: Phase
    reviewer_id: Identifier
    public_key_base64: str
    valid_from: datetime
    valid_until: datetime

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_key_window(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("G606 review trust window is invalid")
        _decode(self.public_key_base64, 32)
        return self


class PhaseReview(Contract):
    schema_version: Literal[1] = 1
    phase: Phase
    decision: Literal["accept", "reject"]
    manifest_sha256: Digest
    broker_build_sha256: Digest
    artifact_sha256: Digest
    source_set_sha256: Digest
    upstream_sha256: Digest | None = None
    reviewer_id: Identifier
    reviewed_at: datetime
    valid_until: datetime

    @field_validator("reviewed_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def ordered_window(self) -> Self:
        if self.valid_until <= self.reviewed_at:
            raise ValueError("G606 review window is invalid")
        return self


class SignedPhaseReview(Contract):
    review: PhaseReview
    signature_base64: str

    @model_validator(mode="after")
    def canonical_signature(self) -> Self:
        _decode(self.signature_base64, 64)
        return self

    @property
    def review_sha256(self) -> str:
        return digest(canonical_bytes(self))


def sign_synthetic_phase_review(
    review: PhaseReview, private_key: bytes
) -> SignedPhaseReview:
    """Fixture helper; real reviewer enrollment and key custody are external."""
    signature = Ed25519PrivateKey.from_private_bytes(private_key).sign(
        _REVIEW_DOMAIN + canonical_bytes(review)
    )
    return SignedPhaseReview(
        review=review,
        signature_base64=base64.b64encode(signature).decode("ascii"),
    )


class FrozenR2EvidenceAnchor(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    broker_build_sha256: Digest
    r0_index_sha256: Digest
    r1_batch_sha256: Digest
    entry_result_sha256: Digest
    r1_source_set_sha256: Digest
    oncall_evidence_sha256: Digest
    expected_task_session_sha256: Annotated[
        tuple[Digest, ...], Field(min_length=1, max_length=256)
    ]
    trust_roster_sha256: Digest
    valid_until: datetime

    @field_validator("valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def unique_tasks(self) -> Self:
        if self.expected_task_session_sha256 != tuple(
            sorted(set(self.expected_task_session_sha256))
        ):
            raise ValueError("G606 R1 expected task coverage is not canonical")
        return self


class R5SourceBundle(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    broker_build_sha256: Digest
    r5_anchor_sha256: Digest
    r4_packet_sha256: Digest
    r4_result_sha256: Digest
    preclose_state_sha256: Digest
    recovery_anchor_sha256: Digest
    reproduction_sha256: Digest
    closeout_packet_sha256: Digest
    r5_result_sha256: Digest


class R6SourceBundle(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    broker_build_sha256: Digest
    r5_bundle_sha256: Digest
    r6_anchor_sha256: Digest
    r6_packet_sha256: Digest
    r6_result_sha256: Digest
    evidence_references_sha256: Digest
    dispatch_index_sha256: Digest
    roster_sha256: Digest


class FrozenR5R6EvidenceAnchor(Contract):
    schema_version: Literal[1] = 1
    manifest_sha256: Digest
    broker_build_sha256: Digest
    source_set_sha256: Digest
    r5_bundle_sha256: Digest
    r6_bundle_sha256: Digest
    trust_roster_sha256: Digest
    valid_until: datetime

    @field_validator("valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)


class G606EvidenceAssessment(Contract):
    status: Literal["blocked", "reviewable"]
    reasons: tuple[Identifier, ...]
    checked_phase_count: Annotated[int, Field(ge=0, le=5)]
    independent_custody_verified: Literal[False] = False
    cohort_release_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False
    assessment_authorized: Literal[False] = False


def _trust_map(
    trusts: tuple[PhaseReviewTrust, ...],
    *,
    phases: tuple[Phase, ...],
    owner_signer_id: str,
    operator_signer_id: str,
    reasons: set[str],
) -> dict[Phase, PhaseReviewTrust]:
    if (
        tuple(sorted(item.phase for item in trusts)) != tuple(sorted(phases))
        or len({item.reviewer_id for item in trusts}) != len(trusts)
        or len({item.public_key_base64 for item in trusts}) != len(trusts)
        or any(
            item.reviewer_id in (owner_signer_id, operator_signer_id) for item in trusts
        )
    ):
        reasons.add("review_trust_roster_invalid")
    return {item.phase: item for item in trusts}


def _review(
    signed: SignedPhaseReview | None,
    *,
    trust: PhaseReviewTrust | None,
    phase: Phase,
    manifest_sha256: str,
    broker_build_sha256: str,
    artifact_sha256: str,
    source_set_sha256: str,
    upstream_sha256: str | None,
    earliest_review_at: datetime,
    now: datetime,
    reasons: set[str],
) -> None:
    if signed is None:
        reasons.add(f"{phase.lower()}_review_missing")
        return
    review = signed.review
    if (
        review.phase != phase
        or review.decision != "accept"
        or review.manifest_sha256 != manifest_sha256
        or review.broker_build_sha256 != broker_build_sha256
        or review.artifact_sha256 != artifact_sha256
        or review.source_set_sha256 != source_set_sha256
        or review.upstream_sha256 != upstream_sha256
        or trust is None
        or trust.phase != phase
        or review.reviewer_id != trust.reviewer_id
    ):
        reasons.add(f"{phase.lower()}_review_binding_invalid")
    if (
        review.reviewed_at < earliest_review_at
        or review.reviewed_at > now
        or now >= review.valid_until
        or trust is None
        or not trust.valid_from <= review.reviewed_at
        or review.valid_until > trust.valid_until
    ):
        reasons.add(f"{phase.lower()}_review_time_invalid")
    if trust is not None:
        try:
            Ed25519PublicKey.from_public_bytes(
                _decode(trust.public_key_base64, 32)
            ).verify(
                _decode(signed.signature_base64, 64),
                _REVIEW_DOMAIN + canonical_bytes(review),
            )
        except (InvalidSignature, ValueError):
            reasons.add(f"{phase.lower()}_review_signature_invalid")


def validate_r0_r1_to_r2_evidence(
    *,
    packet: OfflineR2EntryPacket,
    entry_anchor: FrozenR2EntryAnchor,
    entry_result: OfflineR2EntryResult,
    shadow_release_sha256: Digest,
    candidate_policy_sha256: Digest,
    owner_signer_id: Identifier,
    operator_signer_id: Identifier,
    anchor: FrozenR2EvidenceAnchor,
    r0_index: R0OfflineResultIndex,
    r1_batch: OfflineShadowDecisionBatch,
    trusts: tuple[PhaseReviewTrust, PhaseReviewTrust, PhaseReviewTrust],
    r0_review: SignedPhaseReview | None,
    r1_review: SignedPhaseReview | None,
    oncall_review: SignedPhaseReview | None,
    now: datetime,
) -> G606EvidenceAssessment:
    """Bind exact R0/R1 artifacts and signed review metadata to a proposed R2."""
    _utc(now)
    reasons: set[str] = set()
    mapping = _trust_map(
        trusts,
        phases=("R0", "R1", "ONCALL"),
        owner_signer_id=owner_signer_id,
        operator_signer_id=operator_signer_id,
        reasons=reasons,
    )
    if (
        digest(canonical_bytes(ContractRoster(trusts=trusts)))
        != anchor.trust_roster_sha256
    ):
        reasons.add("review_trust_binding_mismatch")
    r0_sha256 = digest(canonical_bytes(r0_index))
    r1_sha256 = digest(canonical_bytes(r1_batch))
    source_set_sha256 = digest(
        json.dumps(
            [(item.relative_path, item.sha256) for item in r0_index.source_files],
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if (
        now >= anchor.valid_until
        or packet.proposed_at != now
        or entry_result.status != "reviewable"
        or not entry_result.readiness_checked
        or not entry_result.signed_owner_decision_checked
    ):
        reasons.add("r2_base_not_reviewable")
    if (
        anchor.manifest_sha256 != packet.manifest_sha256
        or anchor.manifest_sha256 != entry_anchor.manifest_sha256
        or anchor.r0_index_sha256 != r0_sha256
        or anchor.r1_batch_sha256 != r1_sha256
        or anchor.entry_result_sha256 != digest(canonical_bytes(entry_result))
        or anchor.oncall_evidence_sha256 != packet.oncall_evidence_sha256
        or anchor.oncall_evidence_sha256 != entry_anchor.oncall_evidence_sha256
        or packet.r0.evidence_sha256 != r0_sha256
        or entry_anchor.r0_review_sha256 != r0_sha256
        or packet.r1.evidence_sha256 != r1_sha256
        or entry_anchor.r1_review_sha256 != r1_sha256
        or packet.g6_05.broker_build_sha256 != anchor.broker_build_sha256
    ):
        reasons.add("r2_evidence_binding_mismatch")
    if (
        r0_index.status != "synthetic_pass"
        or tuple(item.suite_id for item in r0_index.suites)
        != tuple(suite_id for suite_id, _ in R0_SUITES)
        or tuple(item.relative_path for item in r0_index.source_files)
        != R0_SOURCE_PATHS
        or r0_index.bound_source_set_sha256 != source_set_sha256
        or any(
            item.status != "synthetic_pass"
            or item.expected_case_count == 0
            or item.ran_count != item.expected_case_count
            or item.failure_count
            or item.error_count
            or item.skipped_count
            or item.expected_failure_count
            or item.unexpected_success_count
            for item in r0_index.suites
        )
    ):
        reasons.add("r0_index_invalid")
    observed_tasks = tuple(
        sorted(item.task_session_sha256 for item in r1_batch.decisions)
    )
    if (
        r1_batch.manifest_sha256 != anchor.manifest_sha256
        or r1_batch.release_sha256 != shadow_release_sha256
        or r1_batch.candidate_policy_sha256 != candidate_policy_sha256
        or observed_tasks != anchor.expected_task_session_sha256
        or any(
            item.checked_at > packet.r1.reviewed_at
            or item.checked_at >= now
            or item.route_observed_at > item.checked_at
            or item.route_valid_until <= item.checked_at
            for item in r1_batch.decisions
        )
    ):
        reasons.add("r1_batch_invalid")
    for reference, signed in (
        (packet.r0, r0_review),
        (packet.r1, r1_review),
    ):
        if signed is None or (
            reference.status != "accepted"
            or reference.reviewer_id != signed.review.reviewer_id
            or reference.reviewed_at != signed.review.reviewed_at
            or reference.valid_until != signed.review.valid_until
            or reference.manifest_sha256 != anchor.manifest_sha256
            or reference.broker_build_sha256 != anchor.broker_build_sha256
        ):
            reasons.add(f"{reference.phase.lower()}_entry_reference_invalid")
    if not packet.oncall_ready:
        reasons.add("oncall_not_ready")
    _review(
        r0_review,
        trust=mapping.get("R0"),
        phase="R0",
        manifest_sha256=anchor.manifest_sha256,
        broker_build_sha256=anchor.broker_build_sha256,
        artifact_sha256=r0_sha256,
        source_set_sha256=source_set_sha256,
        upstream_sha256=None,
        earliest_review_at=r0_index.generated_at,
        now=now,
        reasons=reasons,
    )
    _review(
        r1_review,
        trust=mapping.get("R1"),
        phase="R1",
        manifest_sha256=anchor.manifest_sha256,
        broker_build_sha256=anchor.broker_build_sha256,
        artifact_sha256=r1_sha256,
        source_set_sha256=anchor.r1_source_set_sha256,
        upstream_sha256=None if r0_review is None else r0_review.review_sha256,
        earliest_review_at=max(item.checked_at for item in r1_batch.decisions),
        now=now,
        reasons=reasons,
    )
    _review(
        oncall_review,
        trust=mapping.get("ONCALL"),
        phase="ONCALL",
        manifest_sha256=anchor.manifest_sha256,
        broker_build_sha256=anchor.broker_build_sha256,
        artifact_sha256=anchor.oncall_evidence_sha256,
        source_set_sha256=anchor.r1_source_set_sha256,
        upstream_sha256=None if r1_review is None else r1_review.review_sha256,
        earliest_review_at=(now if r1_review is None else r1_review.review.reviewed_at),
        now=now,
        reasons=reasons,
    )
    return G606EvidenceAssessment(
        status="blocked" if reasons else "reviewable",
        reasons=tuple(sorted(reasons)),
        checked_phase_count=3,
    )


class ContractRoster(Contract):
    trusts: tuple[PhaseReviewTrust, ...]


def make_r5_source_bundle(
    *,
    broker_build_sha256: Digest,
    anchor: FrozenR5CloseAnchor,
    r4_packet: OfflineR4SurveillancePacket,
    r4_result: OfflineR4SurveillanceResult,
    preclose_state: WitnessedState,
    recovery_anchor: FrozenCohortRecoveryAnchor,
    reproduction: OfflineR4TriggerReproduction,
    closeout: CohortCloseoutPacket,
    r5_result: OfflineR5CloseResult,
) -> R5SourceBundle:
    return R5SourceBundle(
        manifest_sha256=anchor.manifest_sha256,
        broker_build_sha256=broker_build_sha256,
        r5_anchor_sha256=digest(canonical_bytes(anchor)),
        r4_packet_sha256=digest(canonical_bytes(r4_packet)),
        r4_result_sha256=digest(canonical_bytes(r4_result)),
        preclose_state_sha256=preclose_state.state_sha256,
        recovery_anchor_sha256=digest(canonical_bytes(recovery_anchor)),
        reproduction_sha256=digest(canonical_bytes(reproduction)),
        closeout_packet_sha256=digest(canonical_bytes(closeout)),
        r5_result_sha256=digest(canonical_bytes(r5_result)),
    )


def make_r6_source_bundle(
    *,
    broker_build_sha256: Digest,
    r5_bundle: R5SourceBundle,
    anchor: FrozenR6AssessmentAnchor,
    packet: OfflineR6AssessmentPacket,
    result: OfflineR6AssessmentResult,
) -> R6SourceBundle:
    return R6SourceBundle(
        manifest_sha256=anchor.manifest_sha256,
        broker_build_sha256=broker_build_sha256,
        r5_bundle_sha256=digest(canonical_bytes(r5_bundle)),
        r6_anchor_sha256=digest(canonical_bytes(anchor)),
        r6_packet_sha256=digest(canonical_bytes(packet)),
        r6_result_sha256=digest(canonical_bytes(result)),
        evidence_references_sha256=digest(canonical_bytes(packet.evidence)),
        dispatch_index_sha256=digest(canonical_bytes(packet.dispatch_index)),
        roster_sha256=packet.roster_sha256,
    )


def validate_r5_r6_source_evidence(
    *,
    anchor: FrozenR5R6EvidenceAnchor,
    r5_bundle: R5SourceBundle,
    r6_bundle: R6SourceBundle,
    r5_anchor: FrozenR5CloseAnchor,
    r4_packet: OfflineR4SurveillancePacket,
    r4_result: OfflineR4SurveillanceResult,
    preclose_state: WitnessedState,
    recovery_anchor: FrozenCohortRecoveryAnchor,
    reproduction: OfflineR4TriggerReproduction,
    closeout: CohortCloseoutPacket,
    r5_result: OfflineR5CloseResult,
    r6_anchor: FrozenR6AssessmentAnchor,
    r6_packet: OfflineR6AssessmentPacket,
    r6_result: OfflineR6AssessmentResult,
    trusts: tuple[PhaseReviewTrust, PhaseReviewTrust],
    r5_review: SignedPhaseReview | None,
    r6_review: SignedPhaseReview | None,
    now: datetime,
) -> G606EvidenceAssessment:
    """Require signed exact-source R5/R6 metadata before assessment handoff."""
    _utc(now)
    reasons: set[str] = set()
    mapping = _trust_map(
        trusts,
        phases=("R5", "R6"),
        owner_signer_id=r6_anchor.owner_signer_id,
        operator_signer_id=r6_anchor.operator_signer_id,
        reasons=reasons,
    )
    if (
        digest(canonical_bytes(ContractRoster(trusts=trusts)))
        != anchor.trust_roster_sha256
    ):
        reasons.add("review_trust_binding_mismatch")
    expected_r5 = make_r5_source_bundle(
        broker_build_sha256=anchor.broker_build_sha256,
        anchor=r5_anchor,
        r4_packet=r4_packet,
        r4_result=r4_result,
        preclose_state=preclose_state,
        recovery_anchor=recovery_anchor,
        reproduction=reproduction,
        closeout=closeout,
        r5_result=r5_result,
    )
    expected_r6 = make_r6_source_bundle(
        broker_build_sha256=anchor.broker_build_sha256,
        r5_bundle=r5_bundle,
        anchor=r6_anchor,
        packet=r6_packet,
        result=r6_result,
    )
    r5_sha256 = digest(canonical_bytes(r5_bundle))
    r6_sha256 = digest(canonical_bytes(r6_bundle))
    if (
        now >= anchor.valid_until
        or r5_result.status != "reviewable"
        or r6_result.status != "reviewable"
        or not r6_result.r5_reproduction_checked
    ):
        reasons.add("phase_result_not_reviewable")
    if (
        r5_bundle != expected_r5
        or r6_bundle != expected_r6
        or anchor.r5_bundle_sha256 != r5_sha256
        or anchor.r6_bundle_sha256 != r6_sha256
        or anchor.manifest_sha256 != r5_anchor.manifest_sha256
        or anchor.manifest_sha256 != r6_anchor.manifest_sha256
        or anchor.manifest_sha256 != r6_packet.manifest_sha256
        or r5_anchor.r4_packet_sha256 != r5_bundle.r4_packet_sha256
        or r5_anchor.r4_result_sha256 != r5_bundle.r4_result_sha256
        or r5_anchor.preclose_state_sha256 != r5_bundle.preclose_state_sha256
        or r6_anchor.r5_result_sha256 != r5_bundle.r5_result_sha256
        or r6_anchor.closeout_packet_sha256 != r5_bundle.closeout_packet_sha256
        or r6_anchor.r5_reproduction_sha256 != r5_bundle.reproduction_sha256
        or r6_anchor.evidence_references_sha256 != r6_bundle.evidence_references_sha256
        or r6_anchor.dispatch_index_sha256 != r6_bundle.dispatch_index_sha256
        or r6_anchor.roster_sha256 != r6_bundle.roster_sha256
        or reproduction.status != "reproduced"
        or reproduction.reproduced_at != r5_anchor.triggered_at
    ):
        reasons.add("phase_source_binding_mismatch")
    if (
        r5_review is None
        or r6_review is None
        or r6_packet.reviewer_id != r6_review.review.reviewer_id
        or r6_packet.review_status != "accepted"
        or r6_packet.reviewed_at != r6_review.review.reviewed_at
        or r6_packet.reviewed_at != now
        or r6_packet.prepared_at < closeout.prepared_at
        or r5_review.review.reviewed_at < closeout.prepared_at
        or r5_review.review.reviewed_at > r6_review.review.reviewed_at
    ):
        reasons.add("phase_review_sequence_invalid")
    _review(
        r5_review,
        trust=mapping.get("R5"),
        phase="R5",
        manifest_sha256=anchor.manifest_sha256,
        broker_build_sha256=anchor.broker_build_sha256,
        artifact_sha256=r5_sha256,
        source_set_sha256=anchor.source_set_sha256,
        upstream_sha256=r5_bundle.reproduction_sha256,
        earliest_review_at=closeout.prepared_at,
        now=now,
        reasons=reasons,
    )
    _review(
        r6_review,
        trust=mapping.get("R6"),
        phase="R6",
        manifest_sha256=anchor.manifest_sha256,
        broker_build_sha256=anchor.broker_build_sha256,
        artifact_sha256=r6_sha256,
        source_set_sha256=anchor.source_set_sha256,
        upstream_sha256=None if r5_review is None else r5_review.review_sha256,
        earliest_review_at=(now if r5_review is None else r5_review.review.reviewed_at),
        now=now,
        reasons=reasons,
    )
    return G606EvidenceAssessment(
        status="blocked" if reasons else "reviewable",
        reasons=tuple(sorted(reasons)),
        checked_phase_count=2,
    )
