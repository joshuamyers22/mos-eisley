"""One-response spending reservation for text-only OpenAI preview calls."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, JsonValue, model_validator

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.run.store import private_write

Money = Annotated[int, Field(ge=0, le=1_000_000_000_000)]


class SpendPolicy(Contract):
    schema_version: Literal[1] = 1
    model: Identifier
    currency: Literal["USD"] = "USD"
    service_tier: Literal["default"] = "default"
    pricing_source: Annotated[str, Field(min_length=1, max_length=1000)]
    valid_from: datetime
    valid_until: datetime
    input_microusd_per_million: Annotated[int, Field(gt=0, le=1_000_000_000_000)]
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
        return self

    def check_current(self) -> None:
        if not self.valid_from <= datetime.now(UTC) < self.valid_until:
            raise ValueError("spending policy is outside its validity window")

    @property
    def policy_sha256(self) -> str:
        return digest(canonical_bytes(self))

    def cost(self, input_tokens: int, output_tokens: int) -> int:
        # No cache discount is assumed; output_tokens already includes reasoning.
        return (
            input_tokens * self.input_microusd_per_million
            + output_tokens * self.output_microusd_per_million
            + 999_999
        ) // 1_000_000


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


class CountedTransport(Protocol):
    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int: ...
    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]: ...


class BudgetedOpenAITransport:
    """Single use: uncertain responses retain the reservation and are never retried."""

    def __init__(
        self, transport: CountedTransport, policy: SpendPolicy, directory: Path
    ):
        self.transport = transport
        self.policy = policy
        self.directory = directory
        self._used = False

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if self._used:
            raise ProviderError("spending controller permits one response only")
        self._used = True  # Set before the first await, including concurrent callers.
        request = copy.deepcopy(payload)
        self.policy.check_current()
        if request.get("model") != self.policy.model:
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
            "truncation",
        }
        if set(request) - permitted or request.get("tools"):
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
        if (
            type(output_cap) is not int
            or not 1 <= output_cap <= self.policy.max_output_tokens
        ):
            raise ProviderError("output limit exceeds spending policy")
        request["store"] = False
        request["truncation"] = "disabled"
        request["service_tier"] = "default"
        count_payload = {
            key: value
            for key, value in request.items()
            if key not in ("max_output_tokens", "store", "include", "service_tier")
        }
        tokens = await self.transport.count_input_tokens(copy.deepcopy(count_payload))
        if type(tokens) is not int or not 0 <= tokens <= self.policy.max_input_tokens:
            raise ProviderError("input count exceeds spending policy")
        self.policy.check_current()
        reserved = self.policy.cost(tokens, output_cap)
        if reserved > self.policy.max_cost_microusd:
            raise ProviderError("response reservation exceeds spending limit")
        reservation = SpendReservation(
            policy_sha256=self.policy.policy_sha256,
            request_sha256=digest(
                json.dumps(
                    request, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ),
            input_tokens=tokens,
            max_output_tokens=output_cap,
            reserved_microusd=reserved,
        )
        reservation_bytes = canonical_bytes(reservation)
        private_write(self.directory / "spend-reservation.json", reservation_bytes)
        reservation_hash = digest(reservation_bytes)
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
        if (
            actual_input > tokens
            or actual_output > output_cap
            or response.get("service_tier") != "default"
            or response.get("model") != self.policy.model
        ):
            self._receipt(reservation_hash, "violation", reserved)
            raise ProviderError("response violated reserved pricing assumptions")
        self._receipt(
            reservation_hash,
            "settled",
            self.policy.cost(actual_input, actual_output),
            actual_input,
            actual_output,
        )
        return response

    def _receipt(
        self,
        reservation_hash: str,
        status: Literal["settled", "uncertain", "violation"],
        retained: int,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        private_write(
            self.directory / "spend-receipt.json",
            canonical_bytes(
                SpendReceipt(
                    reservation_sha256=reservation_hash,
                    status=status,
                    retained_microusd=retained,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            ),
        )
