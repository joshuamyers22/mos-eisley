"""Explicit operator-configured stdio MCP tools for the canonical agent port."""

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated, Any, Literal, Self, cast

from jsonschema import Draft202012Validator
from mcp import Client
from mcp.client.stdio import (
    DEFAULT_INHERITED_ENV_VARS,
    StdioServerParameters,
    stdio_client,
)
from mcp.types import CallToolResult, TextContent
from pydantic import Field, JsonValue, model_validator

from mos_eisley.core.models import Contract, Identifier, canonical_bytes
from mos_eisley.core.protocol import (
    ToolCallBlock,
    ToolDefinition,
    ToolResultBlock,
    ToolSchema,
)
from mos_eisley.tools.mcp_schema import lower_schema


class MCPFailure(ValueError):
    """Sanitized infrastructure failure; a submitted write may have committed."""


class _RedactSDKDiagnostic(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = "MCP transport diagnostic; details redacted"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


@contextmanager
def _redacted_sdk_logs() -> Generator[None]:
    # The locked SDK's stdio parser logs Pydantic exceptions, including rejected
    # wire values, before our boundary catches them. Filters must attach to the
    # emitting loggers: an ancestor logger's filter does not cover propagation.
    loggers = [
        logging.getLogger(name)
        for name in tuple(logging.Logger.manager.loggerDict)
        if name == "mcp" or name.startswith("mcp.")
    ]
    scrubber = _RedactSDKDiagnostic()
    for logger in loggers:
        logger.addFilter(scrubber)
    try:
        yield
    finally:
        for logger in loggers:
            logger.removeFilter(scrubber)


class MCPConfig(Contract):
    schema_version: Literal[1] = 1
    command: Annotated[str, Field(min_length=1, max_length=4096)]
    args: Annotated[tuple[str, ...], Field(max_length=64)] = ()
    cwd: Annotated[str, Field(min_length=1, max_length=4096)]
    env: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    tools: Annotated[
        dict[Identifier, Literal["read", "write"]], Field(min_length=1, max_length=64)
    ]
    allow_writes: bool = False
    timeout_seconds: Annotated[int, Field(ge=1, le=300)] = 30
    max_result_bytes: Annotated[int, Field(ge=1024, le=60000)] = 4000
    max_argument_bytes: Annotated[int, Field(ge=1024, le=1048576)] = 65536

    @model_validator(mode="after")
    def valid_launch(self) -> Self:
        if not Path(self.command).is_absolute() or not Path(self.cwd).is_absolute():
            raise ValueError("MCP command and cwd must be absolute")
        if any("\0" in value or len(value) > 8192 for value in self.args):
            raise ValueError("invalid MCP launch arguments")
        if len(set(self.env)) != len(self.env) or any(
            not key.isascii() or not key.isidentifier() for key in self.env
        ):
            raise ValueError("invalid environment allowlist")
        if not self.allow_writes and "write" in self.tools.values():
            raise ValueError("write tools require allow_writes in operator config")
        return self

    def parameters(self) -> StdioServerParameters:
        # The SDK merges its default environment. Blank those keys explicitly so
        # no parent value passes through unless the operator names it below.
        environment = dict.fromkeys(DEFAULT_INHERITED_ENV_VARS, "")
        for key in self.env:
            if key not in os.environ:
                raise MCPFailure("required MCP environment variable is missing")
            environment[key] = os.environ[key]
        return StdioServerParameters(
            command=self.command, args=list(self.args), cwd=self.cwd, env=environment
        )


class MCPDispatcher:
    """One session, one immutable catalog, and no automatic call retries."""

    def __init__(self, client: Client, config: MCPConfig) -> None:
        self._client = client
        # Revalidate and copy: frozen models can contain mutable dictionaries,
        # and Pydantic model_copy(update=...) deliberately bypasses validation.
        self._config = MCPConfig.model_validate_json(config.model_dump_json())
        self._definitions: tuple[ToolDefinition, ...] = ()
        self._schemas: dict[str, dict[str, Any]] = {}
        self._losses: dict[str, tuple[str, ...]] = {}
        self._used_ids: set[str] = set()
        self._ready = False
        self._lock = asyncio.Lock()

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(item.model_copy(deep=True) for item in self._definitions)

    @property
    def schema_changes(self) -> dict[str, tuple[str, ...]]:
        return self._losses.copy()

    def close(self) -> None:
        self._ready = False

    async def discover(self) -> None:
        if self._schemas:
            raise MCPFailure("MCP catalog is immutable for this session")
        definitions: list[ToolDefinition] = []
        seen: set[str] = set()
        cursors: set[str] = set()
        cursor: str | None = None
        async with asyncio.timeout(self._config.timeout_seconds):
            for _ in range(16):
                result = await self._client.list_tools(cursor=cursor)
                if len(result.model_dump_json().encode()) > 262144:
                    raise MCPFailure("MCP catalog exceeds the byte limit")
                for tool in result.tools:
                    if tool.name in seen or len(seen) >= 256:
                        raise MCPFailure("duplicate or excessive MCP tools")
                    seen.add(tool.name)
                    if tool.name not in self._config.tools:
                        continue
                    schema, losses = lower_schema(tool.input_schema)
                    # The SDK validates structured results. External references
                    # are forbidden so that validation cannot fetch network data.
                    if tool.output_schema is not None:
                        _check_output_schema(tool.output_schema)
                    definitions.append(
                        ToolDefinition(
                            name=tool.name,
                            description=tool.description
                            or "Operator-selected MCP tool",
                            input_schema=schema,
                        )
                    )
                    self._schemas[tool.name] = tool.input_schema
                    self._losses[tool.name] = losses
                cursor = result.next_cursor
                if cursor is None:
                    break
                if cursor in cursors:
                    raise MCPFailure("MCP catalog repeats a cursor")
                cursors.add(cursor)
            else:
                raise MCPFailure("MCP catalog exceeds the page limit")
        if set(self._schemas) != set(self._config.tools):
            raise MCPFailure("required MCP tool is unavailable")
        self._definitions = tuple(sorted(definitions, key=lambda item: item.name))
        self._ready = True

    async def dispatch(self, call: ToolCallBlock) -> ToolResultBlock:
        async with self._lock:
            if not self._ready:
                raise MCPFailure("MCP session is unavailable")
            if call.name not in self._schemas:
                return _error(call, "tool is not allowed by operator configuration")
            if call.id in self._used_ids or len(self._used_ids) >= 128:
                return _error(call, "duplicate call ID or session call limit reached")
            definition = next(d for d in self._definitions if d.name == call.name)
            # Check both the original server schema and the stricter canonical
            # object shape. In particular, undeclared arguments never pass through.
            validator = Draft202012Validator(self._schemas[call.name])
            # typeshed's deprecated overload has an untyped instance parameter.
            valid = validator.is_valid(call.args)  # pyright: ignore[reportUnknownMemberType]
            if (
                len(canonical_bytes(call)) > self._config.max_argument_bytes
                or not valid
                or not _arguments_match(definition.input_schema, call.args)
            ):
                return _error(call, "invalid MCP tool arguments")
            self._used_ids.add(call.id)
            try:
                async with asyncio.timeout(self._config.timeout_seconds):
                    # Low-level API refuses input-required results; high-level
                    # Client.call_tool can repeat a call to satisfy elicitation.
                    result = await self._client.session.call_tool(call.name, call.args)
                converted = _convert_result(call, result)
                if len(canonical_bytes(converted)) > self._config.max_result_bytes:
                    raise MCPFailure("MCP result exceeds the byte limit")
                return converted
            except asyncio.CancelledError:
                self._ready = False
                raise
            except Exception:
                self._ready = False
                raise MCPFailure(
                    "MCP call failed; write outcome may be unknown; "
                    "inspect before retry"
                ) from None


def _arguments_match(schema: ToolSchema, value: JsonValue) -> bool:
    if schema.type == "object":
        return (
            isinstance(value, dict)
            and set(value) <= set(schema.properties)
            and all(
                _arguments_match(schema.properties[key], item)
                for key, item in value.items()
            )
        )
    if schema.type == "array":
        assert schema.items is not None
        item_schema = schema.items
        return isinstance(value, list) and all(
            _arguments_match(item_schema, item) for item in value
        )
    return True  # Primitive types and required fields checked by original schema.


def _check_output_schema(schema: dict[str, Any]) -> None:
    def walk(value: Any, depth: int = 0) -> None:
        if depth > 16:
            raise MCPFailure("MCP output schema is too deep")
        if isinstance(value, dict):
            if any(key in value for key in ("$ref", "$dynamicRef", "$recursiveRef")):
                raise MCPFailure("MCP output schema references are unsupported")
            for item in cast(dict[str, Any], value).values():
                walk(item, depth + 1)
        elif isinstance(value, list):
            for item in cast(list[Any], value):
                walk(item, depth + 1)

    walk(schema)
    Draft202012Validator.check_schema(schema)


def _error(call: ToolCallBlock, message: str) -> ToolResultBlock:
    return ToolResultBlock(
        call_id=call.id, name=call.name, content=message, is_error=True
    )


def _convert_result(call: ToolCallBlock, result: CallToolResult) -> ToolResultBlock:
    if result.is_error:
        return _error(call, "MCP tool reported an error; inspect writes before retry")
    if any(not isinstance(item, TextContent) for item in result.content):
        raise MCPFailure("MCP non-text content is unsupported")
    content = json.dumps(
        {
            "structured_content": result.structured_content,
            "text": [
                item.text for item in result.content if isinstance(item, TextContent)
            ],
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return ToolResultBlock(call_id=call.id, name=call.name, content=content)


@asynccontextmanager
async def connect_mcp(config: MCPConfig) -> AsyncGenerator[MCPDispatcher]:
    """Launch only the named server; release its process on exit or cancellation."""
    config = MCPConfig.model_validate_json(config.model_dump_json())
    parameters = config.parameters()
    dispatcher: MCPDispatcher | None = None
    body_error: BaseException | None = None
    try:
        with _redacted_sdk_logs(), open(os.devnull, "w") as stderr:
            async with Client(
                stdio_client(parameters, errlog=stderr),
                read_timeout_seconds=config.timeout_seconds,
                cache=None,
            ) as client:
                dispatcher = MCPDispatcher(client, config)
                await dispatcher.discover()
                try:
                    yield dispatcher
                except BaseException as error:
                    body_error = error
                    raise
    except Exception:
        if body_error is not None:
            raise body_error from None
        raise MCPFailure(
            "MCP session failed; inspect any submitted write before retry"
        ) from None
    finally:
        if dispatcher is not None:
            dispatcher.close()
