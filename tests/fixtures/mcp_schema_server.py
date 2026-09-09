"""Standalone stdio schema fixture."""

from fixtures.mcp_schema_tools import add_schema_tools
from mcp.server import MCPServer

server = MCPServer("schema-fixture")
add_schema_tools(server)
if __name__ == "__main__":
    server.run()
