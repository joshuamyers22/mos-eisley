"""Portable signed checkpoints for verified skill-runtime publication history."""

from __future__ import annotations

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
from mos_eisley.run.skill_runtime_response import (
    SkillRuntimeResponseHistory,
    SkillRuntimeResponseStore,
)

_DOMAIN = b"mos-eisley/skill-runtime-publication-witness/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]
UtcTimestamp = Annotated[datetime, Field()]


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use an explicit UTC offset")
    return value


class TrustedSkillRuntimePublicationWitness(Contract):
    witness_id: Identifier
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: EncodedKey

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        _decode(self.public_key_base64, 32, "public key")
        return self

    @property
    def public_key_sha256(self) -> str:
        return digest(_decode(self.public_key_base64, 32, "public key"))


class SkillRuntimePublicationWitnessPolicy(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_publication_witness_policy"] = (
        "skill_runtime_publication_witness_policy"
    )
    policy_id: Identifier
    response_store_policy_sha256: Digest
    valid_from: UtcTimestamp
    valid_until: UtcTimestamp
    max_checkpoint_age_seconds: Annotated[int, Field(gt=0, le=2_592_000)]
    minimum_publications: Annotated[int, Field(ge=1, le=100_000)] = 1
    witnesses: Annotated[
        tuple[TrustedSkillRuntimePublicationWitness, ...],
        Field(min_length=1, max_length=20),
    ]
    external_retention_required: Literal[True] = True
    raw_response_export_authorized: Literal[False] = False
    result_export_authorized: Literal[False] = False
    provider_retry_authorized: Literal[False] = False
    budget_release_authorized: Literal[False] = False

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def canonical_and_valid(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("publication witness policy window must be positive")
        identities = tuple(item.witness_id for item in self.witnesses)
        keys = tuple(item.public_key_sha256 for item in self.witnesses)
        if tuple(sorted(set(identities))) != identities or len(keys) != len(set(keys)):
            raise ValueError(
                "publication witnesses need sorted unique identities and keys"
            )
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimePublicationCheckpoint(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["skill_runtime_publication_checkpoint"] = (
        "skill_runtime_publication_checkpoint"
    )
    witness_policy_sha256: Digest
    response_store_policy_sha256: Digest
    history: SkillRuntimeResponseHistory
    witnessed_at: UtcTimestamp
    external_retention_required: Literal[True] = True
    external_retention_proven: Literal[False] = False
    raw_responses_included: Literal[False] = False
    published_results_included: Literal[False] = False
    latest_external_checkpoint_proven: Literal[False] = False
    provider_retry_authorized: Literal[False] = False
    budget_release_authorized: Literal[False] = False

    @field_validator("witnessed_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_history(self) -> Self:
        if (
            self.response_store_policy_sha256
            != self.history.response_store_policy_sha256
        ):
            raise ValueError("publication checkpoint store identity mismatch")
        return self

    @property
    def checkpoint_sha256(self) -> str:
        return digest(canonical_bytes(self))


class SkillRuntimePublicationCheckpointSignature(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    signer_id: Identifier
    public_key_sha256: Digest
    checkpoint_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedSkillRuntimePublicationCheckpoint(Contract):
    schema_version: Literal[1] = 1
    checkpoint: SkillRuntimePublicationCheckpoint
    signature: SkillRuntimePublicationCheckpointSignature

    @model_validator(mode="after")
    def bound_content(self) -> Self:
        if self.signature.checkpoint_sha256 != self.checkpoint.checkpoint_sha256:
            raise ValueError("signature does not identify this publication checkpoint")
        return self

    @property
    def signed_checkpoint_sha256(self) -> str:
        return digest(canonical_bytes(self))


class VerifiedSkillRuntimePublicationCheckpoint(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["verified_skill_runtime_publication_checkpoint"] = (
        "verified_skill_runtime_publication_checkpoint"
    )
    witness_policy_sha256: Digest
    response_store_policy_sha256: Digest
    signer_id: Identifier
    signed_checkpoint: SignedSkillRuntimePublicationCheckpoint
    current_history: SkillRuntimeResponseHistory
    verified_at: UtcTimestamp
    checkpoint_is_verified_prefix: Literal[True] = True
    rollback_or_divergence_observed: Literal[False] = False
    external_retention_proven: Literal[False] = False
    latest_external_checkpoint_proven: Literal[False] = False
    raw_responses_included: Literal[False] = False
    published_results_included: Literal[False] = False
    provider_retry_authorized: Literal[False] = False
    budget_release_authorized: Literal[False] = False

    @field_validator("verified_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def bound_checkpoint(self) -> Self:
        checkpoint = self.signed_checkpoint.checkpoint
        if (
            self.witness_policy_sha256 != checkpoint.witness_policy_sha256
            or self.response_store_policy_sha256
            != checkpoint.response_store_policy_sha256
            or self.signer_id != self.signed_checkpoint.signature.signer_id
            or self.current_history.response_store_policy_sha256
            != checkpoint.response_store_policy_sha256
            or self.current_history.publications < checkpoint.history.publications
            or self.verified_at < checkpoint.witnessed_at
        ):
            raise ValueError("verified publication checkpoint is inconsistent")
        return self

    @property
    def verification_sha256(self) -> str:
        return digest(canonical_bytes(self))


def trusted_skill_runtime_publication_witness(
    witness_id: str, public_key: bytes
) -> TrustedSkillRuntimePublicationWitness:
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain 32 bytes")
    return TrustedSkillRuntimePublicationWitness(
        witness_id=witness_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def make_skill_runtime_publication_checkpoint(
    response_store: SkillRuntimeResponseStore,
    policy: SkillRuntimePublicationWitnessPolicy,
    witnessed_at: datetime,
) -> SkillRuntimePublicationCheckpoint:
    """Derive hash-only checkpoint metadata for independent signing and retention."""

    current = _require_utc(witnessed_at)
    history = response_store.history()
    if (
        policy.response_store_policy_sha256 != response_store.policy.policy_sha256
        or history.publications < policy.minimum_publications
        or not policy.valid_from <= current <= policy.valid_until
    ):
        raise ValueError("publication checkpoint does not match witness policy")
    return SkillRuntimePublicationCheckpoint(
        witness_policy_sha256=policy.policy_sha256,
        response_store_policy_sha256=response_store.policy.policy_sha256,
        history=history,
        witnessed_at=current,
    )


def sign_skill_runtime_publication_checkpoint(
    checkpoint: SkillRuntimePublicationCheckpoint,
    signer_id: str,
    private_key: bytes,
) -> SignedSkillRuntimePublicationCheckpoint:
    """Sign canonical checkpoint bytes; callers retain private-key custody."""

    checkpoint = SkillRuntimePublicationCheckpoint.model_validate_json(
        canonical_bytes(checkpoint)
    )
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = key.sign(_DOMAIN + canonical_bytes(checkpoint))
        public_key = key.public_key().public_bytes_raw()
    except (TypeError, ValueError, UnsupportedAlgorithm):
        raise ValueError("invalid Ed25519 private key") from None
    return SignedSkillRuntimePublicationCheckpoint(
        checkpoint=checkpoint,
        signature=SkillRuntimePublicationCheckpointSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            checkpoint_sha256=checkpoint.checkpoint_sha256,
            signature_base64=base64.b64encode(signature).decode("ascii"),
        ),
    )


def verify_skill_runtime_publication_checkpoint(
    signed: SignedSkillRuntimePublicationCheckpoint,
    policy: SkillRuntimePublicationWitnessPolicy,
    response_store: SkillRuntimeResponseStore,
    now: datetime,
) -> VerifiedSkillRuntimePublicationCheckpoint:
    """Verify signer, freshness, and exact store prefix without exporting content."""

    current = _require_utc(now)
    signed = SignedSkillRuntimePublicationCheckpoint.model_validate_json(
        canonical_bytes(signed)
    )
    policy = SkillRuntimePublicationWitnessPolicy.model_validate_json(
        canonical_bytes(policy)
    )
    checkpoint = signed.checkpoint
    if (
        checkpoint.witness_policy_sha256 != policy.policy_sha256
        or checkpoint.response_store_policy_sha256
        != policy.response_store_policy_sha256
        or policy.response_store_policy_sha256 != response_store.policy.policy_sha256
        or checkpoint.history.publications < policy.minimum_publications
        or not policy.valid_from
        <= checkpoint.witnessed_at
        <= current
        <= policy.valid_until
        or (current - checkpoint.witnessed_at).total_seconds()
        > policy.max_checkpoint_age_seconds
    ):
        raise ValueError("publication checkpoint does not match witness policy")
    matches = [
        item
        for item in policy.witnesses
        if item.witness_id == signed.signature.signer_id
    ]
    if len(matches) != 1:
        raise ValueError("publication checkpoint signer is not trusted")
    trusted = matches[0]
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("publication checkpoint signature key differs from policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _DOMAIN + canonical_bytes(checkpoint),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError(
            "publication checkpoint signature verification failed"
        ) from None
    current_history = response_store.verify_history_prefix(checkpoint.history)
    return VerifiedSkillRuntimePublicationCheckpoint(
        witness_policy_sha256=policy.policy_sha256,
        response_store_policy_sha256=policy.response_store_policy_sha256,
        signer_id=trusted.witness_id,
        signed_checkpoint=signed,
        current_history=current_history,
        verified_at=current,
    )
