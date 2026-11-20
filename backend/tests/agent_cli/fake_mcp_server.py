"""A one-tool stdio MCP server standing in for Coffer's shim in the agent CLI
smoke checks: the agent connects to it the way it would connect to the shim."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

server = FastMCP("coffer")


@server.tool()
def coffer_ping() -> str:
    """Answer pong."""
    return "pong"


if __name__ == "__main__":
    server.run()
