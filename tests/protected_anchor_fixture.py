"""Synthetic enrolled service kept independently of the disposable task ledger."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from threading import Lock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.run.protected_spend_anchor import (
    BINDING_DOMAIN,
    RECEIPT_DOMAIN,
    AnchorReceipt,
    AnchorRequest,
    ProtectedAnchorBinding,
    ProtectedAnchorGuard,
    SignedAnchorReceipt,
    SignedProtectedAnchorBinding,
    Stage,
    sign_anchor_binding,
)
from mos_eisley.run.spend_ledger import SpendLedger


class FixtureAnchorService:
    def __init__(self, owner: Ed25519PrivateKey, cap: int = 5000):
        self.owner = owner.public_key()
        self.key = Ed25519PrivateKey.generate()
        self.service_id = digest(b"synthetic-protected-service")
        self.scope_id = digest(b"synthetic-owner-scope")
        self.epoch = 1
        self.cap = cap
        self.revoked = False
        self.sequence = 0
        self.held = 0
        self.stages: dict[str, list[Stage]] = {}
        self.entries: dict[str, str] = {}
        self.lock = Lock()

    def admit(
        self,
        signed: SignedProtectedAnchorBinding,
        request: AnchorRequest,
        *,
        timeout_seconds: float = 10.0,
    ) -> SignedAnchorReceipt:
        if not 0 < timeout_seconds <= 10:
            raise ValueError("anchor call must have a bounded positive timeout")
        binding = signed.binding
        self.owner.verify(
            base64.b64decode(signed.signature.signature_base64, validate=True),
            BINDING_DOMAIN + canonical_bytes(binding),
        )
        with self.lock:
            if (
                binding.owner_id != "creator"
                or self.revoked
                or binding.service_id != self.service_id
                or binding.scope_id != self.scope_id
                or binding.epoch != self.epoch
                or binding.scope_ceiling_microusd != self.cap
                or request.binding_sha256 != digest(canonical_bytes(signed))
                or request.entry.entry_id != binding.grant_sha256
            ):
                raise ValueError("remote owner, epoch, cap or revocation mismatch")
            entry_id = request.entry.entry_id
            entry_hash = digest(canonical_bytes(request.entry))
            prior = self.stages.get(entry_id, [])
            expected = (
                ("claim", "count", "send")[len(prior)] if len(prior) < 3 else None
            )
            if request.stage != expected or (
                prior and self.entries[entry_id] != entry_hash
            ):
                raise ValueError("remote grant stage is already spent or substituted")
            if request.stage == "claim":
                if self.held + request.entry.reserved_microusd > self.cap:
                    raise ValueError("remote aggregate allowance exhausted")
                self.held += request.entry.reserved_microusd
                self.entries[entry_id] = entry_hash
            self.stages[entry_id] = [*prior, request.stage]
            self.sequence += 1
            receipt = AnchorReceipt(
                request_sha256=digest(canonical_bytes(request)),
                service_id=self.service_id,
                scope_id=self.scope_id,
                epoch=self.epoch,
                sequence=self.sequence,
                charged_or_held_microusd=self.held,
                issued_at=datetime.now(UTC),
            )
            return SignedAnchorReceipt(
                receipt=receipt,
                signature_base64=base64.b64encode(
                    self.key.sign(RECEIPT_DOMAIN + canonical_bytes(receipt))
                ).decode(),
            )


def fixture_anchor(
    owner: Ed25519PrivateKey,
    ledger: SpendLedger,
    grant_sha256: str,
    service: FixtureAnchorService | None = None,
) -> ProtectedAnchorGuard:
    remote = service if service is not None else FixtureAnchorService(owner)
    now = datetime.now(UTC)
    binding = ProtectedAnchorBinding(
        owner_id="creator",
        service_id=remote.service_id,
        scope_id=remote.scope_id,
        epoch=remote.epoch,
        scope_ceiling_microusd=remote.cap,
        grant_sha256=grant_sha256,
        ledger_policy_sha256=digest(canonical_bytes(ledger.policy)),
        anchor_public_key_base64=base64.b64encode(
            remote.key.public_key().public_bytes_raw()
        ).decode(),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=15),
    )
    return ProtectedAnchorGuard(sign_anchor_binding(binding, owner), remote)
