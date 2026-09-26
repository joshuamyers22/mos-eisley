"""One credentialed, synthetic Claude Messages probe with bounded spending."""

from __future__ import annotations

import asyncio
import json
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue

from mos_eisley.core.models import Contract, Digest, Identifier, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ModelRequest, TextBlock, Turn, Usage
from mos_eisley.providers.anthropic_live import EphemeralAnthropicTransport
from mos_eisley.providers.anthropic_messages import (
    AnthropicTransport,
    request_payload,
    response_from_payload,
)
from mos_eisley.providers.openai_spend import (
    SpendPolicy,
    SpendReceipt,
    SpendReservation,
)
from mos_eisley.run.files import read_bounded
from mos_eisley.run.spend_ledger import LedgerEntry, LedgerSettlement, SpendLedger
from mos_eisley.run.store import private_write

PROBE_MODEL = "claude-sonnet-5"
PROBE_MODELS = ("claude-sonnet-5", "claude-opus-5-5")
PROBE_PROMPT = "Synthetic API conformance probe. Reply with exactly OK."
PROBE_SYSTEM = "Return a short plain-text acknowledgement. Do not use tools."


class AnthropicProbeReceipt(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["anthropic_credentialed_probe"] = "anthropic_credentialed_probe"
    provider: Literal["anthropic"] = "anthropic"
    model: Identifier
    api_family: Literal["messages"] = "messages"
    request_sha256: Digest
    provider_request_id: str
    response_sha256: Digest
    policy_sha256: Digest
    ledger_id: Digest
    ledger_entry_id: Digest
    reservation_sha256: Digest
    settled_microusd: Annotated[int, Field(ge=0)]
    usage: Usage
    stop_reason: Literal["end_turn"] = "end_turn"
    credentialed_exchange_observed: Literal[True] = True
    provider_authorship_proven: Literal[False] = False
    billing_reconciled: Literal[False] = False
    review_role_conformance_proven: Literal[False] = False
    repeated_conformance_proven: Literal[False] = False
    evaluation_evidence_eligible: Literal[False] = False


def probe_request(policy: SpendPolicy) -> ModelRequest:
    if policy.provider != "anthropic" or policy.model not in PROBE_MODELS:
        raise ValueError("Anthropic probe policy must pin a supported Claude model")
    return ModelRequest(
        provider="anthropic",
        model=policy.model,
        effort="high",
        system=PROBE_SYSTEM,
        turns=(Turn(role="user", blocks=(TextBlock(text=PROBE_PROMPT),)),),
        max_output=16_000,
        max_output_tokens=policy.max_output_tokens,
    )


def load_anthropic_key(path: Path) -> str:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError("Anthropic key must be a private regular file")
    value = read_bounded(path, 4096).decode("utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise ValueError("Anthropic key file must contain one nonempty line")
    return value


def _json_bytes(value: dict[str, JsonValue]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _preflight(policy: SpendPolicy, ledger: SpendLedger, directory: Path) -> None:
    policy.check_current()
    probe_request(policy)
    if policy.schema_version != 1 or policy.max_output_tokens > 128:
        raise ValueError(
            "probe requires no-cache pricing and at most 128 output tokens"
        )
    if policy.max_input_tokens > 2048 or policy.max_cost_microusd > 10_000:
        raise ValueError("probe spending ceiling exceeds the fixed safety limit")
    if (
        policy.reservation_cost(policy.max_input_tokens, policy.max_output_tokens)
        > policy.max_cost_microusd
    ):
        raise ValueError("full reservation exceeds the reviewed per-call limit")
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("probe output directory must already exist")
    for name in ("reservation.json", "receipt.json", "result.json"):
        path = directory / name
        if path.exists() or path.is_symlink():
            raise ValueError("probe artifacts must be fresh")
    if ledger.entry_status(digest(str(directory.resolve()).encode())) is not None:
        raise ValueError("probe ledger entry already exists")
    if ledger.snapshot().blocked:
        raise ValueError("spending ledger is blocked")


async def run_anthropic_probe(
    *,
    policy: SpendPolicy,
    ledger: SpendLedger,
    directory: Path,
    transport: AnthropicTransport | EphemeralAnthropicTransport,
) -> AnthropicProbeReceipt:
    """Reserve a full envelope before count/send; never retry or release ambiguity."""
    _preflight(policy, ledger, directory)
    request = probe_request(policy)
    payload = request_payload(request)
    request_sha256 = digest(_json_bytes(payload))
    reserved = policy.reservation_cost(
        policy.max_input_tokens, policy.max_output_tokens
    )
    reservation = SpendReservation(
        policy_sha256=policy.policy_sha256,
        request_sha256=request_sha256,
        input_tokens=policy.max_input_tokens,
        max_output_tokens=policy.max_output_tokens,
        reserved_microusd=reserved,
    )
    reservation_sha256 = digest(canonical_bytes(reservation))
    entry_id = digest(str(directory.resolve()).encode())
    private_write(directory / "reservation.json", canonical_bytes(reservation))
    ledger.reserve(
        LedgerEntry(
            entry_id=entry_id,
            reservation_sha256=reservation_sha256,
            reserved_microusd=reserved,
        )
    )
    status: Literal["settled", "uncertain", "violation"] = "uncertain"
    charged = reserved
    input_tokens: int | None = None
    output_tokens: int | None = None
    result: AnthropicProbeReceipt | None = None
    try:
        count = await transport.count_input_tokens(payload)
        if type(count) is not int or count < 0 or count > policy.max_input_tokens:
            status = "violation"
            raise ProviderError("Anthropic count exceeded the held envelope")
        policy.check_current()
        response = await transport.create_message(payload)
        if response.get("model") != policy.model:
            status = "violation"
            raise ProviderError("Anthropic response model differs from request")
        usage = response.get("usage")
        if not isinstance(usage, dict):
            raise ProviderError("Anthropic response omitted usage")
        base = usage.get("input_tokens")
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)
        output = usage.get("output_tokens")
        if any(
            type(item) is not int or item < 0
            for item in (base, cache_read, cache_write, output)
        ):
            raise ProviderError("Anthropic response returned invalid usage")
        assert isinstance(base, int) and isinstance(cache_read, int)
        assert isinstance(cache_write, int) and isinstance(output, int)
        actual_input = base + cache_read + cache_write
        if (
            actual_input > policy.max_input_tokens
            or output > policy.max_output_tokens
            or cache_write != 0
        ):
            status = "violation"
            raise ProviderError("Anthropic response violated the held envelope")
        input_tokens, output_tokens = actual_input, output
        charged = policy.cost(actual_input, output)
        if charged > reserved:
            status = "violation"
            charged = reserved
            raise ProviderError("Anthropic response exceeded the reserved cost")
        # Pricing can settle even when content does not satisfy the probe.
        status = "settled"
        model_response = response_from_payload(response)
        if model_response.stop_reason != "end_turn" or not any(
            isinstance(block, TextBlock) and block.text.strip()
            for block in model_response.turn.blocks
        ):
            raise ProviderError("Anthropic probe did not complete with text")
        if len(canonical_bytes(model_response)) > request.max_output:
            raise ProviderError("Anthropic probe response exceeded the byte limit")
        provider_request_id = model_response.provider_request_id
        assert provider_request_id is not None
        result = AnthropicProbeReceipt(
            model=policy.model,
            request_sha256=request_sha256,
            provider_request_id=provider_request_id,
            response_sha256=digest(_json_bytes(response)),
            policy_sha256=policy.policy_sha256,
            ledger_id=ledger.policy.ledger_id,
            ledger_entry_id=entry_id,
            reservation_sha256=reservation_sha256,
            settled_microusd=charged,
            usage=model_response.usage,
        )
    finally:
        ledger.settle(
            LedgerSettlement(
                entry_id=entry_id,
                reservation_sha256=reservation_sha256,
                status=status,
                charged_microusd=charged,
            )
        )
        private_write(
            directory / "receipt.json",
            canonical_bytes(
                SpendReceipt(
                    reservation_sha256=reservation_sha256,
                    status=status,
                    retained_microusd=charged,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    ledger_id=ledger.policy.ledger_id,
                    ledger_entry_id=entry_id,
                )
            ),
        )
    assert result is not None
    private_write(directory / "result.json", canonical_bytes(result))
    return result


def run_from_paths(
    *, policy_path: Path, ledger_path: Path, key_path: Path, output_dir: Path
) -> AnthropicProbeReceipt:
    policy = SpendPolicy.model_validate_json(read_bounded(policy_path, 16_000))
    ledger = SpendLedger(ledger_path)
    policy.check_current(datetime.now(UTC))
    # Read the credential only after local policy, ledger and artifact preflight.
    _preflight(policy, ledger, output_dir)
    api_key = load_anthropic_key(key_path)
    try:
        return asyncio.run(
            run_anthropic_probe(
                policy=policy,
                ledger=ledger,
                directory=output_dir,
                transport=EphemeralAnthropicTransport(api_key, 30),
            )
        )
    finally:
        del api_key
