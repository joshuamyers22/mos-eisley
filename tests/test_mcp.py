"""MCP capability, schema, lifecycle, and canonical-agent boundary tests."""

import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, cast
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from mcp import Client
from mcp.types import CallToolResult, ImageContent, ListToolsResult, TextContent, Tool

from mos_eisley.cli import main
from mos_eisley.core.agent import run_agent
from mos_eisley.core.protocol import (
    ModelRequest,
    ModelResponse,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
    Turn,
    Usage,
)
from mos_eisley.core.registry import fixture_registry
from mos_eisley.demo_agent import agent_demo_inputs
from mos_eisley.tools.mcp import MCPConfig, MCPDispatcher, MCPFailure, connect_mcp
from mos_eisley.tools.mcp_schema import lower_schema

FIXTURE = Path(__file__).parent / "fixtures" / "mcp_server.py"


def config(**updates: Any) -> MCPConfig:
    return MCPConfig.model_validate(
        {
            "command": sys.executable,
            "args": (str(FIXTURE),),
            "cwd": str(FIXTURE.parent),
            "tools": {"echo": "read"},
            **updates,
        }
    )


def call(name: str = "echo", **args: Any) -> ToolCallBlock:
    return ToolCallBlock(id="test-call", name=name, args=args)


class MCPConfigTests(TestCase):
    def test_launch_policy(self) -> None:
        for updates in (
            {"command": "python"},
            {"cwd": "."},
            {"env": ("A", "A")},
            {"env": ("BAD=KEY",)},
            {"args": ("\0",)},
            {"tools": {"write": "write"}},
            {"unknown": True},
        ):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                config(**updates)
        self.assertTrue(
            config(tools={"write": "write"}, allow_writes=True).allow_writes
        )
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(MCPFailure):
            config(env=("MCP_MISSING",)).parameters()

    def test_schema_lowering_reports_every_change(self) -> None:
        schema, changes = lower_schema(
            {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["a", "b"],
                        "default": "a",
                        "title": "Mode",
                    },
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["paths"],
            }
        )
        self.assertEqual(schema.required, ("paths",))
        self.assertEqual(len(changes), 3)
        for value in (
            {"type": "object", "additionalProperties": True},
            {"type": "string", "pattern": ".*"},
            {"$ref": "https://example.invalid/schema"},
            {"type": ["string", "null"]},
            {"anyOf": [{"type": "string"}, {"type": "number"}]},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                lower_schema(value)

    def test_cli_discovery_call_and_redacted_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cfg = Path(directory) / "mcp.json"
            arg = Path(directory) / "call.json"
            cfg.write_text(config().model_dump_json())
            arg.write_text(call(value="synthetic").model_dump_json())
            for command in (
                ["mcp-list", "--config", str(cfg)],
                [
                    "mcp-call",
                    "--config",
                    str(cfg),
                    "--call",
                    str(arg),
                ],
            ):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(command), 0)
                json.loads(output.getvalue())
            cfg.write_text(config(tools={"failure": "read"}).model_dump_json())
            arg.write_text(call("failure").model_dump_json())
            output, errors = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                self.assertEqual(
                    main(["mcp-call", "--config", str(cfg), "--call", str(arg)]), 2
                )
            self.assertNotIn("MCP_TEST_SECRET", output.getvalue() + errors.getvalue())


class MCPStdioTests(IsolatedAsyncioTestCase):
    async def test_startup_timeout_reaps_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pid_file = Path(temporary) / "pid"
            cfg = config(
                args=(
                    "-c",
                    "import os,pathlib,sys,time; "
                    "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); "
                    "time.sleep(30)",
                    str(pid_file),
                ),
                timeout_seconds=1,
            )
            with self.assertRaises(MCPFailure):
                async with connect_mcp(cfg):
                    self.fail("nonresponsive process must not connect")
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid_file.read_text()), 0)

    async def test_malformed_wire_diagnostics_are_redacted(self) -> None:
        cfg = config(
            args=(
                "-c",
                "import time; print('MCP_PRIVATE_WIRE_VALUE',flush=True); "
                "time.sleep(2)",
            ),
            timeout_seconds=1,
        )
        with (
            self.assertLogs("mcp", level="ERROR") as logs,
            self.assertRaises(MCPFailure),
        ):
            async with connect_mcp(cfg):
                self.fail("malformed server must not connect")
        self.assertNotIn("MCP_PRIVATE_WIRE_VALUE", " ".join(logs.output))
        self.assertIn("redacted", " ".join(logs.output))

    async def test_caller_failure_is_preserved(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "caller failure"):
            async with connect_mcp(config()):
                raise RuntimeError("caller failure")

    async def test_mutated_config_is_revalidated_before_launch(self) -> None:
        cfg = config()
        cfg.tools["write_parquet"] = "write"
        with self.assertRaises(ValueError):
            async with connect_mcp(cfg):
                self.fail("unvalidated write grant must not launch")

    async def test_real_stdio_and_argument_checks(self) -> None:
        async with connect_mcp(config()) as dispatcher:
            self.assertEqual([d.name for d in dispatcher.definitions], ["echo"])
            for invalid in (call("unknown"), call(value=1), call(extra="bad")):
                self.assertTrue((await dispatcher.dispatch(invalid)).is_error)
            result = await dispatcher.dispatch(call())
            self.assertEqual(
                json.loads(result.content)["structured_content"], {"value": "default"}
            )
            self.assertTrue((await dispatcher.dispatch(call())).is_error)
        with self.assertRaises(MCPFailure):
            await dispatcher.dispatch(call())

    async def test_only_allowlisted_environment_values_cross(self) -> None:
        with patch.dict(
            os.environ,
            {"MCP_TEST_ALLOWED": "yes", "MCP_TEST_SECRET": "hidden", "HOME": "/secret"},
        ):
            async with connect_mcp(
                config(tools={"environment": "read"}, env=("MCP_TEST_ALLOWED",))
            ) as dispatcher:
                result = await dispatcher.dispatch(call("environment"))
        self.assertEqual(
            json.loads(result.content)["structured_content"],
            {
                "MCP_TEST_ALLOWED": "yes",
                "MCP_TEST_SECRET": None,
                "HOME": "",
            },
        )

    async def test_missing_server_or_tool_fails_closed(self) -> None:
        for cfg in (
            config(command="/missing/mcp-server"),
            config(tools={"absent": "read"}),
        ):
            with self.subTest(cfg=cfg), self.assertRaises(MCPFailure):
                async with connect_mcp(cfg):
                    self.fail("unavailable server must not yield")

    async def test_deadline_and_oversized_result_break_session(self) -> None:
        for name in ("slow", "oversized"):
            async with connect_mcp(
                config(tools={name: "read"}, timeout_seconds=1)
            ) as dispatcher:
                with self.assertRaises(MCPFailure):
                    await dispatcher.dispatch(call(name))
                with self.assertRaises(MCPFailure):
                    await dispatcher.dispatch(
                        call(name).model_copy(update={"id": "next"})
                    )

    async def test_cancellation_propagates_and_breaks_session(self) -> None:
        async with connect_mcp(config(tools={"slow": "read"})) as dispatcher:
            task = asyncio.create_task(dispatcher.dispatch(call("slow")))
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            with self.assertRaises(MCPFailure):
                await dispatcher.dispatch(call("slow"))

    async def test_canonical_agent_uses_mcp_dispatcher(self) -> None:
        class FixtureModel:
            async def complete(self, request: ModelRequest) -> ModelResponse:
                if len(request.turns) == 1:
                    blocks = (call(value="agent-fixture"),)
                    return ModelResponse(
                        turn=Turn(role="assistant", blocks=blocks),
                        stop_reason="tool_use",
                        usage=Usage(input=1, output=1),
                    )
                result = request.turns[-1].blocks[0]
                assert isinstance(result, ToolResultBlock)
                assert "agent-fixture" in result.content
                return ModelResponse(
                    turn=Turn(role="assistant", blocks=(TextBlock(text="verified"),)),
                    stop_reason="end_turn",
                    usage=Usage(input=1, output=1),
                )

        agent_config, _, _ = agent_demo_inputs()
        async with connect_mcp(config()) as dispatcher:
            result = await run_agent(
                agent_config, fixture_registry(), FixtureModel(), dispatcher
            )
        self.assertEqual((result.final_text, result.usage.tools), ("verified", 1))


class FakeClient:
    def __init__(
        self, pages: list[ListToolsResult], result: CallToolResult | None = None
    ) -> None:
        self.pages = pages
        self.result = result or CallToolResult(
            content=[TextContent(type="text", text="ok")]
        )
        self.session = self
        self.calls = 0

    async def list_tools(self, **kwargs: Any) -> ListToolsResult:
        return self.pages.pop(0)

    async def call_tool(self, name: str, args: Any) -> CallToolResult:
        self.calls += 1
        return self.result


class MCPCatalogTests(IsolatedAsyncioTestCase):
    async def test_reject_duplicate_missing_unsafe_schema_and_repeated_pages(
        self,
    ) -> None:
        echo = Tool(name="echo", input_schema={"type": "object"})
        variants = (
            [ListToolsResult(tools=[echo, echo])],
            [ListToolsResult(tools=[])],
            [
                ListToolsResult(
                    tools=[
                        echo.model_copy(
                            update={
                                "output_schema": {
                                    "$ref": "https://example.invalid/secret"
                                }
                            }
                        )
                    ]
                )
            ],
            [
                ListToolsResult(tools=[], next_cursor="repeat"),
                ListToolsResult(tools=[], next_cursor="repeat"),
            ],
        )
        for pages in variants:
            dispatcher = MCPDispatcher(cast(Client, FakeClient(pages)), config())
            with self.assertRaises(ValueError):
                await dispatcher.discover()
            with self.assertRaises(MCPFailure):
                await dispatcher.dispatch(call())

    async def test_pagination_filters_tools_and_ignores_annotations(self) -> None:
        from mcp.types import ToolAnnotations

        client = FakeClient(
            [
                ListToolsResult(
                    tools=[
                        Tool(
                            name="unapproved_write",
                            input_schema={"type": "object"},
                            annotations=ToolAnnotations(read_only_hint=True),
                        )
                    ],
                    next_cursor="two",
                ),
                ListToolsResult(
                    tools=[Tool(name="echo", input_schema={"type": "object"})]
                ),
            ]
        )
        dispatcher = MCPDispatcher(cast(Client, client), config())
        await dispatcher.discover()
        self.assertTrue((await dispatcher.dispatch(call("unapproved_write"))).is_error)
        self.assertEqual(client.calls, 0)
        self.assertFalse((await dispatcher.dispatch(call())).is_error)

    async def test_nontext_result_is_rejected_without_retry(self) -> None:
        client = FakeClient(
            [
                ListToolsResult(
                    tools=[Tool(name="echo", input_schema={"type": "object"})]
                )
            ],
            CallToolResult(
                content=[ImageContent(type="image", data="AA==", mime_type="image/png")]
            ),
        )
        dispatcher = MCPDispatcher(cast(Client, client), config())
        await dispatcher.discover()
        with self.assertRaises(MCPFailure):
            await dispatcher.dispatch(call())
        self.assertEqual(client.calls, 1)
