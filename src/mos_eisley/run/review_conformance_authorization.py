"""Independent, phase-specific authorization for a future credentialed review probe."""

import base64
import binascii
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.run.process import MAX_WIRE_BYTES
from mos_eisley.run.review_controller import (
    ControllerCriticPreview,
    ControllerJudgePreview,
    ControllerStart,
)

_DOMAIN = b"mos-eisley/review-conformance-authorization/v1\x00"
Amount = Annotated[int, Field(ge=0, le=1_000_000_000_000)]
ImageID = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


def _decode(value: str, size: int) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("invalid conformance signature encoding") from None
    if len(raw) != size or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("noncanonical conformance signature encoding")
    return raw


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("review conformance timestamps require explicit UTC")
    return value


class ReviewConformanceSigner(Contract):
    signer_id: Identifier
    public_key_base64: Annotated[str, Field(min_length=44, max_length=44)]

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        _decode(self.public_key_base64, 32)
        return self

    @property
    def key_sha256(self) -> str:
        return digest(_decode(self.public_key_base64, 32))


def review_conformance_signer(
    signer_id: str, key: Ed25519PublicKey
) -> ReviewConformanceSigner:
    return ReviewConformanceSigner(
        signer_id=signer_id,
        public_key_base64=base64.b64encode(key.public_bytes_raw()).decode("ascii"),
    )


class ReviewConformanceAuthorityPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_conformance_authority_policy"] = (
        "review_conformance_authority_policy"
    )
    policy_id: Identifier
    authorities: Annotated[
        tuple[ReviewConformanceSigner, ...], Field(min_length=1, max_length=20)
    ]
    observers: Annotated[
        tuple[ReviewConformanceSigner, ...], Field(min_length=1, max_length=20)
    ]
    valid_from: datetime
    valid_until: datetime
    max_authorization_seconds: Annotated[int, Field(gt=0, le=600)]
    max_reserved_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    explicit_local_consent_required: Literal[True] = True
    live_review_activation_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def independent_keys_and_window(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("review authority window must be positive")
        all_signers = self.authorities + self.observers
        if len({s.signer_id for s in all_signers}) != len(all_signers) or len(
            {s.key_sha256 for s in all_signers}
        ) != len(all_signers):
            raise ValueError(
                "review authorities and observers require distinct identities and keys"
            )
        for group in (self.authorities, self.observers):
            if tuple(s.signer_id for s in group) != tuple(
                sorted(s.signer_id for s in group)
            ):
                raise ValueError("review conformance signers must be sorted")
        return self

    @property
    def sha256(self) -> str:
        return digest(canonical_bytes(self))


class ReviewConformanceScope(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_conformance_phase_scope"] = "review_conformance_phase_scope"
    phase: Literal["critics", "judge"]
    controller_sha256: Digest
    critic_preview_sha256: Digest
    phase_preview_sha256: Digest
    start_sha256: Digest | None
    guidance_sha256: Digest
    ledger_id: Digest
    ledger_policy_sha256: Digest
    max_reserved_microusd: Amount
    additional_reservation_microusd: Amount
    sdk_version: Identifier
    image_id: ImageID
    expires_at: datetime
    provider: Literal["openai"] = "openai"
    endpoint_origin: Literal["https://api.openai.com"] = "https://api.openai.com"
    api_family: Literal["responses"] = "responses"
    automatic_retries: Literal[0] = 0
    provider_storage_requested: Literal[False] = False

    @field_validator("expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def coherent_phase(self) -> Self:
        if self.phase == "critics":
            if (
                self.start_sha256 is not None
                or self.phase_preview_sha256 != self.critic_preview_sha256
                or self.additional_reservation_microusd != self.max_reserved_microusd
            ):
                raise ValueError(
                    "critic scope has inconsistent reservation or preview bindings"
                )
        elif self.start_sha256 is None or self.additional_reservation_microusd != 0:
            raise ValueError(
                "judge scope requires a start and transfers only existing spending"
            )
        return self


def review_conformance_scope(
    critics: ControllerCriticPreview,
    *,
    sdk_version: str,
    image_id: str,
    judge: ControllerJudgePreview | None = None,
    start: ControllerStart | None = None,
) -> ReviewConformanceScope:
    """Derive signature scope from trusted host previews without granting authority."""
    critics = ControllerCriticPreview.model_validate_json(canonical_bytes(critics))
    envelope = critics.envelope
    guidance = envelope.critics[0].guidance_sha256
    if guidance is None or any(
        request.provider != "openai" for request in critics.requests
    ):
        raise ValueError("review conformance requires guided OpenAI requests")
    amount = envelope.total_reserved_microusd
    deadline = envelope.expires_at
    phase_sha = digest(canonical_bytes(critics))
    start_sha = None
    if judge is None:
        if start is not None:
            raise ValueError("critic scope must precede the controller start")
    else:
        raw = canonical_bytes(judge)
        if len(raw) > MAX_WIRE_BYTES:
            raise ValueError("judge conformance preview exceeds its byte limit")
        judge = ControllerJudgePreview.model_validate_json(raw)
        if start is None:
            raise ValueError("judge conformance requires the trusted controller start")
        start = ControllerStart.model_validate_json(canonical_bytes(start))
        if (
            start.authorization != critics.authorization
            or start.started_at.tzinfo is None
            or start.expires_at.tzinfo is None
            or not start.started_at < start.expires_at <= envelope.expires_at
            or (start.expires_at - start.started_at).total_seconds()
            > critics.authorization.total_seconds
            or judge.controller_sha256 != critics.sha256
            or judge.evidence.envelope_sha256 != critics.authorization.envelope_sha256
            or judge.evidence.policy != critics.authorization.policy
            or judge.evidence.judge_request.brief.brief_id
            != envelope.judge.brief_sha256
            or judge.model_request.provider != "openai"
            or judge.model_request.model != envelope.judge.spend_policy.model
            or digest(canonical_bytes(judge.evidence))
            != judge.authorization.evidence_sha256
        ):
            raise ValueError("judge conformance scope differs from its controller")
        amount = envelope.judge.reserved_microusd
        deadline = start.expires_at
        phase_sha = judge.sha256
        start_sha = digest(canonical_bytes(start))
    return ReviewConformanceScope(
        phase="critics" if judge is None else "judge",
        controller_sha256=critics.sha256,
        critic_preview_sha256=digest(canonical_bytes(critics)),
        phase_preview_sha256=phase_sha,
        start_sha256=start_sha,
        guidance_sha256=guidance,
        ledger_id=envelope.critics[0].ledger_id,
        ledger_policy_sha256=envelope.ledger_policy_sha256,
        max_reserved_microusd=amount,
        additional_reservation_microusd=amount if judge is None else 0,
        sdk_version=sdk_version,
        image_id=image_id,
        expires_at=deadline.astimezone(UTC),
    )


class ReviewConformanceAuthorization(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["review_conformance_authorization"] = (
        "review_conformance_authorization"
    )
    authority_policy_sha256: Digest
    scope: ReviewConformanceScope
    issued_at: datetime
    valid_until: datetime
    exact_phase_probe_authorized: Literal[True] = True
    explicit_local_consent_also_required: Literal[True] = True
    automatic_retry_authorized: Literal[False] = False
    automatic_budget_release_authorized: Literal[False] = False
    conformance_proven: Literal[False] = False
    live_review_activation_authorized: Literal[False] = False

    @field_validator("issued_at", "valid_until")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)


class SignedReviewConformanceAuthorization(Contract):
    schema_version: Literal[1] = 1
    authorization: ReviewConformanceAuthorization
    signer_id: Identifier
    public_key_sha256: Digest
    signature_base64: Annotated[str, Field(min_length=88, max_length=88)]

    @model_validator(mode="after")
    def valid_encoding(self) -> Self:
        _decode(self.signature_base64, 64)
        return self


def make_review_conformance_authorization(
    scope: ReviewConformanceScope,
    policy: ReviewConformanceAuthorityPolicy,
    issued_at: datetime,
    valid_until: datetime,
) -> ReviewConformanceAuthorization:
    scope = ReviewConformanceScope.model_validate_json(canonical_bytes(scope))
    policy = ReviewConformanceAuthorityPolicy.model_validate_json(
        canonical_bytes(policy)
    )
    issued_at, valid_until = _utc(issued_at), _utc(valid_until)
    if (
        not policy.valid_from
        <= issued_at
        < valid_until
        <= min(policy.valid_until, scope.expires_at)
        or (valid_until - issued_at).total_seconds() > policy.max_authorization_seconds
        or scope.max_reserved_microusd > policy.max_reserved_microusd
    ):
        raise ValueError(
            "review conformance authorization exceeds its time or spending scope"
        )
    return ReviewConformanceAuthorization(
        authority_policy_sha256=policy.sha256,
        scope=scope,
        issued_at=issued_at,
        valid_until=valid_until,
    )


def sign_review_conformance_authorization(
    authorization: ReviewConformanceAuthorization,
    signer_id: str,
    key: Ed25519PrivateKey,
) -> SignedReviewConformanceAuthorization:
    authorization = ReviewConformanceAuthorization.model_validate_json(
        canonical_bytes(authorization)
    )
    return SignedReviewConformanceAuthorization(
        authorization=authorization,
        signer_id=signer_id,
        public_key_sha256=digest(key.public_key().public_bytes_raw()),
        signature_base64=base64.b64encode(
            key.sign(_DOMAIN + canonical_bytes(authorization))
        ).decode("ascii"),
    )


def verify_review_conformance_authorization(
    signed: SignedReviewConformanceAuthorization,
    policy: ReviewConformanceAuthorityPolicy,
    expected_scope: ReviewConformanceScope,
    now: datetime,
) -> ReviewConformanceAuthorization:
    """Verify a signature; the host must still enforce consumption and runtime gates."""
    now = _utc(now)
    signed = SignedReviewConformanceAuthorization.model_validate_json(
        canonical_bytes(signed)
    )
    policy = ReviewConformanceAuthorityPolicy.model_validate_json(
        canonical_bytes(policy)
    )
    expected = make_review_conformance_authorization(
        expected_scope,
        policy,
        signed.authorization.issued_at,
        signed.authorization.valid_until,
    )
    if (
        signed.authorization != expected
        or not signed.authorization.issued_at <= now < signed.authorization.valid_until
    ):
        raise ValueError("review conformance scope changed or authorization expired")
    enrolled = [
        s
        for s in policy.authorities
        if s.signer_id == signed.signer_id and s.key_sha256 == signed.public_key_sha256
    ]
    if len(enrolled) != 1:
        raise ValueError("review conformance authorizer is not enrolled")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(enrolled[0].public_key_base64, 32)
        ).verify(
            _decode(signed.signature_base64, 64),
            _DOMAIN + canonical_bytes(signed.authorization),
        )
    except (InvalidSignature, ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid review conformance authorization signature") from None
    return signed.authorization
