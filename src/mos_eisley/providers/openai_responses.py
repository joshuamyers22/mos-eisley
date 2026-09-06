"""OpenAI Responses API adapter for the canonical model protocol."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Protocol, cast

from openai import AsyncOpenAI, OpenAIError
from openai.types.responses import Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
)

from mos_eisley.core.ports import ProviderError
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    ReasoningBlock,
    StopReason,
    TextBlock,
    ToolCallBlock,
    ToolDefinition,
    ToolSchema,
    Turn,
    Usage,
)

_IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
_ARGUMENTS = TypeAdapter(dict[str, JsonValue])


class OpenAITransport(Protocol):
    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]: ...


class SDKOpenAITransport:
    """Small SDK boundary so protocol translation can be tested without network."""

    def __init__(self, client: AsyncOpenAI) -> None:
        self.client = client

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        try:
            count = await self.client.responses.input_tokens.count(**cast(Any, payload))
        except OpenAIError as error:
            raise ProviderError("OpenAI token count failed") from error
        return count.input_tokens

    async def create_response(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        try:
            response = cast(
                Response,
                await self.client.responses.create(**cast(Any, payload)),
            )
        except OpenAIError as error:
            raise ProviderError("OpenAI request failed") from error
        return cast(dict[str, JsonValue], response.model_dump(mode="json"))


class _External(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class _Message(_External):
    type: str
    role: str
    content: list[dict[str, JsonValue]]


class _FunctionCall(_External):
    type: str
    id: str
    call_id: str
    name: str
    arguments: str


class _Reasoning(_External):
    type: str
    id: str
    summary: list[dict[str, JsonValue]]
    encrypted_content: str | None = None


class _TokenDetails(_External):
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0


class _OpenAIUsage(_External):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    input_tokens_details: _TokenDetails = Field(default_factory=_TokenDetails)
    output_tokens_details: _TokenDetails = Field(default_factory=_TokenDetails)


class _IncompleteDetails(_External):
    reason: str


class _OpenAIResponse(_External):
    id: str = Field(min_length=1, max_length=1000)
    status: str
    output: list[dict[str, JsonValue]]
    usage: _OpenAIUsage
    incomplete_details: _IncompleteDetails | None = None


def _schema_payload(schema: ToolSchema) -> dict[str, JsonValue]:
    if schema.type == "object" and set(schema.required) != set(schema.properties):
        raise ProviderError("OpenAI strict tools require every property")
    payload: dict[str, JsonValue] = {"type": schema.type}
    if schema.type == "object":
        payload["additionalProperties"] = False
    if schema.description:
        payload["description"] = schema.description
    if schema.properties:
        payload["properties"] = {
            name: _schema_payload(child) for name, child in schema.properties.items()
        }
        payload["required"] = list(schema.required)
    if schema.items is not None:
        payload["items"] = _schema_payload(schema.items)
    if schema.enum:
        payload["enum"] = list(schema.enum)
    return payload


def _tool_payload(tool: ToolDefinition) -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": _schema_payload(tool.input_schema),
        "strict": True,
    }


def _provider_call_ids(request: ModelRequest) -> dict[str, str]:
    return {
        block.id: block.provider_call_id or block.id
        for turn in request.turns
        for block in turn.blocks
        if isinstance(block, ToolCallBlock)
    }


def _input_payload(request: ModelRequest) -> list[dict[str, JsonValue]]:
    call_ids = _provider_call_ids(request)
    items: list[dict[str, JsonValue]] = []
    for turn in request.turns:
        for block in turn.blocks:
            if isinstance(block, TextBlock):
                items.append({"role": turn.role, "content": block.text})
            elif isinstance(block, ReasoningBlock):
                if block.provider != "openai":
                    raise ProviderError("reasoning item belongs to another provider")
                items.append(block.opaque)
            elif isinstance(block, ToolCallBlock):
                call: dict[str, JsonValue] = {
                    "type": "function_call",
                    "call_id": block.provider_call_id or block.id,
                    "name": block.name,
                    "arguments": json.dumps(
                        block.args,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                }
                if block.native_id is not None:
                    call["id"] = block.native_id
                items.append(call)
            else:
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_ids[block.call_id],
                        "output": block.content,
                    }
                )
    return items


def request_payload(request: ModelRequest) -> dict[str, JsonValue]:
    if request.provider != "openai":
        raise ProviderError("OpenAI adapter received another provider")
    if request.max_output_tokens is None:
        raise ProviderError("OpenAI request requires an output token limit")
    return {
        "model": request.model,
        "instructions": request.system or None,
        "input": cast(JsonValue, _input_payload(request)),
        "tools": cast(JsonValue, [_tool_payload(tool) for tool in request.tools]),
        "reasoning": {"effort": request.effort},
        "max_output_tokens": request.max_output_tokens,
        "parallel_tool_calls": True,
        "include": ["reasoning.encrypted_content"],
        "store": False,
        "truncation": "disabled",
    }


def _harness_call_id(provider_call_id: str) -> str:
    if _IDENTIFIER.fullmatch(provider_call_id):
        return provider_call_id
    value = hashlib.sha256(provider_call_id.encode("utf-8")).hexdigest()
    return f"openai-{value}"


def _chunks(text: str, size: int = 8000) -> tuple[str, ...]:
    return tuple(text[index : index + size] for index in range(0, len(text), size))


def _text_from_content(content: dict[str, JsonValue]) -> tuple[str, bool]:
    kind = content.get("type")
    if kind == "output_text" and isinstance(content.get("text"), str):
        return cast(str, content["text"]), False
    if kind == "refusal" and isinstance(content.get("refusal"), str):
        return cast(str, content["refusal"]), True
    raise ProviderError("OpenAI returned unsupported message content")


def response_from_payload(payload: dict[str, JsonValue]) -> ModelResponse:
    try:
        response = _OpenAIResponse.model_validate(payload)
    except ValidationError as error:
        raise ProviderError("OpenAI returned an invalid response") from error

    blocks: list[TextBlock | ReasoningBlock | ToolCallBlock] = []
    refused = False
    for raw_item in response.output:
        kind = raw_item.get("type")
        try:
            if kind == "message":
                message = _Message.model_validate(raw_item)
                if message.role != "assistant":
                    raise ProviderError("OpenAI returned a non-assistant message")
                for content in message.content:
                    text, is_refusal = _text_from_content(content)
                    refused = refused or is_refusal
                    blocks.extend(TextBlock(text=part) for part in _chunks(text))
            elif kind == "function_call":
                call = _FunctionCall.model_validate(raw_item)
                args = _ARGUMENTS.validate_python(json.loads(call.arguments))
                blocks.append(
                    ToolCallBlock(
                        id=_harness_call_id(call.call_id),
                        provider_call_id=call.call_id,
                        native_id=call.id,
                        name=call.name,
                        args=args,
                    )
                )
            elif kind == "reasoning":
                reasoning = _Reasoning.model_validate(raw_item)
                if reasoning.encrypted_content is None:
                    raise ProviderError("OpenAI omitted stateless reasoning content")
                summary = "\n".join(
                    cast(str, item["text"])
                    for item in reasoning.summary
                    if isinstance(item.get("text"), str)
                )
                blocks.append(
                    ReasoningBlock(
                        provider="openai",
                        visible=summary[:32_000] or None,
                        opaque=raw_item,
                    )
                )
            else:
                raise ProviderError("OpenAI returned an unsupported output item")
        except (ValidationError, json.JSONDecodeError) as error:
            raise ProviderError("OpenAI returned an invalid output item") from error

    if not blocks:
        raise ProviderError("OpenAI returned no canonical output")
    calls = any(isinstance(block, ToolCallBlock) for block in blocks)
    if response.status == "completed":
        stop_reason: StopReason = (
            "tool_use" if calls else "filtered" if refused else "end_turn"
        )
    elif (
        response.status == "incomplete"
        and response.incomplete_details is not None
        and response.incomplete_details.reason == "max_output_tokens"
    ):
        stop_reason = "max_output"
    else:
        stop_reason = "error"
    if calls and stop_reason != "tool_use":
        raise ProviderError("OpenAI returned incomplete tool calls")
    usage = response.usage
    return ModelResponse(
        turn=Turn(role="assistant", blocks=tuple(blocks)),
        stop_reason=stop_reason,
        usage=Usage(
            unit="tokens",
            input=usage.input_tokens,
            output=usage.output_tokens,
            reasoning=usage.output_tokens_details.reasoning_tokens,
            cache_read=usage.input_tokens_details.cached_tokens,
            cache_write=usage.input_tokens_details.cache_write_tokens,
        ),
        provider_request_id=response.id,
    )


class OpenAIResponsesClient:
    def __init__(self, transport: OpenAITransport) -> None:
        self.transport = transport

    async def complete(self, request: ModelRequest) -> ModelResponse:
        payload = request_payload(request)
        try:
            response = await self.transport.create_response(payload)
            return response_from_payload(response)
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError("OpenAI adapter failed") from error
