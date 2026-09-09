"""Explicit MCP discovery and one-shot calls without a provider invocation."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import cast

from mos_eisley.core.protocol import ToolCallBlock
from mos_eisley.run.files import read_bounded
from mos_eisley.tools.mcp import MCPConfig, MCPFailure, connect_mcp


def run_mcp_command(args: argparse.Namespace) -> int:
    config = MCPConfig.model_validate_json(read_bounded(cast(Path, args.config), 65536))
    call = None
    if args.command == "mcp-call":
        call = ToolCallBlock.model_validate_json(
            read_bounded(cast(Path, args.call), config.max_argument_bytes)
        )
        if call.name not in config.tools:
            raise ValueError("tool is not allowed by operator configuration")

    async def execute() -> int:
        async with connect_mcp(config) as dispatcher:
            if call is None:
                print(
                    json.dumps(
                        {
                            "type": "mcp.ready",
                            "tools": [
                                tool.model_dump(mode="json")
                                for tool in dispatcher.definitions
                            ],
                            "capabilities": config.tools,
                            "schema_changes": dispatcher.schema_changes,
                        }
                    )
                )
                return 0
            result = await dispatcher.dispatch(call)
            print(result.model_dump_json())
            return 2 if result.is_error else 0

    try:
        return asyncio.run(execute())
    except MCPFailure:
        print(
            "mos-eisley: MCP connection or call failed; check configuration and "
            "credentials. Inspect any submitted write before retrying.",
            file=sys.stderr,
        )
        return 2
