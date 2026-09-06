"""Deterministic one-assignment OpenAI conformance request construction."""

from __future__ import annotations

from pydantic import JsonValue

from mos_eisley.core.models import Critique, canonical_bytes
from mos_eisley.evaluation.execution import EvaluationRequest, ExecutionBatch
from mos_eisley.providers.openai_spend import SpendPolicy


def _strict_schema(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [_strict_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, JsonValue] = {
        key: _strict_schema(item)
        for key, item in value.items()
        if key not in ("default", "title")
    }
    properties = result.get("properties")
    if result.get("type") == "object" and isinstance(properties, dict):
        result["required"] = list(properties)
        result["additionalProperties"] = False
    return result


def critique_format() -> dict[str, JsonValue]:
    """OpenAI strict JSON Schema derived from the canonical Critique contract."""
    return {
        "format": {
            "type": "json_schema",
            "name": "mos_eisley_critique",
            "strict": True,
            "schema": _strict_schema(Critique.model_json_schema()),
        }
    }


def _assignment(batch: ExecutionBatch, sample_id: str) -> EvaluationRequest:
    matches = [item for item in batch.requests if item.sample_id == sample_id]
    if len(matches) != 1:
        raise ValueError("conformance requires one exact assignment")
    return matches[0]


def build_openai_conformance_payload(
    batch: ExecutionBatch, sample_id: str, policy: SpendPolicy
) -> dict[str, JsonValue]:
    """Build a text-only, no-tools request wholly from the blinded assignment."""
    request = _assignment(batch, sample_id)
    if request.route.provider != "openai":
        raise ValueError("conformance assignment provider must be OpenAI")
    if request.route.model != policy.model:
        raise ValueError("conformance assignment differs from spending policy")
    return {
        "model": request.route.model,
        "instructions": request.route.prompt.instructions,
        "input": [
            {
                "role": "user",
                "content": canonical_bytes(request.brief).decode("utf-8"),
            }
        ],
        "tools": [],
        "reasoning": {"effort": request.route.effort},
        "text": critique_format(),
        "max_output_tokens": policy.max_output_tokens,
        "parallel_tool_calls": False,
        "store": False,
        "truncation": "disabled",
    }
