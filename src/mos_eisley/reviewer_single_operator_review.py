"""Owner-attested G4 cross-provider review, separate from independent review."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import (
    Contract,
    CriticResult,
    CriticSpec,
    Digest,
    Identifier,
    JudgeDecision,
    JudgeRequest,
    ReviewPolicy,
    Verdict,
    canonical_bytes,
    digest,
)
from mos_eisley.review.citations import citation_bound_request, validate_evidence
from mos_eisley.review.pipeline import critic_quorum_met, judge_findings, judge_verdict
from mos_eisley.reviewer_independent_review import REVIEW_RECORD_BYTES, G4ReviewSubject
from mos_eisley.reviewer_provenance import (
    AuthenticatedG4ProvenanceRecord,
    G4ArtifactSignature,
    verify_provenance_signature,
)

_AUTHORITY_DOMAIN = b"mos-eisley/g4-single-operator-review-authority/v1\x00"
_DECISION_DOMAIN = b"mos-eisley/g4-single-operator-review-decision/v1\x00"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("G4 single-operator review timestamps require UTC")
    return value


class G4SingleOperatorReviewAuthority(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_single_operator_review_authority"] = (
        "g4_single_operator_review_authority"
    )
    authority_id: Identifier
    provenance_policy_sha256: Digest
    subject_sha256: Digest
    review_policy: ReviewPolicy
    critics: Annotated[tuple[CriticSpec, ...], Field(min_length=2, max_length=8)]
    critic_request_sha256s: Annotated[
        tuple[Digest, ...], Field(min_length=2, max_length=8)
    ]
    judge_provider: Identifier
    judge_model: Identifier
    issued_at: datetime
    expires_at: datetime
    single_operator_self_review_risk_accepted: Literal[True] = True
    provider_dispatch_authorized: Literal[False] = False
    independent_review_evidence_passed: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def valid_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        ids = tuple(item.id for item in self.critics)
        if (
            not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24)
            or ids != tuple(sorted(ids))
            or len(ids) != len(set(ids))
            or len(self.critics) != len(self.critic_request_sha256s)
            or self.review_policy.min_critics < 2
            or self.review_policy.min_providers < 2
            or len(self.critics) < self.review_policy.min_critics
            or len({item.provider for item in self.critics})
            < self.review_policy.min_providers
        ):
            raise ValueError("invalid G4 single-operator review authority")
        return self


class SignedG4SingleOperatorReviewAuthority(Contract):
    authority: G4SingleOperatorReviewAuthority
    signature: G4ArtifactSignature

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4SingleOperatorCriticObservation(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_single_operator_critic_observation"] = (
        "g4_single_operator_critic_observation"
    )
    result: CriticResult
    request_sha256: Digest
    response_sha256: Digest | None = None
    audit_sha256: Digest | None = None
    observed_at: datetime
    full_subject_review_claimed: bool

    @field_validator("observed_at")
    @classmethod
    def valid_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        completed = self.result.status == "completed"
        if (
            self.full_subject_review_claimed != completed
            or (self.response_sha256 is not None) != completed
            or (self.audit_sha256 is not None) != completed
        ):
            raise ValueError("G4 critic observation disagrees with completion")
        return self

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4SingleOperatorJudgeObservation(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_single_operator_judge_observation"] = (
        "g4_single_operator_judge_observation"
    )
    provider: Identifier
    model: Identifier
    request_sha256: Digest
    response_sha256: Digest
    audit_sha256: Digest
    decision: JudgeDecision
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def valid_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


class G4SingleOperatorReviewDecision(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_single_operator_review_decision"] = (
        "g4_single_operator_review_decision"
    )
    authority_sha256: Digest
    subject_sha256: Digest
    critic_artifact_sha256s: Annotated[
        tuple[Digest, ...], Field(min_length=2, max_length=8)
    ]
    judge_artifact_sha256: Digest
    verdict: Verdict
    decided_at: datetime
    single_operator_self_review_risk_accepted: Literal[True] = True
    independent_review_evidence_passed: Literal[False] = False
    independent_human_review_proven: Literal[False] = False
    provider_operation_proven: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @field_validator("decided_at")
    @classmethod
    def valid_utc(cls, value: datetime) -> datetime:
        return _utc(value)


class SignedG4SingleOperatorReviewDecision(Contract):
    decision: G4SingleOperatorReviewDecision
    signature: G4ArtifactSignature


class G4SingleOperatorReviewRecord(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_single_operator_review_record"] = (
        "g4_single_operator_review_record"
    )
    subject: G4ReviewSubject
    authority: SignedG4SingleOperatorReviewAuthority
    critics: Annotated[
        tuple[G4SingleOperatorCriticObservation, ...], Field(min_length=2, max_length=8)
    ]
    judge: G4SingleOperatorJudgeObservation
    decision: SignedG4SingleOperatorReviewDecision
    single_operator_review_evidence_passed: bool
    independent_review_evidence_passed: Literal[False] = False
    independent_human_review_proven: Literal[False] = False
    provider_operation_proven: Literal[False] = False
    acceptance_authorized: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            self.single_operator_review_evidence_passed
            != (self.decision.decision.verdict.decision == "accept")
            or len(canonical_bytes(self)) > REVIEW_RECORD_BYTES
        ):
            raise ValueError("G4 single-operator record is inconsistent")
        return self

    @property
    def record_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _sign(
    value: Contract, signer_id: str, key: Ed25519PrivateKey, domain: bytes
) -> G4ArtifactSignature:
    return G4ArtifactSignature(
        signer_id=signer_id,
        public_key_sha256=digest(key.public_key().public_bytes_raw()),
        signature_base64=base64.b64encode(
            key.sign(domain + canonical_bytes(value))
        ).decode("ascii"),
    )


def sign_single_operator_review_authority(
    authority: G4SingleOperatorReviewAuthority,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4SingleOperatorReviewAuthority:
    return SignedG4SingleOperatorReviewAuthority(
        authority=authority,
        signature=_sign(authority, signer_id, key, _AUTHORITY_DOMAIN),
    )


def sign_single_operator_review_decision(
    decision: G4SingleOperatorReviewDecision,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedG4SingleOperatorReviewDecision:
    return SignedG4SingleOperatorReviewDecision(
        decision=decision,
        signature=_sign(decision, signer_id, key, _DECISION_DOMAIN),
    )


def assess_single_operator_review(
    subject: G4ReviewSubject,
    provenance: AuthenticatedG4ProvenanceRecord,
    authority: SignedG4SingleOperatorReviewAuthority,
    critics: tuple[G4SingleOperatorCriticObservation, ...],
    judge: G4SingleOperatorJudgeObservation,
    signed_decision: SignedG4SingleOperatorReviewDecision,
) -> G4SingleOperatorReviewRecord:
    """Verify one owner, two provider families, citations, hashes, and verdict."""
    grant = authority.authority
    if provenance.policy.operator_mode != "single_operator":
        raise ValueError("G4 one-signer review requires single-operator provenance")
    creator = verify_provenance_signature(
        grant, authority.signature, provenance.policy, "creator", _AUTHORITY_DOMAIN
    )
    if (
        grant.provenance_policy_sha256 != provenance.policy.policy_sha256
        or grant.subject_sha256 != subject.subject_sha256
        or subject.provenance_sha256 != provenance.record_sha256
        or subject.base_revision != provenance.git_provenance.provenance.base_revision
        or subject.source_revision
        != provenance.git_provenance.provenance.source_revision
        or subject.approved_plan_sha256
        != provenance.creator_approval.approval.approved_plan_sha256
        or not provenance.policy.valid_from
        <= grant.issued_at
        < grant.expires_at
        <= provenance.policy.valid_until
        or grant.issued_at < provenance.creator_approval.approval.issued_at
        or grant.issued_at < subject.final_suite_started_at
        or len(critics) != len(grant.critics)
    ):
        raise ValueError("G4 one-signer authority differs from its exact lineage")
    results: list[CriticResult] = []
    for observation, spec, expected_hash in zip(
        critics, grant.critics, grant.critic_request_sha256s, strict=True
    ):
        request = citation_bound_request(subject.brief, spec.persona)
        if (
            observation.result.critic != spec
            or observation.request_sha256 != digest(canonical_bytes(request))
            or observation.request_sha256 != expected_hash
            or len(canonical_bytes(request)) > grant.review_policy.max_request_bytes
            or not grant.issued_at <= observation.observed_at < grant.expires_at
        ):
            raise ValueError("G4 critic observation differs from the frozen request")
        if observation.result.status == "completed":
            assert observation.result.critique is not None
            validate_evidence(request, observation.result.critique.findings)
        results.append(observation.result)
    if not critic_quorum_met(tuple(results), grant.review_policy):
        raise ValueError("G4 one-signer critic quorum was not met")
    judge_request = JudgeRequest(
        brief=subject.brief, findings=judge_findings(tuple(results))
    )
    if (
        len(canonical_bytes(judge_request)) > grant.review_policy.max_request_bytes
        or judge.provider != grant.judge_provider
        or judge.model != grant.judge_model
        or judge.request_sha256 != digest(canonical_bytes(judge_request))
        or not max(item.observed_at for item in critics)
        <= judge.observed_at
        < grant.expires_at
    ):
        raise ValueError("G4 judge observation differs from the derived request")
    verdict = judge_verdict(judge_request, judge.decision)
    decision = signed_decision.decision
    decision_signer = verify_provenance_signature(
        decision,
        signed_decision.signature,
        provenance.policy,
        "creator",
        _DECISION_DOMAIN,
    )
    if (
        decision_signer != creator
        or decision.authority_sha256 != authority.artifact_sha256
        or decision.subject_sha256 != subject.subject_sha256
        or decision.critic_artifact_sha256s
        != tuple(item.artifact_sha256 for item in critics)
        or decision.judge_artifact_sha256 != judge.artifact_sha256
        or decision.verdict != verdict
        or not judge.observed_at <= decision.decided_at < grant.expires_at
    ):
        raise ValueError("G4 owner decision differs from the exact review evidence")
    return G4SingleOperatorReviewRecord(
        subject=subject,
        authority=authority,
        critics=critics,
        judge=judge,
        decision=signed_decision,
        single_operator_review_evidence_passed=verdict.decision == "accept",
    )
