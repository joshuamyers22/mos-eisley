"""Explicit MCP discovery and one-shot calls without a provider invocation."""

import argparse
import asyncio
import json
import sys
import webbrowser
from pathlib import Path
from typing import cast

from mos_eisley.core.protocol import ToolCallBlock
from mos_eisley.run.files import read_bounded
from mos_eisley.tools.mcp import MCPConfig, MCPFailure, connect_mcp, redacted_sdk_logs
from mos_eisley.tools.mcp_oauth import OAuthController
from mos_eisley.tools.mcp_oauth_store import OAuthFailure


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
        if args.command in {"mcp-login", "mcp-logout"}:
            if config.http is None or config.http.oauth is None:
                raise OAuthFailure("OAuth configuration is required")
            controller = OAuthController(config.http)
            with redacted_sdk_logs():
                if args.command == "mcp-logout":
                    print(
                        json.dumps({"type": "mcp.logout", **await controller.logout()})
                    )
                else:

                    async def show_url(url: str) -> None:
                        print(
                            "Open this URL to authorize the configured scopes:\n" + url,
                            file=sys.stderr,
                            flush=True,
                        )
                        if args.open_browser:
                            await asyncio.to_thread(webbrowser.open, url)

                    await controller.login(show_url)
                    print(json.dumps({"type": "mcp.login", "authenticated": True}))
            return 0
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
    except (MCPFailure, OAuthFailure, TimeoutError):
        print(
            "mos-eisley: MCP connection or call failed; check configuration and "
            "credentials. Inspect any submitted write before retrying.",
            file=sys.stderr,
        )
        return 2
