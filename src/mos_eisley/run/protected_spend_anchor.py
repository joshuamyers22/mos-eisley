"""Prospective remote admission boundary, independent of restorable task state.

The service must enroll owners and atomically enforce scope/epoch, cumulative
holds, revocation and one-use stages. This module authenticates its responses;
it does not turn a local database or an arbitrary HTTP endpoint into that service.
"""

from __future__ import annotations

import base64
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, JsonValue, field_validator, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.providers.openai_spend import CountedTransport
from mos_eisley.reviewer_provenance import (
    G4ArtifactSignature,
    G4ProvenanceTrustPolicy,
    verify_provenance_signature,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerPolicy
from mos_eisley.run.store import private_write

BINDING_DOMAIN = b"mos-eisley/g4-protected-anchor-binding/v1\x00"
RECEIPT_DOMAIN = b"mos-eisley/g4-protected-anchor-receipt/v1\x00"
Stage = Literal["claim", "count", "send"]


class ProtectedAnchorBinding(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["g4_protected_anchor_binding"] = "g4_protected_anchor_binding"
    owner_id: Identifier
    service_id: Digest
    scope_id: Digest
    epoch: Annotated[int, Field(ge=1)]
    scope_ceiling_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    grant_sha256: Digest
    ledger_policy_sha256: Digest
    anchor_public_key_base64: str
    issued_at: datetime
    expires_at: datetime
    metadata_transfer_authorized: Literal[True] = True
    provider_dispatch_authorized: Literal[False] = False

    @field_validator("issued_at", "expires_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("anchor timestamps require UTC")
        return value

    @model_validator(mode="after")
    def coherent(self) -> ProtectedAnchorBinding:
        key = base64.b64decode(self.anchor_public_key_base64, validate=True)
        if (
            len(key) != 32
            or base64.b64encode(key).decode() != self.anchor_public_key_base64
        ):
            raise ValueError("anchor key must be canonical Ed25519 public bytes")
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("anchor binding requires a bounded positive window")
        return self


class SignedProtectedAnchorBinding(Contract):
    binding: ProtectedAnchorBinding
    signature: G4ArtifactSignature


class AnchorRequest(Contract):
    binding_sha256: Digest
    stage: Stage
    nonce: Digest
    entry: LedgerEntry


class AnchorReceipt(Contract):
    request_sha256: Digest
    service_id: Digest
    scope_id: Digest
    epoch: Annotated[int, Field(ge=1)]
    sequence: Annotated[int, Field(ge=1)]
    charged_or_held_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000)]
    issued_at: datetime

    @field_validator("issued_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("anchor receipt timestamp requires UTC")
        return value


class SignedAnchorReceipt(Contract):
    receipt: AnchorReceipt
    signature_base64: str


class AnchorAdmissionRecord(Contract):
    request: AnchorRequest
    response: SignedAnchorReceipt


class ProtectedAnchorService(Protocol):
    """An enrolled remote service, never a task-local fallback.

    Each stage is an atomic one-use admission, ordered claim/count/send. Check
    owner, fixed scope cap, current epoch and revocation at each admission. A
    timeout is uncertain and must not be retried. Retain the full hold after a
    claim; releasing it requires a separate reconciled operation. The service's
    durable state must be outside the task operator's restore/delete authority.
    Revocation is ordered against atomic admission; it cannot undo an already
    admitted in-flight effect. No prompts, provider credentials or outputs enter
    this protocol.
    """

    def admit(
        self,
        binding: SignedProtectedAnchorBinding,
        request: AnchorRequest,
        /,
        *,
        timeout_seconds: float,
    ) -> SignedAnchorReceipt: ...


def sign_anchor_binding(
    binding: ProtectedAnchorBinding, key: Ed25519PrivateKey
) -> SignedProtectedAnchorBinding:
    return SignedProtectedAnchorBinding(
        binding=binding,
        signature=G4ArtifactSignature(
            signer_id=binding.owner_id,
            public_key_sha256=digest(key.public_key().public_bytes_raw()),
            signature_base64=base64.b64encode(
                key.sign(BINDING_DOMAIN + canonical_bytes(binding))
            ).decode(),
        ),
    )


class ProtectedAnchorGuard:
    def __init__(
        self, binding: SignedProtectedAnchorBinding, service: ProtectedAnchorService
    ) -> None:
        self.binding = binding
        self.service = service
        self._sequence = 0
        self._entry: LedgerEntry | None = None
        self._stages: set[Stage] = set()
        self._claim: AnchorAdmissionRecord | None = None
        self._failed = False
        self._deadline: datetime | None = None

    def claim(
        self,
        grant_sha256: str,
        policy: G4ProvenanceTrustPolicy,
        ledger_policy: LedgerPolicy,
        entry: LedgerEntry,
        deadline: datetime | None = None,
    ) -> None:
        binding = self.binding.binding
        verify_provenance_signature(
            binding, self.binding.signature, policy, "creator", BINDING_DOMAIN
        )
        if (
            binding.owner_id != self.binding.signature.signer_id
            or binding.grant_sha256 != grant_sha256
            or binding.ledger_policy_sha256 != digest(canonical_bytes(ledger_policy))
            or entry.entry_id != grant_sha256
            or entry.reserved_microusd > binding.scope_ceiling_microusd
        ):
            raise ValueError("protected anchor binding differs from exact authority")
        self._entry = entry
        self._deadline = min(
            binding.expires_at,
            policy.valid_until,
            deadline if deadline is not None else policy.valid_until,
        )
        self._claim = self.admit_stage("claim")

    def admit_stage(self, stage: Stage) -> AnchorAdmissionRecord:
        binding = self.binding.binding
        current = datetime.now(UTC)
        if self._deadline is None or not binding.issued_at <= current < self._deadline:
            raise ValueError("protected anchor binding expired")
        expected = (
            ("claim", "count", "send")[len(self._stages)]
            if len(self._stages) < 3
            else None
        )
        if self._failed or stage != expected or self._entry is None:
            raise ValueError("protected anchor stage is already spent or out of order")
        # Mark spent before invoking external code, including timeouts.
        self._stages.add(stage)
        self._failed = True
        request = AnchorRequest(
            binding_sha256=digest(canonical_bytes(self.binding)),
            stage=stage,
            nonce=secrets.token_hex(32),
            entry=self._entry,
        )
        response = self.service.admit(
            self.binding,
            request,
            timeout_seconds=min(10.0, (self._deadline - current).total_seconds()),
        )
        receipt = response.receipt
        key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(binding.anchor_public_key_base64, validate=True)
        )
        try:
            key.verify(
                base64.b64decode(response.signature_base64, validate=True),
                RECEIPT_DOMAIN + canonical_bytes(receipt),
            )
        except (InvalidSignature, ValueError):
            raise ValueError("protected anchor receipt is not authenticated") from None
        after = datetime.now(UTC)
        if (
            receipt.request_sha256 != digest(canonical_bytes(request))
            or receipt.service_id != binding.service_id
            or receipt.scope_id != binding.scope_id
            or receipt.epoch != binding.epoch
            or receipt.sequence <= self._sequence
            or not current - timedelta(seconds=30) <= receipt.issued_at <= after
            or after >= self._deadline
            or not self._entry.reserved_microusd
            <= receipt.charged_or_held_microusd
            <= binding.scope_ceiling_microusd
        ):
            raise ValueError("protected anchor receipt is stale or substituted")
        self._sequence = receipt.sequence
        self._failed = False
        return AnchorAdmissionRecord(request=request, response=response)

    def wrap_transport(
        self, transport: CountedTransport, directory: Path
    ) -> CountedTransport:
        if self._claim is None:
            raise ValueError("protected anchor has not admitted this grant")
        private_write(
            directory / "protected-anchor-binding.json", canonical_bytes(self.binding)
        )
        private_write(
            directory / "protected-anchor-claim.json", canonical_bytes(self._claim)
        )
        return _AnchoredTransport(self, transport, directory)


class _AnchoredTransport:
    def __init__(
        self, guard: ProtectedAnchorGuard, transport: CountedTransport, directory: Path
    ):
        self.guard, self.transport, self.directory = guard, transport, directory

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        receipt = self.guard.admit_stage("count")
        private_write(
            self.directory / "protected-anchor-count.json", canonical_bytes(receipt)
        )
        return await self.transport.count_input_tokens(payload)

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        receipt = self.guard.admit_stage("send")
        private_write(
            self.directory / "protected-anchor-send.json", canonical_bytes(receipt)
        )
        return await self.transport.create_response(payload)


def verify_protected_anchor_audit(
    directory: Path,
    policy: G4ProvenanceTrustPolicy,
    grant_sha256: str,
    ledger_policy: LedgerPolicy,
    entry: LedgerEntry,
) -> str:
    """Offline authentication of retained stages, not a new remote admission."""
    raw = read_bounded(directory / "protected-anchor-binding.json", 8192)
    signed = SignedProtectedAnchorBinding.model_validate_json(raw)
    if canonical_bytes(signed) != raw:
        raise ValueError("anchor binding is not canonical")
    binding = signed.binding
    verify_provenance_signature(
        binding, signed.signature, policy, "creator", BINDING_DOMAIN
    )
    if (
        binding.owner_id != signed.signature.signer_id
        or binding.grant_sha256 != grant_sha256
        or entry.entry_id != grant_sha256
        or binding.ledger_policy_sha256 != digest(canonical_bytes(ledger_policy))
    ):
        raise ValueError("anchor audit names another owner, grant or ledger")
    key = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(binding.anchor_public_key_base64, validate=True)
    )
    prior_sequence = 0
    records: list[AnchorAdmissionRecord] = []
    for stage in ("claim", "count", "send"):
        payload = read_bounded(directory / f"protected-anchor-{stage}.json", 8192)
        record = AnchorAdmissionRecord.model_validate_json(payload)
        request, response = record.request, record.response
        receipt = response.receipt
        if (
            canonical_bytes(record) != payload
            or request.stage != stage
            or request.entry != entry
            or request.binding_sha256 != digest(raw)
            or receipt.request_sha256 != digest(canonical_bytes(request))
            or receipt.service_id != binding.service_id
            or receipt.scope_id != binding.scope_id
            or receipt.epoch != binding.epoch
            or receipt.sequence <= prior_sequence
            or not binding.issued_at <= receipt.issued_at < binding.expires_at
            or not entry.reserved_microusd
            <= receipt.charged_or_held_microusd
            <= binding.scope_ceiling_microusd
        ):
            raise ValueError("anchor audit stage is stale or substituted")
        try:
            key.verify(
                base64.b64decode(response.signature_base64, validate=True),
                RECEIPT_DOMAIN + canonical_bytes(receipt),
            )
        except (InvalidSignature, ValueError):
            raise ValueError("anchor audit signature is invalid") from None
        prior_sequence = receipt.sequence
        records.append(record)
    return digest(raw + b"".join(canonical_bytes(record) for record in records))
