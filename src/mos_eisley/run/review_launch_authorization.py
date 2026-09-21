"""A separate, domain-separated independent decision for one exact review launch."""

import base64
import binascii
from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.review_conformance_admission import ReviewConformanceRuntime
from mos_eisley.run.review_conformance_authorization import (
    ReviewConformanceSigner,
)

_DOMAIN = b"mos-eisley/review-launch-decision/v1\x00"


def _decode(value: str, size: int) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("invalid launch signature encoding") from None
    if len(raw) != size or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("noncanonical launch signature encoding")
    return raw


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("launch decision timestamps require explicit UTC")
    return value


class ReviewLaunchAuthorityPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_launch_authority_policy"] = "review_launch_authority_policy"
    policy_id: Identifier
    reviewers: Annotated[
        tuple[ReviewConformanceSigner, ...], Field(min_length=1, max_length=20)
    ]
    valid_from: datetime
    valid_until: datetime
    max_decision_seconds: Annotated[int, Field(gt=0, le=600)]
    max_reserved_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    local_and_phase_approvals_required: Literal[True] = True
    automatic_activation_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.valid_from >= self.valid_until:
            raise ValueError("launch authority window must be positive")
        ids = tuple(s.signer_id for s in self.reviewers)
        if ids != tuple(sorted(set(ids))) or len(
            {s.key_sha256 for s in self.reviewers}
        ) != len(ids):
            raise ValueError(
                "launch reviewers require sorted distinct identities and keys"
            )
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class ReviewLaunchScope(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_launch_scope"] = "review_launch_scope"
    launch_authority_policy_sha256: Digest
    phase_authority_policy_sha256: Digest
    configuration_sha256: Digest
    critic_preview_sha256: Digest
    seal_sha256: Digest
    evidence_file_sha256: Digest
    runtime: ReviewConformanceRuntime
    ledger_path: Annotated[str, Field(min_length=1, max_length=4096)]
    artifact_directory: Annotated[str, Field(min_length=1, max_length=4096)]
    max_reserved_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)


class ReviewLaunchDecision(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_launch_decision"] = "review_launch_decision"
    scope: ReviewLaunchScope
    issued_at: datetime
    valid_until: datetime
    # Required independent assertions, never inferred from fixture or verifier success.
    commitment_custody_reviewed: Literal[True]
    credentialed_campaign_reviewed: Literal[True]
    independent_observer_assessment_reviewed: Literal[True]
    exact_launch_authorized: Literal[True] = True
    local_and_phase_approvals_required: Literal[True] = True
    automatic_retry_authorized: Literal[False] = False
    automatic_activation_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)


class SignedReviewLaunchDecision(Contract):
    schema_version: Literal[1] = 1
    decision: ReviewLaunchDecision
    signer_id: Identifier
    public_key_sha256: Digest
    signature_base64: Annotated[str, Field(min_length=88, max_length=88)]

    @model_validator(mode="after")
    def valid_encoding(self) -> Self:
        _decode(self.signature_base64, 64)
        return self


def sign_review_launch_decision(
    decision: ReviewLaunchDecision, signer_id: str, key: Ed25519PrivateKey
) -> SignedReviewLaunchDecision:
    decision = ReviewLaunchDecision.model_validate_json(canonical_bytes(decision))
    return SignedReviewLaunchDecision(
        decision=decision,
        signer_id=signer_id,
        public_key_sha256=digest(key.public_key().public_bytes_raw()),
        signature_base64=base64.b64encode(
            key.sign(_DOMAIN + canonical_bytes(decision))
        ).decode("ascii"),
    )


def verify_review_launch_decision(
    signed: SignedReviewLaunchDecision,
    policy: ReviewLaunchAuthorityPolicy,
    expected: ReviewLaunchScope,
    now: datetime,
) -> ReviewLaunchDecision:
    signed = SignedReviewLaunchDecision.model_validate_json(canonical_bytes(signed))
    policy = ReviewLaunchAuthorityPolicy.model_validate_json(canonical_bytes(policy))
    expected = ReviewLaunchScope.model_validate_json(canonical_bytes(expected))
    now = _utc(now)
    decision = signed.decision
    if (
        decision.scope != expected
        or policy.sha256 != expected.launch_authority_policy_sha256
        or not policy.valid_from
        <= decision.issued_at
        <= now
        < decision.valid_until
        <= min(policy.valid_until, expected.expires_at)
        or (decision.valid_until - decision.issued_at).total_seconds()
        > policy.max_decision_seconds
        or expected.max_reserved_microusd > policy.max_reserved_microusd
    ):
        raise ValueError(
            "launch decision scope, time or spending differs from admission"
        )
    enrolled = [
        s
        for s in policy.reviewers
        if s.signer_id == signed.signer_id and s.key_sha256 == signed.public_key_sha256
    ]
    if len(enrolled) != 1:
        raise ValueError("independent launch reviewer is not enrolled")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(enrolled[0].public_key_base64, 32)
        ).verify(
            _decode(signed.signature_base64, 64), _DOMAIN + canonical_bytes(decision)
        )
    except (InvalidSignature, ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid independent launch decision signature") from None
    return decision
