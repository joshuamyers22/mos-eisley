"""Explicit operator-configured MCP tools for the canonical agent port."""

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator, Generator
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import httpx2
from mcp import Client
from mcp.client.stdio import (
    DEFAULT_INHERITED_ENV_VARS,
    StdioServerParameters,
    stdio_client,
)
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent
from pydantic import Field, JsonValue, model_validator

from mos_eisley.core.models import Contract, Identifier, canonical_bytes
from mos_eisley.core.protocol import (
    ToolCallBlock,
    ToolDefinition,
    ToolResultBlock,
    ToolSchema,
)
from mos_eisley.tools.mcp_http import MCPHTTPClient, MCPHTTPSettings, MCPHTTPTransport
from mos_eisley.tools.mcp_schema import (
    PreparedSchema,
    compile_schema,
    prepare_schema,
    valid_instance,
)


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
def redacted_sdk_logs() -> Generator[None]:
    # The locked SDK's stdio parser logs Pydantic exceptions, including rejected
    # wire values, before our boundary catches them. Filters must attach to the
    # emitting loggers: an ancestor logger's filter does not cover propagation.
    loggers = [
        logging.getLogger(name)
        for name in tuple(logging.Logger.manager.loggerDict)
        if name.split(".")[0] in {"mcp", "httpx2", "httpcore2"}
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
    transport: Literal["stdio", "streamable_http"] = "stdio"
    schema_mode: Literal["auto", "json_object"] = "auto"
    command: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    args: Annotated[tuple[str, ...], Field(max_length=64)] = ()
    cwd: Annotated[str, Field(min_length=1, max_length=4096)] | None = None
    http: MCPHTTPSettings | None = None
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
        if not self.allow_writes and "write" in self.tools.values():
            raise ValueError("write tools require allow_writes in operator config")
        if self.transport == "streamable_http":
            if (
                self.http is None
                or self.command is not None
                or self.cwd is not None
                or self.args
                or self.env
            ):
                raise ValueError("HTTP requires http settings and forbids stdio fields")
            return self
        if self.http is not None or self.command is None or self.cwd is None:
            raise ValueError("stdio requires command/cwd and forbids HTTP settings")
        if not Path(self.command).is_absolute() or not Path(self.cwd).is_absolute():
            raise ValueError("MCP command and cwd must be absolute")
        if any("\0" in value or len(value) > 8192 for value in self.args):
            raise ValueError("invalid MCP launch arguments")
        if len(set(self.env)) != len(self.env) or any(
            not key.isascii() or not key.isidentifier() for key in self.env
        ):
            raise ValueError("invalid environment allowlist")
        return self

    def parameters(self) -> StdioServerParameters:
        if self.transport != "stdio" or self.command is None:
            raise MCPFailure("stdio parameters requested for HTTP configuration")
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
        self._prepared: dict[str, PreparedSchema] = {}
        self._outputs: dict[str, dict[str, Any]] = {}
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

    @property
    def argument_encodings(self) -> dict[str, str]:
        return {name: item.encoding for name, item in self._prepared.items()}

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
                    prepared = prepare_schema(
                        tool.input_schema,
                        force_wrapper=self._config.schema_mode == "json_object",
                    )
                    # The SDK validates structured results. External references
                    # are forbidden so that validation cannot fetch network data.
                    if tool.output_schema is not None:
                        self._outputs[tool.name], _ = compile_schema(tool.output_schema)
                    definitions.append(
                        ToolDefinition(
                            name=tool.name,
                            description=(
                                (tool.description or "Operator-selected MCP tool")
                                + (
                                    "\n" + prepared.instructions
                                    if prepared.instructions
                                    else ""
                                )
                            ),
                            input_schema=prepared.schema,
                        )
                    )
                    self._schemas[tool.name] = prepared.validation
                    self._prepared[tool.name] = prepared
                    self._losses[tool.name] = prepared.changes
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
            if len(
                canonical_bytes(call)
            ) > self._config.max_argument_bytes or not _arguments_match(
                definition.input_schema, call.args
            ):
                return _error(call, "invalid MCP tool arguments")
            try:
                arguments = self._prepared[call.name].arguments(call.args)
            except Exception:
                return _error(call, "invalid MCP tool arguments")
            self._used_ids.add(call.id)
            try:
                async with asyncio.timeout(self._config.timeout_seconds):
                    # Low-level API refuses input-required results; high-level
                    # Client.call_tool can repeat a call to satisfy elicitation.
                    result = await self._client.session.call_tool(call.name, arguments)
                if (
                    not result.is_error
                    and call.name in self._outputs
                    and (
                        result.structured_content is None
                        or not valid_instance(
                            self._outputs[call.name], result.structured_content
                        )
                    )
                ):
                    raise MCPFailure("MCP structured output violates its schema")
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
    """Connect only to the selected server and release resources on exit."""
    config = MCPConfig.model_validate_json(config.model_dump_json())
    dispatcher: MCPDispatcher | None = None
    body_error: BaseException | None = None
    try:
        with redacted_sdk_logs(), open(os.devnull, "w") as stderr:
            async with AsyncExitStack() as stack:
                if config.http is not None:
                    from mos_eisley.tools.mcp_oauth import OAuthController

                    oauth = (
                        OAuthController(config.http)
                        if config.http.authentication == "oauth"
                        else None
                    )
                    http_client = await stack.enter_async_context(
                        MCPHTTPClient(
                            transport=MCPHTTPTransport(
                                config.http,
                                token_provider=oauth.access_token if oauth else None,
                                invalidate=oauth.invalidate if oauth else None,
                            ),
                            timeout=httpx2.Timeout(config.timeout_seconds),
                            trust_env=False,
                            follow_redirects=False,
                        )
                    )
                    transport = streamable_http_client(
                        config.http.url, http_client=http_client
                    )
                else:
                    transport = stdio_client(config.parameters(), errlog=stderr)
                async with (
                    asyncio.timeout(config.timeout_seconds) as startup,
                    Client(
                        transport,
                        read_timeout_seconds=config.timeout_seconds,
                        cache=None,
                    ) as client,
                ):
                    if config.http is not None and client.protocol_version not in {
                        "2026-07-28",
                        "2025-11-25",
                        "2025-06-18",
                    }:
                        raise MCPFailure("unsupported remote MCP protocol version")
                    dispatcher = MCPDispatcher(client, config)
                    await dispatcher.discover()
                    startup.reschedule(None)
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
