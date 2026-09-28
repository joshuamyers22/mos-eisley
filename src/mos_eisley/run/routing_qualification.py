"""Offline G6-05 packet checks; this module grants no routing authority."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.protocol import Effort
from mos_eisley.evaluation.models import RouteCandidate

if TYPE_CHECKING:
    from mos_eisley.run.routing_host_drills import (
        HostDrillEvidenceIndex,
        HostDrillProtocol,
    )

_REVIEW_DOMAIN = b"mos-eisley/g6-offline-qualification-review/v1\0"
_REQUIRED = (
    "G6-01",
    "G6-02",
    "G6-03",
    "G6-04",
    "Q1",
    "Q2",
    "Q3",
    "Q4",
    "Q5",
    "Q6",
    *(f"O{number:02d}" for number in range(1, 11)),
)
_ROLES = ("operations", "owner", "security", "statistical")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("qualification time must use explicit UTC")
    return value


def _decode(value: str, size: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("qualification key or signature is not base64") from None
    if len(decoded) != size or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("qualification key or signature is not canonical")
    return decoded


class QualificationPrerequisite(Contract):
    milestone: Literal["G2", "G3", "G4"]
    required: bool
    applicability_basis_sha256: Digest


class QualificationScope(Contract):
    owner_id: Identifier
    cohort_id: Identifier
    task_enrollment_sha256: Digest
    task_types: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=64)]
    stages: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=64)]
    valid_from: datetime
    valid_until: datetime
    max_tasks: Annotated[int, Field(gt=0, le=100_000)]
    task_ceiling_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    session_ceiling_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    cohort_ceiling_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    request_maximum_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    unavailable_action: Literal["role_fallback", "fail_closed"]

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_scope(self) -> Self:
        if (
            self.valid_until <= self.valid_from
            or self.task_types != tuple(sorted(set(self.task_types)))
            or self.stages != tuple(sorted(set(self.stages)))
            or self.request_maximum_microusd
            > min(
                self.task_ceiling_microusd,
                self.session_ceiling_microusd,
                self.cohort_ceiling_microusd,
            )
        ):
            raise ValueError("qualification scope is inconsistent")
        return self


class ExactRouteMetadata(Contract):
    """Content-free identity; the candidate digest needs external source review."""

    candidate_id: Digest
    backend: Identifier
    provider: Identifier
    model: Identifier
    effort: Effort
    client_version: Annotated[str, Field(min_length=1, max_length=200)]
    registry_sha256: Digest
    capabilities_sha256: Digest
    prompt_asset_sha256: Digest

    @classmethod
    def from_candidate(cls, route: RouteCandidate, capabilities_sha256: str) -> Self:
        return cls(
            candidate_id=route.candidate_id,
            backend=route.backend,
            provider=route.provider,
            model=route.model,
            effort=route.effort,
            client_version=route.client_version,
            registry_sha256=route.registry_sha256,
            capabilities_sha256=capabilities_sha256,
            prompt_asset_sha256=digest(canonical_bytes(route.prompt)),
        )


class QualifiedRoute(Contract):
    identity: ExactRouteMetadata
    purpose: Literal["selected", "fallback", "both"]
    pricing_basis: Identifier
    max_normalized_cost_microusd: Annotated[
        float, Field(ge=0, le=1_000_000_000_000_000)
    ]


class QualificationCandidate(Contract):
    candidate_policy_sha256: Digest
    sealed_study_sha256: Digest
    plan_sha256: Digest
    feature_partition_sha256: Digest
    g5_claim_sha256: Digest
    g5_holdout_report_sha256: Digest
    g5_use_claim_sha256: Digest
    g5_population_id: Identifier
    g5_estimand_id: Identifier
    routes: Annotated[tuple[QualifiedRoute, ...], Field(min_length=1, max_length=256)]

    @model_validator(mode="after")
    def canonical_routes(self) -> Self:
        ids = tuple(item.identity.candidate_id for item in self.routes)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("qualification routes must be unique and sorted")
        if not any(item.purpose in ("selected", "both") for item in self.routes):
            raise ValueError("qualification requires a selected route")
        return self


class QualificationAuthority(Contract):
    promotion_authority_policy_sha256: Digest
    promotion_receipt_sha256: Digest
    activation_authority_policy_sha256: Digest
    activation_policy_sha256: Digest
    activation_eligibility_sha256: Digest
    control_anchor_policy_sha256: Digest
    latest_control_entry_sha256: Digest
    preflight_sha256: Digest
    promotion_signer_id: Identifier
    activation_signer_id: Identifier
    readiness_signer_id: Identifier
    control_signer_id: Identifier

    @model_validator(mode="after")
    def separated_signers(self) -> Self:
        ids = (
            self.promotion_signer_id,
            self.activation_signer_id,
            self.readiness_signer_id,
            self.control_signer_id,
        )
        if len(set(ids)) != len(ids):
            raise ValueError("qualification authority roles must be distinct")
        return self


class QualificationWitness(Contract):
    enrollment_sha256: Digest
    budget_policy_sha256: Digest
    epoch_id: Digest
    checkpoint_id: Identifier
    operator_id: Identifier
    deployment_id: Identifier
    persistence_design_sha256: Digest
    recovery_runbook_sha256: Digest


class QualificationRuntime(Contract):
    broker_build_sha256: Digest
    target_host_id: Identifier
    broker_os_identity: Identifier
    worker_os_identity: Identifier
    credential_custodian_id: Identifier
    monitor_id: Identifier
    audit_sink_id: Identifier
    clock_source_id: Identifier
    witness_network_policy_sha256: Digest
    stop_runbook_sha256: Digest
    alert_contact_id: Identifier
    transport_retries_disabled: Literal[True] = True

    @model_validator(mode="after")
    def separate_worker(self) -> Self:
        if self.broker_os_identity == self.worker_os_identity:
            raise ValueError("qualification worker and broker identities overlap")
        return self


class QualificationVerification(Contract):
    test_protocol_sha256: Digest
    severity_rubric_sha256: Digest
    retention_policy_sha256: Digest
    max_stop_latency_ms: Annotated[int, Field(gt=0, le=86_400_000)]
    max_alert_latency_ms: Annotated[int, Field(gt=0, le=86_400_000)]
    max_route_evidence_age_seconds: Annotated[int, Field(gt=0, le=604_800)]
    max_workers: Annotated[int, Field(gt=0, le=1024)]
    max_crash_cases: Annotated[int, Field(gt=0, le=10_000)]
    max_synthetic_admissions: Annotated[int, Field(gt=0, le=1_000_000)]
    paid_provider_calls: Literal[0] = 0


class OfflineQualificationPacket(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["g6_offline_qualification_packet"] = "g6_offline_qualification_packet"
    frozen_at: datetime
    decision_deadline: datetime
    prerequisites: Annotated[
        tuple[QualificationPrerequisite, ...], Field(min_length=3, max_length=3)
    ]
    scope: QualificationScope
    candidate: QualificationCandidate
    authority: QualificationAuthority
    witness: QualificationWitness
    runtime: QualificationRuntime
    verification: QualificationVerification

    @field_validator("frozen_at", "decision_deadline")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        if (
            self.decision_deadline <= self.frozen_at
            or self.decision_deadline > self.scope.valid_until
            or tuple(item.milestone for item in self.prerequisites)
            != ("G2", "G3", "G4")
            or (
                self.scope.unavailable_action == "role_fallback"
                and not any(
                    item.purpose in ("fallback", "both")
                    for item in self.candidate.routes
                )
            )
            or (
                self.scope.unavailable_action == "fail_closed"
                and any(
                    item.purpose in ("fallback", "both")
                    for item in self.candidate.routes
                )
            )
        ):
            raise ValueError("qualification packet scope or prerequisite mismatch")
        return self

    @property
    def packet_sha256(self) -> str:
        return digest(canonical_bytes(self))


class QualificationEvidenceRecord(Contract):
    evidence_id: Identifier
    status: Literal["pass", "fail", "unavailable"]
    source_sha256: Digest | None = None
    producer_id: Identifier
    checker_id: Identifier
    collected_at: datetime
    valid_until: datetime

    @field_validator("collected_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_record(self) -> Self:
        if (
            self.valid_until <= self.collected_at
            or self.producer_id == self.checker_id
            or (self.status == "pass" and self.source_sha256 is None)
        ):
            raise ValueError("qualification evidence record is invalid")
        return self


class QualificationRouteObservation(Contract):
    identity: ExactRouteMetadata
    pricing_basis: Identifier
    normalized_cost_microusd: Annotated[float, Field(ge=0, le=1_000_000_000_000_000)]
    catalog_status: Literal["available", "unavailable"]
    catalog_evidence_sha256: Digest
    pricing_evidence_sha256: Digest
    conformance_status: Literal["passed", "failed"]
    conformance_evidence_sha256: Digest
    drift_status: Literal["passed", "failed"]
    drift_evidence_sha256: Digest
    observed_at: datetime
    valid_until: datetime
    source_revision: Identifier
    method_sha256: Digest
    producer_id: Identifier
    checker_id: Identifier

    @field_validator("observed_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_observation(self) -> Self:
        if self.producer_id == self.checker_id or self.valid_until <= self.observed_at:
            raise ValueError("qualification route observation is invalid")
        return self


class QualificationDrillSummary(Contract):
    workers_used: Annotated[int, Field(gt=0, le=1024)]
    crash_cases_run: Annotated[int, Field(gt=0, le=10_000)]
    synthetic_admissions: Annotated[int, Field(gt=0, le=1_000_000)]
    paid_provider_calls: Literal[0] = 0
    measured_max_stop_latency_ms: Annotated[int, Field(ge=0, le=86_400_000)]
    measured_max_alert_latency_ms: Annotated[int, Field(ge=0, le=86_400_000)]


class OfflineQualificationEvidence(Contract):
    schema_version: Literal[2] = 2
    packet_sha256: Digest
    drill_protocol_sha256: Digest
    drill_index_sha256: Digest
    assembled_at: datetime
    records: Annotated[tuple[QualificationEvidenceRecord, ...], Field(max_length=64)]
    route_observations: Annotated[
        tuple[QualificationRouteObservation, ...], Field(max_length=256)
    ]
    drill_summary: QualificationDrillSummary

    @field_validator("assembled_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def canonical_entries(self) -> Self:
        ids = tuple(item.evidence_id for item in self.records)
        routes = tuple(item.identity.candidate_id for item in self.route_observations)
        if ids != tuple(sorted(set(ids))) or routes != tuple(sorted(set(routes))):
            raise ValueError("qualification evidence entries must be unique and sorted")
        return self

    @property
    def evidence_sha256(self) -> str:
        return digest(canonical_bytes(self))


class QualificationReviewer(Contract):
    role: Literal["operations", "owner", "security", "statistical"]
    reviewer_id: Identifier
    public_key_base64: str

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        _decode(self.public_key_base64, 32)
        return self


class OfflineQualificationReviewTrust(Contract):
    schema_version: Literal[1] = 1
    reviewers: Annotated[
        tuple[QualificationReviewer, ...], Field(min_length=4, max_length=4)
    ]

    @model_validator(mode="after")
    def independent_roles(self) -> Self:
        roles = tuple(item.role for item in self.reviewers)
        ids = tuple(item.reviewer_id for item in self.reviewers)
        keys = tuple(item.public_key_base64 for item in self.reviewers)
        if roles != _ROLES or len(set(ids)) != 4 or len(set(keys)) != 4:
            raise ValueError("qualification reviewers must be independently enrolled")
        return self


class OfflineQualificationReviewDecision(Contract):
    schema_version: Literal[1] = 1
    role: Literal["operations", "owner", "security", "statistical"]
    reviewer_id: Identifier
    packet_sha256: Digest
    evidence_sha256: Digest
    decision: Literal["accept", "reject"]
    reviewed_at: datetime
    valid_until: datetime

    @field_validator("reviewed_at", "valid_until")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_until <= self.reviewed_at:
            raise ValueError("qualification review window is invalid")
        return self


class SignedOfflineQualificationReview(Contract):
    review: OfflineQualificationReviewDecision
    signature_base64: str

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64)
        return self


def sign_synthetic_qualification_review(
    review: OfflineQualificationReviewDecision, private_key: bytes
) -> SignedOfflineQualificationReview:
    """Fixture helper; a real reviewer must use independent key custody."""
    signature = Ed25519PrivateKey.from_private_bytes(private_key).sign(
        _REVIEW_DOMAIN + canonical_bytes(review)
    )
    return SignedOfflineQualificationReview(
        review=review, signature_base64=base64.b64encode(signature).decode("ascii")
    )


class OfflineQualificationAssessment(Contract):
    schema_version: Literal[1] = 1
    packet_sha256: Digest
    evidence_sha256: Digest
    reviewable: bool
    reasons: tuple[Identifier, ...]
    qualification_authorized: Literal[False] = False
    dispatch_authorized: Literal[False] = False


def validate_offline_qualification_packet(
    *,
    packet: OfflineQualificationPacket,
    evidence: OfflineQualificationEvidence,
    reviews: tuple[SignedOfflineQualificationReview, ...],
    trust: OfflineQualificationReviewTrust,
    drill_protocol: HostDrillProtocol,
    drill_index: HostDrillEvidenceIndex,
    now: datetime,
) -> OfflineQualificationAssessment:
    """Check bounded packet metadata; never authenticate underlying G5 outcomes."""
    from mos_eisley.run.routing_host_drills import (
        drill_case_sha256,
        validate_joined_inert_host_drill_index,
    )

    _utc(now)
    reasons: set[str] = set()
    drill_assessment = validate_joined_inert_host_drill_index(
        packet=packet, protocol=drill_protocol, evidence=drill_index, now=now
    )
    if not drill_assessment.reviewable:
        reasons.add("drill_index_invalid")
    if (
        evidence.drill_protocol_sha256 != drill_protocol.protocol_sha256
        or evidence.drill_index_sha256 != drill_index.evidence_sha256
    ):
        reasons.add("drill_digest_mismatch")
    if (
        evidence.drill_summary.workers_used != drill_index.workers_used
        or evidence.drill_summary.crash_cases_run != drill_index.crash_cases_run
        or evidence.drill_summary.synthetic_admissions
        != drill_index.synthetic_admissions
        or evidence.drill_summary.paid_provider_calls
        != drill_index.paid_provider_calls
        or evidence.drill_summary.measured_max_stop_latency_ms
        != drill_index.measured_max_stop_latency_ms
        or evidence.drill_summary.measured_max_alert_latency_ms
        != drill_index.measured_max_alert_latency_ms
    ):
        reasons.add("drill_summary_mismatch")
    if not drill_index.assembled_at <= evidence.assembled_at:
        reasons.add("drill_evidence_time_invalid")
    if not packet.scope.valid_from <= now < packet.scope.valid_until:
        reasons.add("scope_stale")
    if not packet.frozen_at <= now < packet.decision_deadline:
        reasons.add("packet_stale")
    if evidence.packet_sha256 != packet.packet_sha256:
        reasons.add("packet_digest_mismatch")
    if not packet.frozen_at <= evidence.assembled_at <= now:
        reasons.add("evidence_time_invalid")
    if (
        evidence.drill_summary.workers_used > packet.verification.max_workers
        or evidence.drill_summary.crash_cases_run > packet.verification.max_crash_cases
        or evidence.drill_summary.synthetic_admissions
        > packet.verification.max_synthetic_admissions
        or evidence.drill_summary.measured_max_stop_latency_ms
        > packet.verification.max_stop_latency_ms
        or evidence.drill_summary.measured_max_alert_latency_ms
        > packet.verification.max_alert_latency_ms
    ):
        reasons.add("drill_limit_exceeded")

    required = set(_REQUIRED)
    required.update(item.milestone for item in packet.prerequisites if item.required)
    records = {item.evidence_id: item for item in evidence.records}
    if set(records) != required:
        reasons.add("evidence_coverage_invalid")
    for item in evidence.records:
        if item.status != "pass":
            reasons.add("evidence_not_passed")
        if (
            item.collected_at > evidence.assembled_at
            or not item.collected_at <= now < item.valid_until
        ):
            reasons.add("evidence_stale")
    for case_id in ("Q6", *(f"O{number:02d}" for number in range(1, 11))):
        record = records.get(case_id)
        if record is None:
            continue
        expected_sha256 = (
            drill_index.evidence_sha256
            if case_id == "Q6"
            else drill_case_sha256(drill_index, case_id)
        )
        if record.source_sha256 != expected_sha256:
            reasons.add("drill_record_mismatch")
        if (
            record.producer_id != drill_protocol.operator_id
            or record.checker_id != drill_protocol.independent_checker_id
        ):
            reasons.add("drill_record_role_mismatch")
        if record.collected_at < drill_index.assembled_at:
            reasons.add("drill_record_time_invalid")

    required_routes = {
        item.identity.candidate_id: item for item in packet.candidate.routes
    }
    observations = {
        item.identity.candidate_id: item for item in evidence.route_observations
    }
    if set(observations) != set(required_routes):
        reasons.add("route_coverage_invalid")
    for candidate_id, item in observations.items():
        expected = required_routes.get(candidate_id)
        if expected is None:
            continue
        if (
            item.identity != expected.identity
            or item.pricing_basis != expected.pricing_basis
            or item.normalized_cost_microusd > expected.max_normalized_cost_microusd
            or item.catalog_status != "available"
            or item.conformance_status != "passed"
            or item.drift_status != "passed"
        ):
            reasons.add("route_ineligible")
        if (
            item.observed_at > evidence.assembled_at
            or not item.observed_at <= now < item.valid_until
            or now - item.observed_at
            > timedelta(seconds=packet.verification.max_route_evidence_age_seconds)
        ):
            reasons.add("route_stale")

    enrolled = {item.role: item for item in trust.reviewers}
    received = {item.review.role: item for item in reviews}
    if len(reviews) != len(received) or set(received) != set(enrolled):
        reasons.add("review_coverage_invalid")
    for role, signed in received.items():
        expected = enrolled.get(role)
        review = signed.review
        if expected is None:
            continue
        if (
            review.reviewer_id != expected.reviewer_id
            or review.packet_sha256 != packet.packet_sha256
            or review.evidence_sha256 != evidence.evidence_sha256
        ):
            reasons.add("review_binding_invalid")
        if review.decision != "accept":
            reasons.add("review_rejected")
        if not evidence.assembled_at <= review.reviewed_at <= now < review.valid_until:
            reasons.add("review_stale")
        try:
            Ed25519PublicKey.from_public_bytes(
                _decode(expected.public_key_base64, 32)
            ).verify(
                _decode(signed.signature_base64, 64),
                _REVIEW_DOMAIN + canonical_bytes(review),
            )
        except (InvalidSignature, ValueError):
            reasons.add("review_signature_invalid")

    return OfflineQualificationAssessment(
        packet_sha256=packet.packet_sha256,
        evidence_sha256=evidence.evidence_sha256,
        reviewable=not reasons,
        reasons=tuple(sorted(reasons)),
    )
