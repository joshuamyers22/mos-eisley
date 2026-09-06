"""Turn a validated broker response into non-scoreable evaluation conformance."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from mos_eisley.core.models import Contract, Critique, Digest, canonical_bytes, digest
from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import ReasoningBlock, TextBlock, Usage
from mos_eisley.providers.openai_responses import response_from_payload
from mos_eisley.run.broker_audit import (
    AssignmentAuthorization,
    inspect_broker_recovery,
)
from mos_eisley.run.broker_wire import BrokerReply
from mos_eisley.run.spend_ledger import SpendLedger


class BrokeredEvaluationArtifact(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["broker_conformance"] = "broker_conformance"
    authorization: AssignmentAuthorization
    authorization_sha256: Digest
    outcome_sha256: Digest
    provider_response_sha256: Digest
    provider_request_id: Annotated[str, Field(min_length=1, max_length=1000)]
    usage: Usage
    latency_ms: Annotated[int, Field(ge=0, le=86_400_000)]
    cost_microusd: Annotated[int, Field(ge=0, le=1_000_000_000_000)]
    critique: Critique
    promotion_eligible: Literal[False] = False

    @property
    def artifact_sha256(self) -> str:
        return digest(canonical_bytes(self))


def compile_brokered_evaluation(
    reply: BrokerReply,
    expected: AssignmentAuthorization,
    audit_directory: Path,
    ledger: SpendLedger,
) -> BrokeredEvaluationArtifact:
    """Validate audit, spend, OpenAI shape and strict critique before provenance."""
    state = inspect_broker_recovery(audit_directory, expected, ledger)
    response_hash = digest(canonical_bytes(reply))
    if (
        state.phase != "finished"
        or state.outcome_status != "response_received"
        or state.outcome_sha256 is None
        or state.response_sha256 != response_hash
        or state.ledger_status != "settled"
        or state.latency_ms is None
    ):
        raise ValueError("brokered evaluation provenance is incomplete")
    entry = ledger.entry_status(expected.ledger_entry_id)
    if entry is None or entry.status != "settled":
        raise ValueError("brokered evaluation spending is incomplete")
    try:
        response = response_from_payload(reply.response)
        if response.stop_reason != "end_turn" or any(
            not isinstance(block, (TextBlock, ReasoningBlock))
            for block in response.turn.blocks
        ):
            raise ValueError("response did not complete with text")
        text = "".join(
            block.text for block in response.turn.blocks if isinstance(block, TextBlock)
        )
        critique = Critique.model_validate_json(text)
        if response.provider_request_id is None:
            raise ValueError("provider request identity is absent")
    except (ProviderError, ValidationError, ValueError):
        raise ValueError("brokered critique validation failed") from None
    return BrokeredEvaluationArtifact(
        authorization=expected,
        authorization_sha256=state.authorization_sha256,
        outcome_sha256=state.outcome_sha256,
        provider_response_sha256=response_hash,
        provider_request_id=response.provider_request_id,
        usage=response.usage,
        latency_ms=state.latency_ms,
        cost_microusd=entry.charged_microusd,
        critique=critique,
    )
