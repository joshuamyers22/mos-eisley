"""Canonical model, content, and tool contracts independent of provider SDKs."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from mos_eisley.core.models import Contract, Identifier, Text

Effort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
StopReason = Literal["end_turn", "tool_use", "max_output", "filtered", "error"]


class ToolSchema(Contract):
    """Small JSON Schema subset accepted by the offline protocol."""

    type: Literal["object", "string", "number", "integer", "boolean", "array"]
    description: Annotated[str, Field(max_length=2000)] = ""
    properties: Annotated[dict[str, ToolSchema], Field(max_length=64)] = Field(
        default_factory=dict
    )
    required: Annotated[tuple[str, ...], Field(max_length=64)] = ()
    items: ToolSchema | None = None
    enum: Annotated[tuple[str | int | float | bool, ...], Field(max_length=64)] = ()
    additional_properties: Literal[False] = False

    @model_validator(mode="after")
    def valid_shape(self) -> Self:
        property_names = set(self.properties)
        if any(not name or len(name) > 80 for name in property_names):
            raise ValueError("property names must contain 1 to 80 characters")
        if len(self.required) != len(set(self.required)):
            raise ValueError("required fields must be unique")
        if not set(self.required) <= property_names:
            raise ValueError("required fields must be declared properties")
        if self.type == "object":
            if self.items is not None or self.enum:
                raise ValueError("object schema cannot declare items or enum")
        elif self.properties or self.required:
            raise ValueError("only object schemas can declare properties")
        if self.type == "array" and self.items is None:
            raise ValueError("array schema requires items")
        if self.type != "array" and self.items is not None:
            raise ValueError("items is valid only for arrays")
        if self.type == "array" and self.enum:
            raise ValueError("array schema cannot declare enum")
        expected_types: dict[str, tuple[type[object], ...]] = {
            "string": (str,),
            "number": (int, float),
            "integer": (int,),
            "boolean": (bool,),
        }
        expected = expected_types.get(self.type)
        if expected is not None and any(
            not isinstance(value, expected)
            or (self.type in {"number", "integer"} and isinstance(value, bool))
            for value in self.enum
        ):
            raise ValueError("enum values must match the schema type")
        typed_values = tuple((type(value), value) for value in self.enum)
        if len(typed_values) != len(set(typed_values)):
            raise ValueError("enum values must be unique")
        return self


class ToolDefinition(Contract):
    name: Identifier
    description: Text
    input_schema: ToolSchema

    @model_validator(mode="after")
    def object_input(self) -> Self:
        if self.input_schema.type != "object":
            raise ValueError("tool input schema must be an object")
        return self


class TextBlock(Contract):
    kind: Literal["text"] = "text"
    text: Text


class ReasoningBlock(Contract):
    kind: Literal["reasoning"] = "reasoning"
    provider: Identifier
    visible: Annotated[str, Field(max_length=32_000)] | None = None
    opaque: dict[str, JsonValue]


class ToolCallBlock(Contract):
    kind: Literal["tool_call"] = "tool_call"
    id: Identifier
    name: Identifier
    args: dict[str, JsonValue]
    native_id: Annotated[str, Field(max_length=1000)] | None = None


class ToolResultBlock(Contract):
    kind: Literal["tool_result"] = "tool_result"
    call_id: Identifier
    name: Identifier
    content: Annotated[str, Field(max_length=64_000)]
    is_error: bool = False


Block = Annotated[
    TextBlock | ReasoningBlock | ToolCallBlock | ToolResultBlock,
    Field(discriminator="kind"),
]


class Turn(Contract):
    role: Literal["user", "assistant"]
    blocks: Annotated[tuple[Block, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def role_matches_blocks(self) -> Self:
        if self.role == "assistant" and any(
            isinstance(block, ToolResultBlock) for block in self.blocks
        ):
            raise ValueError("assistant turns cannot contain tool results")
        if self.role == "user" and any(
            isinstance(block, (ReasoningBlock, ToolCallBlock)) for block in self.blocks
        ):
            raise ValueError("user turns cannot contain reasoning or tool calls")
        return self


def validate_turn_sequence(turns: tuple[Turn, ...]) -> None:
    if turns[0].role != "user" or turns[-1].role != "user":
        raise ValueError("model request must start and end with a user turn")
    if any(
        left.role == right.role for left, right in zip(turns, turns[1:], strict=False)
    ):
        raise ValueError("model request turns must alternate roles")
    used_calls: set[str] = set()
    pending: dict[str, str] = {}
    for turn in turns:
        calls = tuple(
            block for block in turn.blocks if isinstance(block, ToolCallBlock)
        )
        results = tuple(
            block for block in turn.blocks if isinstance(block, ToolResultBlock)
        )
        if calls:
            if pending or any(call.id in used_calls for call in calls):
                raise ValueError("tool calls must have unique IDs and ordered results")
            pending = {call.id: call.name for call in calls}
            used_calls.update(pending)
        if turn.role == "user":
            if pending:
                returned = {result.call_id: result.name for result in results}
                if len(returned) != len(results) or returned != pending:
                    raise ValueError("tool results must match every pending call")
                pending = {}
            elif results:
                raise ValueError("tool result has no pending call")
    if pending:
        raise ValueError("model request has unresolved tool calls")


class Usage(Contract):
    unit: Literal["bytes"] = "bytes"
    input: Annotated[int, Field(ge=0)]
    output: Annotated[int, Field(ge=0)]
    reasoning: Annotated[int, Field(ge=0)] = 0
    cache_read: Annotated[int, Field(ge=0)] = 0
    cache_write: Annotated[int, Field(ge=0)] = 0


class ModelRequest(Contract):
    schema_version: Literal[1] = 1
    provider: Identifier
    model: Identifier
    effort: Effort
    system: Annotated[str, Field(max_length=64_000)] = ""
    tools: Annotated[tuple[ToolDefinition, ...], Field(max_length=64)] = ()
    turns: Annotated[tuple[Turn, ...], Field(min_length=1, max_length=256)]
    max_output: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def unique_tools(self) -> Self:
        names = tuple(tool.name for tool in self.tools)
        if len(names) != len(set(names)):
            raise ValueError("tool names must be unique")
        validate_turn_sequence(self.turns)
        return self


class ModelResponse(Contract):
    schema_version: Literal[1] = 1
    turn: Turn
    stop_reason: StopReason
    usage: Usage
    provider_request_id: Annotated[str, Field(max_length=1000)] | None = None

    @model_validator(mode="after")
    def valid_stop(self) -> Self:
        if self.turn.role != "assistant":
            raise ValueError("model response must contain an assistant turn")
        calls = tuple(
            block for block in self.turn.blocks if isinstance(block, ToolCallBlock)
        )
        if self.stop_reason == "tool_use" and not calls:
            raise ValueError("tool_use stop requires a tool call")
        if self.stop_reason != "tool_use" and calls:
            raise ValueError("tool calls require tool_use stop")
        if len({call.id for call in calls}) != len(calls):
            raise ValueError("tool call IDs must be unique within a response")
        return self


class JournalEvent(Contract):
    schema_version: Literal[1] = 1
    type: Literal[
        "model.request.started",
        "model.response.completed",
        "model.request.failed",
        "tool.completed",
        "tool.failed",
    ]
    request_id: Identifier
    sequence: Annotated[int, Field(ge=0)]
    payload_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    detail: Annotated[str, Field(max_length=256)] = ""
