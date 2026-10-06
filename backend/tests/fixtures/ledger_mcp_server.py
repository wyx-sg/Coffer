"""A stdio MCP server that writes every call's fate to a ledger file.

Tools: ``echo`` (``text`` must be a string, so a wrong type is the SDK's own
``-32602``), ``slow`` (sleeps ``delay`` seconds), ``rpc_error`` (answers with
JSON-RPC ``-32602`` itself). Each call appends ``start``, then ``done`` or
``cancelled``, as JSON lines to ``--ledger``, so a test counts how often the
upstream really ran something and whether a cancellation reached it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import mcp.types as mcp_types
from mcp import MCPError
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
from mcp.server.stdio import stdio_server

_args = argparse.Namespace()


def _record(event: str, name: str) -> None:
    with Path(_args.ledger).open("a") as out:
        out.write(json.dumps({"event": event, "tool": name}) + "\n")


async def _list(
    ctx: ServerRequestContext[Any], params: mcp_types.PaginatedRequestParams | None
) -> mcp_types.ListToolsResult:
    def tool(name: str, props: dict[str, Any], required: list[str]) -> mcp_types.Tool:
        schema = {"type": "object", "properties": props, "required": required}
        return mcp_types.Tool(name=name, description=f"ledger {name}", inputSchema=schema)

    return mcp_types.ListToolsResult(
        tools=[
            tool("echo", {"text": {"type": "string"}}, ["text"]),
            tool("slow", {"delay": {"type": "number"}}, []),
            tool("rpc_error", {}, []),
        ]
    )


async def _call(
    ctx: ServerRequestContext[Any], params: mcp_types.CallToolRequestParams
) -> mcp_types.CallToolResult:
    name, args = params.name, params.arguments or {}
    if name == "echo" and not isinstance(args.get("text"), str):
        raise MCPError(mcp_types.INVALID_PARAMS, "text must be a string")
    if name == "rpc_error":
        raise MCPError(mcp_types.INVALID_PARAMS, "rpc_error always refuses")
    _record("start", name)
    try:
        if name == "slow":
            await asyncio.sleep(float(args.get("delay", 1)))
    except asyncio.CancelledError:
        _record("cancelled", name)
        raise
    _record("done", name)
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=json.dumps(args))]
    )


async def _main() -> None:
    server: Server[Any] = Server("ledger", on_list_tools=_list, on_call_tool=_call)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True)
    _args = parser.parse_args()
    asyncio.run(_main())
