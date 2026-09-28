"""Claude Messages translation for the provider-neutral model protocol."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Protocol, cast

from anthropic import (
    AnthropicError,
    APIConnectionError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from anthropic.types import Message
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from mos_eisley.core.ports import ProviderError, ProviderFailureKind
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    ReasoningBlock,
    StopReason,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
    ToolSchema,
    Turn,
    Usage,
)

_IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")


class AnthropicTransport(Protocol):
    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int: ...

    async def create_message(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]: ...


def safe_anthropic_failure_kind(error: AnthropicError) -> ProviderFailureKind:
    """Classify SDK exceptions without retaining messages, headers or bodies."""
    if isinstance(error, AuthenticationError):
        return "authentication_error"
    if isinstance(error, PermissionDeniedError):
        return "permission_error"
    if isinstance(error, RateLimitError):
        return "rate_limit_error"
    if isinstance(error, NotFoundError):
        return "not_found_error"
    if isinstance(error, BadRequestError):
        return "invalid_request_error"
    if isinstance(error, APITimeoutError):
        return "provider_timeout"
    if isinstance(error, APIConnectionError):
        return "transport_error"
    return "provider_error"


class SDKAnthropicTransport:
    """One SDK boundary; callers own credential, lifetime and spending admission."""

    def __init__(self, client: AsyncAnthropic) -> None:
        self.client = client

    async def create_message(
        self, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        try:
            result = cast(
                Message, await self.client.messages.create(**cast(Any, payload))
            )
        except AnthropicError as error:
            raise ProviderError(
                "Anthropic request failed",
                failure_kind=safe_anthropic_failure_kind(error),
                failure_stage="response",
            ) from None
        return cast(dict[str, JsonValue], result.model_dump(mode="json"))

    async def count_input_tokens(self, payload: dict[str, JsonValue]) -> int:
        count_payload = {
            key: value
            for key, value in payload.items()
            if key not in ("max_tokens", "service_tier", "stream")
        }
        try:
            count = await self.client.messages.count_tokens(**cast(Any, count_payload))
        except AnthropicError as error:
            raise ProviderError(
                "Anthropic token count failed",
                failure_kind=safe_anthropic_failure_kind(error),
                failure_stage="token_count",
            ) from None
        return count.input_tokens


def _schema_payload(schema: ToolSchema) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {"type": schema.type}
    if schema.description:
        result["description"] = schema.description
    if schema.type == "object":
        result["properties"] = {
            name: _schema_payload(child) for name, child in schema.properties.items()
        }
        result["required"] = list(schema.required)
        result["additionalProperties"] = False
    if schema.items is not None:
        result["items"] = _schema_payload(schema.items)
    if schema.enum:
        result["enum"] = list(schema.enum)
    return result


def _reasoning_payload(item: dict[str, JsonValue]) -> dict[str, JsonValue]:
    kind = item.get("type")
    if kind == "thinking":
        if (
            set(item) != {"type", "thinking", "signature"}
            or not isinstance(item.get("thinking"), str)
            or not isinstance(item.get("signature"), str)
        ):
            raise ProviderError("Anthropic thinking block is incomplete")
    elif kind == "redacted_thinking":
        if set(item) != {"type", "data"} or not isinstance(item.get("data"), str):
            raise ProviderError("Anthropic redacted thinking block is incomplete")
    else:
        raise ProviderError("reasoning block belongs to another provider")
    return item


def request_payload(request: ModelRequest) -> dict[str, JsonValue]:
    """Preserve ordered Claude content blocks, including signed reasoning."""
    if request.provider != "anthropic":
        raise ProviderError("Anthropic adapter received another provider")
    if request.max_output_tokens is None:
        raise ProviderError("Anthropic request requires an output token limit")
    if request.effort not in ("low", "medium", "high", "xhigh", "max"):
        raise ProviderError("Anthropic model does not support this effort")
    messages: list[dict[str, JsonValue]] = []
    call_ids = {
        block.id: block.provider_call_id or block.id
        for turn in request.turns
        for block in turn.blocks
        if isinstance(block, ToolCallBlock)
    }
    for turn in request.turns:
        content: list[dict[str, JsonValue]] = []
        for block in turn.blocks:
            if isinstance(block, TextBlock):
                content.append({"type": "text", "text": block.text})
            elif isinstance(block, ReasoningBlock):
                if block.provider != "anthropic":
                    raise ProviderError("reasoning block belongs to another provider")
                content.append(_reasoning_payload(block.opaque))
            elif isinstance(block, ToolCallBlock):
                content.append(
                    {
                        "type": "tool_use",
                        "id": block.provider_call_id or block.id,
                        "name": block.name,
                        "input": block.args,
                    }
                )
            else:
                assert isinstance(block, ToolResultBlock)
                content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call_ids[block.call_id],
                        "content": block.content,
                        "is_error": block.is_error,
                    }
                )
        messages.append({"role": turn.role, "content": cast(JsonValue, content)})
    payload: dict[str, JsonValue] = {
        "model": request.model,
        "max_tokens": request.max_output_tokens,
        "messages": cast(JsonValue, messages),
        "output_config": {"effort": request.effort},
        "thinking": {"type": "adaptive"},
        "service_tier": "standard_only",
        "stream": False,
    }
    if request.system:
        payload["system"] = request.system
    if request.tools:
        payload["tools"] = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": _schema_payload(tool.input_schema),
            }
            for tool in request.tools
        ]
        payload["tool_choice"] = {"type": "auto"}
    return payload


class _External(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class _Usage(_External):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_input_tokens: int = Field(default=0, ge=0)
    cache_creation_input_tokens: int = Field(default=0, ge=0)


class _Message(_External):
    id: str = Field(min_length=1, max_length=1000)
    type: str
    role: str
    model: str
    stop_reason: str | None
    content: list[dict[str, JsonValue]]
    usage: _Usage


def _harness_call_id(native_id: str) -> str:
    if _IDENTIFIER.fullmatch(native_id):
        return native_id
    return "anthropic-" + hashlib.sha256(native_id.encode()).hexdigest()


def _text_blocks(value: str) -> list[TextBlock]:
    return [
        TextBlock(text=value[index : index + 8000])
        for index in range(0, len(value), 8000)
    ]


def response_from_payload(payload: dict[str, JsonValue]) -> ModelResponse:
    try:
        message = _Message.model_validate(payload)
        if message.type != "message" or message.role != "assistant":
            raise ValueError("wrong message role or type")
        blocks: list[TextBlock | ReasoningBlock | ToolCallBlock] = []
        for item in message.content:
            kind = item.get("type")
            if kind == "text":
                value = item.get("text")
                if not isinstance(value, str):
                    raise ValueError("invalid text block")
                blocks.extend(_text_blocks(value))
            elif kind == "thinking":
                visible = item.get("thinking")
                signature = item.get("signature")
                if (
                    set(item) != {"type", "thinking", "signature"}
                    or not isinstance(visible, str)
                    or not isinstance(signature, str)
                ):
                    raise ValueError("unsigned thinking block")
                blocks.append(
                    ReasoningBlock(
                        provider="anthropic",
                        visible=visible[:32_000] or None,
                        opaque=item,
                    )
                )
            elif kind == "redacted_thinking":
                if set(item) != {"type", "data"} or not isinstance(
                    item.get("data"), str
                ):
                    raise ValueError("invalid redacted thinking block")
                blocks.append(ReasoningBlock(provider="anthropic", opaque=item))
            elif kind == "tool_use":
                native_id = item.get("id")
                name = item.get("name")
                args = item.get("input")
                if (
                    not isinstance(native_id, str)
                    or not native_id
                    or not isinstance(name, str)
                    or not isinstance(args, dict)
                ):
                    raise ValueError("invalid tool call")
                blocks.append(
                    ToolCallBlock(
                        id=_harness_call_id(native_id),
                        provider_call_id=native_id,
                        name=name,
                        args=args,
                    )
                )
            else:
                raise ValueError("unsupported Claude content")
        if not blocks:
            raise ValueError("empty Claude content")
        reasons: dict[str, StopReason] = {
            "end_turn": "end_turn",
            "tool_use": "tool_use",
            "max_tokens": "max_output",
            "model_context_window_exceeded": "max_output",
            "refusal": "filtered",
        }
        stop = reasons.get(message.stop_reason or "", "error")
        has_calls = any(isinstance(block, ToolCallBlock) for block in blocks)
        if has_calls != (stop == "tool_use"):
            raise ValueError("tool calls and stop reason disagree")
        usage = message.usage
        return ModelResponse(
            turn=Turn(role="assistant", blocks=tuple(blocks)),
            stop_reason=stop,
            usage=Usage(
                unit="tokens",
                input=(
                    usage.input_tokens
                    + usage.cache_read_input_tokens
                    + usage.cache_creation_input_tokens
                ),
                output=usage.output_tokens,
                cache_read=usage.cache_read_input_tokens,
                cache_write=usage.cache_creation_input_tokens,
            ),
            provider_request_id=message.id,
        )
    except (ValidationError, ValueError, TypeError) as error:
        raise ProviderError("Anthropic returned an invalid response") from error


class AnthropicMessagesClient:
    def __init__(self, transport: AnthropicTransport) -> None:
        self.transport = transport

    async def complete(self, request: ModelRequest) -> ModelResponse:
        payload = request_payload(request)
        try:
            response = await self.transport.create_message(payload)
            if response.get("model") != request.model:
                raise ProviderError("Anthropic response model does not match request")
            result = response_from_payload(response)
            if len(
                result.model_dump_json().encode()
            ) > request.max_output or result.usage.output > cast(
                int, request.max_output_tokens
            ):
                raise ProviderError("Anthropic response exceeded request bounds")
            return result
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError("Anthropic adapter failed") from error
