"""Conservative one-use ledger settlement for Anthropic review Messages."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import Field, JsonValue

from mos_eisley.core.models import Contract, Digest, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.anthropic_review import (
    MAX_ANTHROPIC_RESPONSE_BYTES,
    normalized_payload,
    payload_bytes,
)
from mos_eisley.providers.openai_spend import (
    SpendPolicy,
    SpendReceipt,
    SpendReservation,
    spending_request_sha256,
)
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerSettlement, SpendLedger
from mos_eisley.run.store import private_write


class AnthropicCountedTransport(Protocol):
    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int: ...

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]: ...


class AnthropicReviewCountObservation(Contract):
    kind: Literal["anthropic_review_count_observation"] = (
        "anthropic_review_count_observation"
    )
    request_sha256: Digest
    reservation_sha256: Digest
    ledger_id: Digest
    ledger_entry_id: Digest
    counted_input_tokens: Annotated[int, Field(ge=0)]
    held_input_tokens: Annotated[int, Field(ge=0)]
    generation_started_at_observation: Literal[False] = False


def prepare_anthropic_reservation(
    payload: dict[str, JsonValue], policy: SpendPolicy
) -> SpendReservation:
    """Reserve the complete input/output envelope at the highest cache-write rate."""
    if policy.schema_version != 2:
        raise ValueError("Anthropic review needs a cache-write-safe spending policy")
    request = normalized_payload(payload, policy)
    if request["max_tokens"] != policy.max_output_tokens:
        raise ValueError("Anthropic review output cap differs from spending policy")
    amount = policy.reservation_cost(policy.max_input_tokens, policy.max_output_tokens)
    if amount > policy.max_cost_microusd:
        raise ValueError("Anthropic review reservation exceeds the per-call ceiling")
    return SpendReservation(
        policy_sha256=policy.policy_sha256,
        request_sha256=spending_request_sha256(request),
        input_tokens=policy.max_input_tokens,
        max_output_tokens=policy.max_output_tokens,
        reserved_microusd=amount,
    )


def _nonnegative(value: JsonValue | None) -> int | None:
    return value if type(value) is int and value >= 0 else None


class PreReservedAnthropicReviewTransport:
    """One approved request; any uncertain exchange keeps the full ledger hold."""

    def __init__(
        self,
        transport: AnthropicCountedTransport,
        policy: SpendPolicy,
        directory: Path,
        ledger: SpendLedger,
        reservation: SpendReservation,
        ledger_entry: LedgerEntry,
        grant_expires_at: datetime | None = None,
    ) -> None:
        self.transport = transport
        self.policy = policy
        self.directory = directory
        self.ledger = ledger
        self.reservation = reservation
        self.ledger_entry = ledger_entry
        self.ledger_entry_id = ledger_entry.entry_id
        self.grant_expires_at = grant_expires_at
        self._used = False

    def _grant_current(self) -> None:
        if (
            self.grant_expires_at is not None
            and datetime.now(UTC) >= self.grant_expires_at
        ):
            raise ValueError("Anthropic live grant expired before provider transfer")

    def _held(self) -> None:
        if self.ledger.snapshot().blocked:
            raise ValueError("spending ledger is blocked by a pricing violation")
        status = self.ledger.entry_status(self.ledger_entry_id)
        if (
            status is None
            or status.reservation_sha256 != self.ledger_entry.reservation_sha256
            or status.reserved_microusd != self.ledger_entry.reserved_microusd
            or status.charged_microusd != self.ledger_entry.reserved_microusd
            or status.status != "held"
        ):
            raise ValueError("Anthropic spending reservation is not the exact hold")

    def _receipt(
        self,
        reservation_sha256: str,
        status: Literal["settled", "uncertain", "violation"],
        charged: int,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_write_tokens: int | None = None,
    ) -> None:
        self.ledger.settle(
            LedgerSettlement(
                entry_id=self.ledger_entry_id,
                reservation_sha256=reservation_sha256,
                status=status,
                charged_microusd=charged,
            )
        )
        private_write(
            self.directory / "spend-receipt.json",
            canonical_bytes(
                SpendReceipt(
                    reservation_sha256=reservation_sha256,
                    status=status,
                    retained_microusd=charged,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_write_tokens=cache_write_tokens,
                    ledger_id=self.ledger.policy.ledger_id,
                    ledger_entry_id=self.ledger_entry_id,
                )
            ),
        )

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if self._used:
            raise ProviderError("Anthropic spending controller permits one call only")
        self._used = True  # Consume before token counting or any await.
        self.policy.check_current()
        self._grant_current()
        request = normalized_payload(payload, self.policy)
        expected = prepare_anthropic_reservation(request, self.policy)
        reservation_sha256 = digest(canonical_bytes(self.reservation))
        if (
            self.reservation != expected
            or reservation_sha256 != self.ledger_entry.reservation_sha256
            or self.reservation.reserved_microusd != self.ledger_entry.reserved_microusd
        ):
            raise ValueError("Anthropic spending envelope differs from the held grant")
        self._held()
        private_write(
            self.directory / "spend-reservation.json", canonical_bytes(self.reservation)
        )
        try:
            counted = await self.transport.count_input_tokens(request)
        except BaseException:
            self._receipt(
                reservation_sha256, "uncertain", self.reservation.reserved_microusd
            )
            raise
        private_write(
            self.directory / "token-count-observation.json",
            canonical_bytes(
                AnthropicReviewCountObservation(
                    request_sha256=spending_request_sha256(request),
                    reservation_sha256=reservation_sha256,
                    ledger_id=self.ledger.policy.ledger_id,
                    ledger_entry_id=self.ledger_entry_id,
                    counted_input_tokens=counted,
                    held_input_tokens=self.reservation.input_tokens,
                )
            ),
        )
        if counted > self.reservation.input_tokens:
            self._receipt(
                reservation_sha256,
                "violation",
                self.reservation.reserved_microusd,
                input_tokens=counted,
            )
            raise ProviderError("Anthropic input count exceeded the held envelope")
        self.policy.check_current()
        try:
            self._grant_current()
        except ValueError:
            self._receipt(
                reservation_sha256, "uncertain", self.reservation.reserved_microusd
            )
            raise
        self._held()
        try:
            response = await self.transport.create_response(request)
            raw = payload_bytes(response)
            if len(raw) > MAX_ANTHROPIC_RESPONSE_BYTES:
                raise ProviderError("Anthropic canonical response exceeded byte limit")
            private_write(self.directory / "provider-response.json", raw)
        except BaseException:
            self._receipt(
                reservation_sha256, "uncertain", self.reservation.reserved_microusd
            )
            raise
        usage = response.get("usage")
        if not isinstance(usage, dict):
            self._receipt(
                reservation_sha256, "uncertain", self.reservation.reserved_microusd
            )
            raise ProviderError("Anthropic response omitted usage")
        input_tokens = _nonnegative(usage.get("input_tokens"))
        output_tokens = _nonnegative(usage.get("output_tokens"))
        cache_write = _nonnegative(usage.get("cache_creation_input_tokens"))
        cache_read = _nonnegative(usage.get("cache_read_input_tokens"))
        if None in (input_tokens, output_tokens, cache_write, cache_read):
            self._receipt(
                reservation_sha256, "uncertain", self.reservation.reserved_microusd
            )
            raise ProviderError("Anthropic response returned invalid usage")
        assert input_tokens is not None
        assert output_tokens is not None
        assert cache_write is not None
        assert cache_read is not None
        total_input = input_tokens + cache_write + cache_read
        tool_usage = usage.get("server_tool_use")
        if (
            total_input > self.reservation.input_tokens
            or output_tokens > self.reservation.max_output_tokens
            or response.get("model") != self.policy.model
            or usage.get("service_tier") != "standard"
            or usage.get("inference_geo") != "global"
            or (
                tool_usage is not None
                and (
                    not isinstance(tool_usage, dict)
                    or any(value != 0 for value in tool_usage.values())
                )
            )
        ):
            self._receipt(
                reservation_sha256, "violation", self.reservation.reserved_microusd
            )
            raise ProviderError("Anthropic response violated reserved pricing")
        charged = self.policy.cost(total_input, output_tokens, cache_write)
        if charged > self.reservation.reserved_microusd:
            self._receipt(
                reservation_sha256, "violation", self.reservation.reserved_microusd
            )
            raise ProviderError("Anthropic response exceeded held spending")
        self._receipt(
            reservation_sha256,
            "settled",
            charged,
            total_input,
            output_tokens,
            cache_write,
        )
        return response
