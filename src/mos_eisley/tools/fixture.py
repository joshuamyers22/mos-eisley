"""A bounded, in-memory dispatcher for protocol tests and demonstrations."""

import json
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from mos_eisley.core.models import Contract
from mos_eisley.core.protocol import (
    ToolCallBlock,
    ToolDefinition,
    ToolResultBlock,
    ToolSchema,
)


class FixtureValues(Contract):
    schema_version: Literal[1] = 1
    values: Annotated[dict[str, str], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def bounded_values(self) -> Self:
        if any(not key or len(key) > 80 for key in self.values):
            raise ValueError("fixture keys must contain 1 to 80 characters")
        if any(len(value) > 4000 for value in self.values.values()):
            raise ValueError("fixture values must contain at most 4000 characters")
        return self


class FixtureDispatcher:
    _definition = ToolDefinition(
        name="fixture_lookup",
        description="Look up one value from the bounded in-memory fixture.",
        input_schema=ToolSchema(
            type="object",
            properties={"key": ToolSchema(type="string")},
            required=("key",),
        ),
    )

    def __init__(self, fixtures: FixtureValues) -> None:
        self.fixtures = fixtures

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return (self._definition,)

    async def dispatch(self, call: ToolCallBlock) -> ToolResultBlock:
        if call.name != self._definition.name:
            return ToolResultBlock(
                call_id=call.id,
                name=call.name,
                content="unknown tool",
                is_error=True,
            )
        if set(call.args) != {"key"} or not isinstance(call.args["key"], str):
            return ToolResultBlock(
                call_id=call.id,
                name=call.name,
                content="invalid fixture_lookup arguments",
                is_error=True,
            )
        key = call.args["key"]
        value = self.fixtures.values.get(key)
        if value is None:
            return ToolResultBlock(
                call_id=call.id,
                name=call.name,
                content="fixture key not found",
                is_error=True,
            )
        return ToolResultBlock(
            call_id=call.id,
            name=call.name,
            content=json.dumps({"key": key, "value": value}, sort_keys=True),
        )
