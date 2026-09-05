"""Ed25519 authentication for route-blind human adjudication artifacts."""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.evaluation.adjudication import (
    AdjudicationSet,
    GradingBatch,
    validate_adjudication,
)

_DOMAIN = b"mos-eisley/adjudication-signature/v1\x00"
EncodedKey = Annotated[str, Field(min_length=44, max_length=44)]
EncodedSignature = Annotated[str, Field(min_length=88, max_length=88)]


def _decode(value: str, length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} must be canonical base64") from None
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} has an invalid encoding or length")
    return decoded


class TrustedAdjudicator(Contract):
    adjudicator_id: Identifier
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: EncodedKey

    @model_validator(mode="after")
    def valid_key(self) -> Self:
        _decode(self.public_key_base64, 32, "public key")
        return self

    @property
    def public_key_sha256(self) -> str:
        return digest(_decode(self.public_key_base64, 32, "public key"))


class GradingTrustPolicy(Contract):
    schema_version: Literal[1] = 1
    policy_id: Identifier
    rubric_sha256: Digest
    adjudicators: Annotated[
        tuple[TrustedAdjudicator, ...], Field(min_length=2, max_length=20)
    ]

    @model_validator(mode="after")
    def unique_identities_and_keys(self) -> Self:
        identities = tuple(item.adjudicator_id for item in self.adjudicators)
        keys = tuple(item.public_key_sha256 for item in self.adjudicators)
        if len(identities) != len(set(identities)) or len(keys) != len(set(keys)):
            raise ValueError("trust policy identities and public keys must be unique")
        return self

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AdjudicationSignature(Contract):
    schema_version: Literal[1] = 1
    algorithm: Literal["ed25519"] = "ed25519"
    signer_id: Identifier
    public_key_sha256: Digest
    adjudication_sha256: Digest
    signature_base64: EncodedSignature

    @model_validator(mode="after")
    def valid_signature_encoding(self) -> Self:
        _decode(self.signature_base64, 64, "signature")
        return self


class SignedAdjudication(Contract):
    schema_version: Literal[1] = 1
    adjudication: AdjudicationSet
    signature: AdjudicationSignature

    @model_validator(mode="after")
    def bound_identity_and_content(self) -> Self:
        if (
            self.signature.signer_id != self.adjudication.adjudicator.adjudicator_id
            or self.signature.adjudication_sha256
            != self.adjudication.adjudication_sha256
        ):
            raise ValueError("signature does not identify this adjudication")
        return self

    @property
    def signed_adjudication_sha256(self) -> str:
        return digest(canonical_bytes(self))


class AuthenticatedAdjudication(Contract):
    schema_version: Literal[1] = 1
    grading_batch_sha256: Digest
    trust_policy_sha256: Digest
    signed_adjudication: SignedAdjudication

    @model_validator(mode="after")
    def bound_batch(self) -> Self:
        if (
            self.grading_batch_sha256
            != self.signed_adjudication.adjudication.grading_batch_sha256
        ):
            raise ValueError("authentication receipt grading batch mismatch")
        return self

    @property
    def authenticated_adjudication_sha256(self) -> str:
        return digest(canonical_bytes(self))


def _message(adjudication: AdjudicationSet) -> bytes:
    return _DOMAIN + canonical_bytes(adjudication)


def sign_adjudication(
    adjudication: AdjudicationSet, signer_id: str, private_key: bytes
) -> SignedAdjudication:
    """Sign canonical adjudication bytes; callers retain private-key custody."""
    if signer_id != adjudication.adjudicator.adjudicator_id:
        raise ValueError("signer identity differs from adjudicator")
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
    except (UnsupportedAlgorithm, ValueError):
        raise ValueError("Ed25519 signing unavailable or private key invalid") from None
    public_key = key.public_key().public_bytes_raw()
    return SignedAdjudication(
        adjudication=adjudication,
        signature=AdjudicationSignature(
            signer_id=signer_id,
            public_key_sha256=digest(public_key),
            adjudication_sha256=adjudication.adjudication_sha256,
            signature_base64=base64.b64encode(key.sign(_message(adjudication))).decode(
                "ascii"
            ),
        ),
    )


def trusted_adjudicator(signer_id: str, public_key: bytes) -> TrustedAdjudicator:
    """Build a trust entry from an independently distributed raw public key."""
    if len(public_key) != 32:
        raise ValueError("Ed25519 public key must contain exactly 32 bytes")
    return TrustedAdjudicator(
        adjudicator_id=signer_id,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


def authenticate_adjudication(
    batch: GradingBatch,
    signed: SignedAdjudication,
    policy: GradingTrustPolicy,
) -> AuthenticatedAdjudication:
    """Verify content, human identity, rubric, trust policy, and signature."""
    adjudication = signed.adjudication
    validate_adjudication(batch, adjudication, allow_unresolved=True)
    if (
        signed.signature.signer_id != adjudication.adjudicator.adjudicator_id
        or signed.signature.adjudication_sha256 != adjudication.adjudication_sha256
    ):
        raise ValueError("signature does not identify this adjudication")
    if adjudication.adjudicator.method != "human":
        raise ValueError("only human adjudication can be authenticated")
    if adjudication.adjudicator.rubric_sha256 != policy.rubric_sha256:
        raise ValueError("adjudication rubric differs from trust policy")
    matches = [
        item
        for item in policy.adjudicators
        if item.adjudicator_id == signed.signature.signer_id
    ]
    if len(matches) != 1:
        raise ValueError("adjudicator is not trusted by this policy")
    trusted = matches[0]
    if signed.signature.public_key_sha256 != trusted.public_key_sha256:
        raise ValueError("signature public key differs from trust policy")
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode(trusted.public_key_base64, 32, "public key")
        ).verify(
            _decode(signed.signature.signature_base64, 64, "signature"),
            _message(adjudication),
        )
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        raise ValueError("adjudication signature verification failed") from None
    return AuthenticatedAdjudication(
        grading_batch_sha256=batch.grading_batch_sha256,
        trust_policy_sha256=policy.policy_sha256,
        signed_adjudication=signed,
    )


def verify_authenticated_adjudication(
    batch: GradingBatch,
    authenticated: AuthenticatedAdjudication,
    policy: GradingTrustPolicy,
) -> None:
    """Reverify a stored receipt against independently supplied batch and policy."""
    if (
        authenticated.grading_batch_sha256 != batch.grading_batch_sha256
        or authenticated.trust_policy_sha256 != policy.policy_sha256
        or authenticate_adjudication(batch, authenticated.signed_adjudication, policy)
        != authenticated
    ):
        raise ValueError("authenticated adjudication provenance mismatch")
