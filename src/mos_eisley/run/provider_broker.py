"""Host-owned, single-use request grants; private IPC lives in isolated_broker."""

from __future__ import annotations

import asyncio
import math
import secrets
import threading
import time
from typing import Literal

from pydantic import Field, JsonValue

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import BudgetedOpenAITransport
from mos_eisley.run.broker_audit import BrokerAudit
from mos_eisley.run.broker_wire import BrokerReply

MAX_REQUEST_BYTES = 1_048_576


class ApprovedRequest(Contract):
    payload: dict[str, JsonValue]


class BrokerClaim(Contract):
    schema_version: Literal[1] = 1
    capability: Digest = Field(repr=False)
    request_sha256: Digest
    authorization_sha256: Digest | None = None


class RequestBoundBroker:
    """One process-local grant composed with mandatory shared spending admission.

    Only trusted host code constructs this object. Never serialize its internals.
    The claim is a bearer secret, not a provider credential or reusable session.
    """

    def __init__(
        self,
        payload: dict[str, JsonValue],
        transport: BudgetedOpenAITransport,
        *,
        lifetime_seconds: float = 30,
        audit: BrokerAudit | None = None,
    ) -> None:
        if not math.isfinite(lifetime_seconds) or not 0 < lifetime_seconds <= 60:
            raise ValueError("broker lifetime must be between zero and 60 seconds")
        if transport.ledger is None:
            raise ValueError("broker requires shared spending admission")
        encoded = canonical_bytes(ApprovedRequest(payload=payload))
        if len(encoded) > MAX_REQUEST_BYTES:
            raise ValueError("broker request exceeds byte limit")
        # Keep bytes, not a frozen model containing a still-mutable nested dict.
        self._request = encoded
        self._transport = transport
        self._capability = secrets.token_hex(32)
        self._request_sha256 = digest(encoded)
        if audit is not None:
            binding = audit.authorization
            if (
                binding.provider_request_sha256 != self._request_sha256
                or binding.spend_policy_sha256 != transport.policy.policy_sha256
                or binding.ledger_id != transport.ledger.policy.ledger_id
                or binding.ledger_entry_id != transport.ledger_entry_id
            ):
                raise ValueError("broker audit authorization mismatch")
        self._audit = audit
        self._authorization_sha256 = (
            audit.authorization_sha256 if audit is not None else None
        )
        self._expires = time.monotonic() + lifetime_seconds
        self._lock = threading.Lock()
        self._used = False

    def claim(self) -> BrokerClaim:
        """Trusted host delivers this once over a private channel; never log it."""
        return BrokerClaim(
            capability=self._capability,
            request_sha256=self._request_sha256,
            authorization_sha256=self._authorization_sha256,
        )

    async def redeem(self, wire: bytes) -> dict[str, JsonValue]:
        # All malformed/authentication failures are deliberately indistinguishable.
        try:
            if len(wire) > 1024:
                raise ValueError("oversize claim")
            claim = BrokerClaim.model_validate_json(wire)
        except ValueError:
            raise ProviderError("broker grant rejected") from None
        with self._lock:
            remaining = self._expires - time.monotonic()
            if (
                self._used
                or remaining <= 0
                or not secrets.compare_digest(claim.capability, self._capability)
                or claim.request_sha256 != self._request_sha256
                or claim.authorization_sha256 != self._authorization_sha256
            ):
                raise ProviderError("broker grant rejected")
            # Consume before any await, token counting, reservation, or dispatch.
            self._used = True
        if self._audit is not None:
            self._audit.admit()
        started = time.monotonic()
        try:
            async with asyncio.timeout(remaining):
                response = await self._transport.create_response(
                    ApprovedRequest.model_validate_json(self._request).payload
                )
        except asyncio.CancelledError:
            if self._audit is not None:
                self._audit.finish("cancelled")
            raise
        except Exception:
            if self._audit is not None:
                self._audit.finish("failed")
            # Cancellation propagates; the grant stays consumed in every case.
            # Spending controller retains uncertain reservations after dispatch.
            raise ProviderError("broker response unavailable") from None
        if self._audit is not None:
            self._audit.finish(
                "response_received",
                digest(canonical_bytes(BrokerReply(response=response))),
                min(86_400_000, math.ceil((time.monotonic() - started) * 1000)),
            )
        return response
