"""Synthetic subprocess used by MCP client tests; no production sources."""

import asyncio
import os
from typing import Any

from mcp.server import MCPServer

server = MCPServer("fixture")


@server.tool()
def echo(value: str = "default") -> dict[str, str]:
    return {"value": value}


@server.tool()
def environment() -> dict[str, str | None]:
    return {
        key: os.environ.get(key)
        for key in ("MCP_TEST_ALLOWED", "MCP_TEST_SECRET", "HOME")
    }


@server.tool()
async def slow() -> str:
    await asyncio.sleep(10)
    return "late"


@server.tool()
def oversized() -> str:
    return "x" * 64001


@server.tool()
def failure() -> Any:
    raise ValueError("MCP_TEST_SECRET must never reach CLI diagnostics")


if __name__ == "__main__":
    server.run()
