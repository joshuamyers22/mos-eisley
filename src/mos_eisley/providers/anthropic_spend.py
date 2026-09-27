"""Pre-reserved, one-use Claude Messages spending controller."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Literal

from pydantic import JsonValue

from mos_eisley.core.models import canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.providers.openai_spend import (
    CountedTransport,
    SpendPolicy,
    SpendReceipt,
    SpendReservation,
)
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerSettlement, SpendLedger
from mos_eisley.run.store import private_write


def _request(
    payload: dict[str, JsonValue], policy: SpendPolicy
) -> dict[str, JsonValue]:
    value = copy.deepcopy(payload)
    if policy.provider != "anthropic" or value.get("model") != policy.model:
        raise ProviderError("Anthropic spending policy model or provider mismatch")
    if set(value) - {
        "model",
        "system",
        "messages",
        "max_tokens",
        "output_config",
        "thinking",
        "service_tier",
        "stream",
    }:
        raise ProviderError("Anthropic request contains unpriced controls")
    if (
        value.get("service_tier") != "standard_only"
        or value.get("stream") is not False
        or value.get("thinking") != {"type": "adaptive"}
        or value.get("output_config")
        not in (
            {"effort": "low"},
            {"effort": "medium"},
            {"effort": "high"},
            {"effort": "xhigh"},
            {"effort": "max"},
        )
        or not isinstance(value.get("system"), str)
    ):
        raise ProviderError("Anthropic request has unsupported review controls")
    output = value.get("max_tokens")
    if type(output) is not int or not 1 <= output <= policy.max_output_tokens:
        raise ProviderError("Anthropic output limit exceeds spending policy")
    messages = value.get("messages")
    if not isinstance(messages, list) or len(messages) != 1:
        raise ProviderError("Anthropic review requires one user message")
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise ProviderError("Anthropic message shape is unsupported")
        if message.get("role") != "user":
            raise ProviderError("Anthropic message role is unsupported")
        content = message.get("content")
        if not isinstance(content, list) or not content:
            raise ProviderError("Anthropic message content is unsupported")
        for block in content:
            if (
                not isinstance(block, dict)
                or set(block) != {"type", "text"}
                or block.get("type") != "text"
                or not isinstance(block.get("text"), str)
            ):
                raise ProviderError("Anthropic content has unpriced capabilities")
    return value


def request_sha256(payload: dict[str, JsonValue]) -> str:
    return digest(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    )


def count_payload(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        key: value
        for key, value in payload.items()
        if key not in ("max_tokens", "service_tier", "stream")
    }


def prepare_full_anthropic_reservation(
    payload: dict[str, JsonValue], policy: SpendPolicy
) -> SpendReservation:
    policy.check_current()
    request = _request(payload, policy)
    if request["max_tokens"] != policy.max_output_tokens:
        raise ValueError("full Anthropic reservation requires exact output cap")
    amount = policy.reservation_cost(policy.max_input_tokens, policy.max_output_tokens)
    if amount > policy.max_cost_microusd:
        raise ValueError("full Anthropic reservation exceeds per-call policy")
    return SpendReservation(
        policy_sha256=policy.policy_sha256,
        request_sha256=request_sha256(request),
        input_tokens=policy.max_input_tokens,
        max_output_tokens=policy.max_output_tokens,
        reserved_microusd=amount,
    )


class PreReservedAnthropicTransport:
    """Use one held ledger entry for count and generation, then settle once."""

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
        if self.ledger is None:
            raise ValueError("Anthropic controller requires shared spending admission")
        return self.ledger

    def _require_held(self) -> None:
        ledger = self._required_ledger()
        if ledger.snapshot().blocked:
            raise ValueError("spending ledger is blocked")
        status = ledger.entry_status(self.ledger_entry.entry_id)
        if (
            status is None
            or status.status != "held"
            or status.reservation_sha256 != self.ledger_entry.reservation_sha256
            or status.reserved_microusd != self.ledger_entry.reserved_microusd
            or status.charged_microusd != self.ledger_entry.reserved_microusd
        ):
            raise ValueError("Anthropic spending reservation is not held")

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if self._used:
            raise ProviderError("Anthropic spending controller permits one response")
        self._used = True
        self.policy.check_current()
        request = _request(payload, self.policy)
        expected = prepare_full_anthropic_reservation(request, self.policy)
        reservation_sha256 = digest(canonical_bytes(self.reservation))
        if (
            expected != self.reservation
            or reservation_sha256 != self.ledger_entry.reservation_sha256
            or expected.reserved_microusd != self.ledger_entry.reserved_microusd
        ):
            raise ValueError("Anthropic held spending envelope differs from request")
        self._require_held()
        private_write(
            self.directory / "spend-reservation.json", canonical_bytes(self.reservation)
        )
        status: Literal["settled", "uncertain", "violation"] = "uncertain"
        retained = self.reservation.reserved_microusd
        actual_input: int | None = None
        actual_output: int | None = None
        cache_write: int | None = None
        try:
            count = await self.transport.count_input_tokens(
                copy.deepcopy(count_payload(request))
            )
            if type(count) is not int or count < 0:
                raise ProviderError("Anthropic returned an invalid input count")
            if count > self.reservation.input_tokens:
                status = "violation"
                raise ProviderError("Anthropic input count exceeded held envelope")
            self.policy.check_current()
            self._require_held()
            response = await self.transport.create_response(request)
            usage = response.get("usage")
            if not isinstance(usage, dict):
                raise ProviderError("Anthropic response omitted billable usage")
            base = usage.get("input_tokens")
            read = usage.get("cache_read_input_tokens", 0)
            written = usage.get("cache_creation_input_tokens", 0)
            output = usage.get("output_tokens")
            if any(
                type(item) is not int or item < 0
                for item in (base, read, written, output)
            ):
                raise ProviderError(
                    "Anthropic response returned invalid billable usage"
                )
            assert isinstance(base, int) and isinstance(read, int)
            assert isinstance(written, int) and isinstance(output, int)
            actual_input = base + read + written
            actual_output = output
            cache_write = written
            if (
                response.get("model") != self.policy.model
                or actual_input > self.reservation.input_tokens
                or actual_output > self.reservation.max_output_tokens
                or (self.policy.schema_version == 1 and written != 0)
            ):
                status = "violation"
                raise ProviderError("Anthropic response violated reserved pricing")
            retained = self.policy.cost(actual_input, actual_output, written)
            if retained > self.reservation.reserved_microusd:
                retained = self.reservation.reserved_microusd
                status = "violation"
                raise ProviderError("Anthropic response exceeded reserved cost")
            status = "settled"
            return response
        finally:
            self._required_ledger().settle(
                LedgerSettlement(
                    entry_id=self.ledger_entry_id,
                    reservation_sha256=reservation_sha256,
                    status=status,
                    charged_microusd=retained,
                )
            )
            private_write(
                self.directory / "spend-receipt.json",
                canonical_bytes(
                    SpendReceipt(
                        reservation_sha256=reservation_sha256,
                        status=status,
                        retained_microusd=retained,
                        input_tokens=actual_input,
                        output_tokens=actual_output,
                        cache_write_tokens=cache_write,
                        ledger_id=self._required_ledger().policy.ledger_id,
                        ledger_entry_id=self.ledger_entry_id,
                    )
                ),
            )
