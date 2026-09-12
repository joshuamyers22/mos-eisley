"""One-response spending reservation for text-only OpenAI preview calls."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerSettlement, SpendLedger
from mos_eisley.run.store import private_write

Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]


class SpendPolicy(Contract):
    schema_version: Literal[1, 2] = 1
    model: Identifier
    currency: Literal["USD"] = "USD"
    service_tier: Literal["default"] = "default"
    pricing_source: Annotated[str, Field(min_length=1, max_length=1000)]
    valid_from: datetime
    valid_until: datetime
    input_microusd_per_million: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    cache_write_microusd_per_million: (
        Annotated[int, Field(gt=0, le=1_000_000_000_000)] | None
    ) = Field(default=None, exclude_if=lambda value: value is None)
    output_microusd_per_million: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    max_cost_microusd: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
    max_input_tokens: Annotated[int, Field(gt=0, le=200_000)] = 64_000
    max_output_tokens: Annotated[int, Field(gt=0, le=4096)] = 4096

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.valid_from.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("pricing timestamps must include a timezone")
        if self.valid_until <= self.valid_from:
            raise ValueError("pricing validity window must be positive")
        if (
            self.schema_version == 1
            and self.cache_write_microusd_per_million is not None
        ):
            raise ValueError("schema-1 spending policy cannot price cache writes")
        if self.schema_version == 2 and (
            self.cache_write_microusd_per_million is None
            or self.cache_write_microusd_per_million < self.input_microusd_per_million
        ):
            raise ValueError(
                "schema-2 spending policy requires a conservative cache-write rate"
            )
        return self

    def check_current(self, now: datetime | None = None) -> None:
        current = now if now is not None else datetime.now(UTC)
        if current.tzinfo is None or current.utcoffset() != timedelta(0):
            raise ValueError("spending policy clock must use an explicit UTC offset")
        if not self.valid_from <= current < self.valid_until:
            raise ValueError("spending policy is outside its validity window")

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def cost(
        self, input_tokens: int, output_tokens: int, cache_write_tokens: int = 0
    ) -> int:
        # No cache-read discount is assumed; output_tokens includes reasoning.
        if (
            type(input_tokens) is not int
            or type(output_tokens) is not int
            or type(cache_write_tokens) is not int
            or input_tokens < 0
            or output_tokens < 0
            or not 0 <= cache_write_tokens <= input_tokens
        ):
            raise ValueError("spending cost requires coherent nonnegative token counts")
        cache_write_rate = (
            self.cache_write_microusd_per_million
            if self.cache_write_microusd_per_million is not None
            else self.input_microusd_per_million
        )
        return (
            input_tokens * self.input_microusd_per_million
            + cache_write_tokens * (cache_write_rate - self.input_microusd_per_million)
            + output_tokens * self.output_microusd_per_million
            + 999_999
        ) // 1_000_000

    def reservation_cost(self, input_tokens: int, output_tokens: int) -> int:
        """Reserve every input token at the highest applicable input rate."""

        cache_write_tokens = input_tokens if self.schema_version == 2 else 0
        return self.cost(input_tokens, output_tokens, cache_write_tokens)


class SpendReservation(Contract):
    policy_sha256: Digest
    request_sha256: Digest
    input_tokens: Annotated[int, Field(ge=0)]
    max_output_tokens: Annotated[int, Field(gt=0)]
    reserved_microusd: Money


class SpendReceipt(Contract):
    reservation_sha256: Digest
    status: Literal["settled", "uncertain", "violation"]
    retained_microusd: Money
    input_tokens: Annotated[int, Field(ge=0)] | None = None
    output_tokens: Annotated[int, Field(ge=0)] | None = None
    cache_write_tokens: Annotated[int, Field(ge=0)] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    ledger_id: Digest | None = None
    ledger_entry_id: Digest | None = None

    @model_validator(mode="after")
    def ledger_reference(self) -> Self:
        if (self.ledger_id is None) != (self.ledger_entry_id is None):
            raise ValueError("ledger receipt requires both identity fields")
        return self


class CountedTransport(Protocol):
    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int: ...
    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]: ...


class SpendControlledOpenAITransport(Protocol):
    """Structural contract consumed by the request-bound broker."""

    policy: SpendPolicy
    ledger: SpendLedger | None
    ledger_entry_id: str

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]: ...


def _normalized_text_request(
    payload: dict[str, JsonValue], policy: SpendPolicy
) -> tuple[dict[str, JsonValue], int]:
    request = copy.deepcopy(payload)
    if request.get("model") != policy.model:
        raise ProviderError("spending policy model mismatch")
    permitted = {
        "model",
        "instructions",
        "input",
        "tools",
        "reasoning",
        "max_output_tokens",
        "parallel_tool_calls",
        "include",
        "store",
        "text",
        "truncation",
        "service_tier",
        "stream",
        "background",
    }
    if (
        set(request) - permitted
        or request.get("tools")
        or request.get("service_tier") not in (None, "default")
        or (request.get("store") is not None and request.get("store") is not False)
        or request.get("truncation") not in (None, "disabled")
        or (request.get("stream") is not None and request.get("stream") is not False)
        or (
            request.get("background") is not None
            and request.get("background") is not False
        )
    ):
        raise ProviderError("spending controller requires a text-only request")
    inputs = request.get("input")
    if not isinstance(inputs, list) or not inputs:
        raise ProviderError("spending controller requires explicit text input")
    for item in inputs:
        if (
            not isinstance(item, dict)
            or set(item) != {"role", "content"}
            or item.get("role") not in ("user", "assistant", "system", "developer")
            or not isinstance(item.get("content"), str)
        ):
            raise ProviderError("spending controller rejects non-text input")
    output_cap = request.get("max_output_tokens")
    if type(output_cap) is not int or not 1 <= output_cap <= policy.max_output_tokens:
        raise ProviderError("output limit exceeds spending policy")
    request["store"] = False
    request["truncation"] = "disabled"
    request["service_tier"] = "default"
    return request, output_cap


def _count_payload(request: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        key: value
        for key, value in request.items()
        if key
        not in (
            "max_output_tokens",
            "stream",
            "background",
            "store",
            "include",
            "service_tier",
        )
    }


def _request_sha256(request: dict[str, JsonValue]) -> str:
    return digest(
        json.dumps(
            request, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    )


def prepare_full_reservation(
    payload: dict[str, JsonValue], policy: SpendPolicy
) -> SpendReservation:
    """Pure, current-policy envelope for a later pre-reserved text dispatch."""
    policy.check_current()
    request, output_cap = _normalized_text_request(payload, policy)
    if output_cap != policy.max_output_tokens:
        raise ValueError("full reservation requires the exact policy output cap")
    amount = policy.reservation_cost(policy.max_input_tokens, output_cap)
    if amount > policy.max_cost_microusd:
        raise ValueError("full reservation exceeds the per-call spending limit")
    return SpendReservation(
        policy_sha256=policy.policy_sha256,
        request_sha256=_request_sha256(request),
        input_tokens=policy.max_input_tokens,
        max_output_tokens=output_cap,
        reserved_microusd=amount,
    )


class BudgetedOpenAITransport:
    """Single use: uncertain responses retain the reservation and are never retried."""

    def __init__(
        self,
        transport: CountedTransport,
        policy: SpendPolicy,
        directory: Path,
        ledger: SpendLedger | None = None,
    ):
        self.transport = transport
        self.policy = policy
        self.directory = directory
        self.ledger = ledger
        self.ledger_entry_id = digest(str(directory.resolve()).encode())
        self._used = False

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if self._used:
            raise ProviderError("spending controller permits one response only")
        self._used = True  # Set before the first await, including concurrent callers.
        self.policy.check_current()
        request, output_cap = _normalized_text_request(payload, self.policy)
        tokens = await self.transport.count_input_tokens(
            copy.deepcopy(_count_payload(request))
        )
        if type(tokens) is not int or not 0 <= tokens <= self.policy.max_input_tokens:
            raise ProviderError("input count exceeds spending policy")
        self.policy.check_current()
        reserved = self.policy.reservation_cost(tokens, output_cap)
        if reserved > self.policy.max_cost_microusd:
            raise ProviderError("response reservation exceeds spending limit")
        reservation = SpendReservation(
            policy_sha256=self.policy.policy_sha256,
            request_sha256=_request_sha256(request),
            input_tokens=tokens,
            max_output_tokens=output_cap,
            reserved_microusd=reserved,
        )
        reservation_bytes = canonical_bytes(reservation)
        private_write(self.directory / "spend-reservation.json", reservation_bytes)
        reservation_hash = digest(reservation_bytes)
        if self.ledger is not None:
            self.ledger.reserve(
                LedgerEntry(
                    entry_id=self.ledger_entry_id,
                    reservation_sha256=reservation_hash,
                    reserved_microusd=reserved,
                )
            )
        try:
            response = await self.transport.create_response(request)
        except BaseException:
            self._receipt(reservation_hash, "uncertain", reserved)
            raise
        usage = response.get("usage")
        if not isinstance(usage, dict):
            self._receipt(reservation_hash, "uncertain", reserved)
            raise ProviderError("response omitted billable usage")
        actual_input, actual_output = (
            usage.get("input_tokens"),
            usage.get("output_tokens"),
        )
        if (
            type(actual_input) is not int
            or type(actual_output) is not int
            or actual_input < 0
            or actual_output < 0
        ):
            self._receipt(reservation_hash, "uncertain", reserved)
            raise ProviderError("response returned invalid billable usage")
        actual_cache_write = 0
        if self.policy.schema_version == 2:
            details = usage.get("input_tokens_details")
            if not isinstance(details, dict):
                self._receipt(reservation_hash, "uncertain", reserved)
                raise ProviderError("response omitted cache-write usage")
            raw_cache_write = details.get("cache_write_tokens")
            if type(raw_cache_write) is not int or raw_cache_write < 0:
                self._receipt(reservation_hash, "uncertain", reserved)
                raise ProviderError("response returned invalid cache-write usage")
            actual_cache_write = raw_cache_write
        if (
            actual_input > tokens
            or actual_output > output_cap
            or actual_cache_write > actual_input
            or response.get("service_tier") != "default"
            or response.get("model") != self.policy.model
        ):
            self._receipt(reservation_hash, "violation", reserved)
            raise ProviderError("response violated reserved pricing assumptions")
        self._receipt(
            reservation_hash,
            "settled",
            self.policy.cost(actual_input, actual_output, actual_cache_write),
            actual_input,
            actual_output,
            actual_cache_write if self.policy.schema_version == 2 else None,
        )
        return response

    def _receipt(
        self,
        reservation_hash: str,
        status: Literal["settled", "uncertain", "violation"],
        retained: int,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_write_tokens: int | None = None,
    ) -> None:
        if self.ledger is not None:
            self.ledger.settle(
                LedgerSettlement(
                    entry_id=self.ledger_entry_id,
                    reservation_sha256=reservation_hash,
                    status=status,
                    charged_microusd=retained,
                )
            )
        private_write(
            self.directory / "spend-receipt.json",
            canonical_bytes(
                SpendReceipt(
                    reservation_sha256=reservation_hash,
                    status=status,
                    retained_microusd=retained,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_write_tokens=cache_write_tokens,
                    ledger_id=self.ledger.policy.ledger_id if self.ledger else None,
                    ledger_entry_id=self.ledger_entry_id if self.ledger else None,
                )
            ),
        )


class PreReservedOpenAITransport:
    """Spend controller for one exact request whose full envelope is already held."""

    def __init__(
        self,
        transport: CountedTransport,
        policy: SpendPolicy,
        directory: Path,
        ledger: SpendLedger,
        reservation: SpendReservation,
        ledger_entry: LedgerEntry,
    ) -> None:
        self.transport = transport
        self.policy = policy
        self.directory = directory
        self.ledger: SpendLedger | None = ledger
        self.reservation = reservation
        self.ledger_entry = ledger_entry
        self.ledger_entry_id = ledger_entry.entry_id
        self._used = False

    def _required_ledger(self) -> SpendLedger:
        if self.ledger is None:  # Defensive parity with the broker protocol.
            raise ValueError(
                "pre-reserved controller requires shared spending admission"
            )
        return self.ledger

    def _require_held(self) -> None:
        status = self._required_ledger().entry_status(self.ledger_entry.entry_id)
        if (
            status is None
            or status.entry_id != self.ledger_entry.entry_id
            or status.reservation_sha256 != self.ledger_entry.reservation_sha256
            or status.reserved_microusd != self.ledger_entry.reserved_microusd
            or status.charged_microusd != self.ledger_entry.reserved_microusd
            or status.status != "held"
        ):
            raise ValueError("spending reservation is not the exact held entry")

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if self._used:
            raise ProviderError("spending controller permits one response only")
        self._used = True
        self.policy.check_current()
        request, output_cap = _normalized_text_request(payload, self.policy)
        reservation_hash = digest(canonical_bytes(self.reservation))
        if (
            self.reservation.policy_sha256 != self.policy.policy_sha256
            or self.reservation.request_sha256 != _request_sha256(request)
            or self.reservation.input_tokens != self.policy.max_input_tokens
            or self.reservation.max_output_tokens != self.policy.max_output_tokens
            or output_cap != self.reservation.max_output_tokens
            or self.reservation.reserved_microusd
            != self.policy.reservation_cost(
                self.policy.max_input_tokens, self.policy.max_output_tokens
            )
            or self.reservation.reserved_microusd != self.ledger_entry.reserved_microusd
            or reservation_hash != self.ledger_entry.reservation_sha256
        ):
            raise ValueError("pre-reserved spending envelope is inconsistent")
        self._require_held()
        private_write(
            self.directory / "spend-reservation.json", canonical_bytes(self.reservation)
        )
        try:
            tokens = await self.transport.count_input_tokens(
                copy.deepcopy(_count_payload(request))
            )
        except BaseException:
            self._receipt(
                reservation_hash, "uncertain", self.reservation.reserved_microusd
            )
            raise
        if type(tokens) is not int or tokens < 0:
            self._receipt(
                reservation_hash, "uncertain", self.reservation.reserved_microusd
            )
            raise ProviderError("provider returned an invalid input count")
        if tokens > self.reservation.input_tokens:
            self._receipt(
                reservation_hash, "violation", self.reservation.reserved_microusd
            )
            raise ProviderError("input count exceeded the held spending envelope")
        try:
            self.policy.check_current()
            self._require_held()
        except BaseException:
            # A current exact hold is mandatory immediately before generation. If
            # another trusted process changed it, this process must not settle it.
            raise
        try:
            response = await self.transport.create_response(request)
        except BaseException:
            self._receipt(
                reservation_hash, "uncertain", self.reservation.reserved_microusd
            )
            raise
        usage = response.get("usage")
        if not isinstance(usage, dict):
            self._receipt(
                reservation_hash, "uncertain", self.reservation.reserved_microusd
            )
            raise ProviderError("response omitted billable usage")
        actual_input = usage.get("input_tokens")
        actual_output = usage.get("output_tokens")
        if (
            type(actual_input) is not int
            or type(actual_output) is not int
            or actual_input < 0
            or actual_output < 0
        ):
            self._receipt(
                reservation_hash, "uncertain", self.reservation.reserved_microusd
            )
            raise ProviderError("response returned invalid billable usage")
        details = usage.get("input_tokens_details")
        if not isinstance(details, dict):
            self._receipt(
                reservation_hash, "uncertain", self.reservation.reserved_microusd
            )
            raise ProviderError("response omitted cache-write usage")
        actual_cache_write = details.get("cache_write_tokens")
        if type(actual_cache_write) is not int or actual_cache_write < 0:
            self._receipt(
                reservation_hash, "uncertain", self.reservation.reserved_microusd
            )
            raise ProviderError("response returned invalid cache-write usage")
        if (
            actual_input > self.reservation.input_tokens
            or actual_output > self.reservation.max_output_tokens
            or actual_cache_write > actual_input
            or response.get("service_tier") != "default"
            or response.get("model") != self.policy.model
        ):
            self._receipt(
                reservation_hash, "violation", self.reservation.reserved_microusd
            )
            raise ProviderError("response violated reserved pricing assumptions")
        actual = self.policy.cost(actual_input, actual_output, actual_cache_write)
        if actual > self.reservation.reserved_microusd:
            self._receipt(
                reservation_hash, "violation", self.reservation.reserved_microusd
            )
            raise ProviderError("response cost exceeded the held spending envelope")
        self._receipt(
            reservation_hash,
            "settled",
            actual,
            actual_input,
            actual_output,
            actual_cache_write,
        )
        return response

    def _receipt(
        self,
        reservation_hash: str,
        status: Literal["settled", "uncertain", "violation"],
        retained: int,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_write_tokens: int | None = None,
    ) -> None:
        ledger = self._required_ledger()
        ledger.settle(
            LedgerSettlement(
                entry_id=self.ledger_entry_id,
                reservation_sha256=reservation_hash,
                status=status,
                charged_microusd=retained,
            )
        )
        private_write(
            self.directory / "spend-receipt.json",
            canonical_bytes(
                SpendReceipt(
                    reservation_sha256=reservation_hash,
                    status=status,
                    retained_microusd=retained,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_write_tokens=cache_write_tokens,
                    ledger_id=ledger.policy.ledger_id,
                    ledger_entry_id=self.ledger_entry_id,
                )
            ),
        )
