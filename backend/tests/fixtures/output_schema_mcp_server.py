"""A stdio MCP server with two tools: ``typed`` declares an ``outputSchema``
(and answers with ``structuredContent``); ``plain`` declares none.

Spawned by tests of the gateway's schema pass-through; shares nothing with
``fake_mcp_server.py`` so that fixture stays unchanged.
"""

from __future__ import annotations

import asyncio
from typing import Any

import mcp.types as mcp_types
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
from mcp.server.stdio import stdio_server

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "total": {"type": "integer", "minimum": 0},
        "note": {"type": ["string", "null"], "default": None},
    },
    "required": ["total"],
}

#: Includes a null and a nested null: the gateway must hand the result back untouched.
STRUCTURED: dict[str, Any] = {"total": 3, "note": None, "nested": {"a": None, "b": [None, 1]}}


async def _list(
    ctx: ServerRequestContext[Any], params: mcp_types.PaginatedRequestParams | None
) -> mcp_types.ListToolsResult:
    return mcp_types.ListToolsResult(
        tools=[
            mcp_types.Tool(
                name="typed",
                description="count things",
                inputSchema={"type": "object", "properties": {}},
                outputSchema=OUTPUT_SCHEMA,
            ),
            mcp_types.Tool(
                name="plain",
                description="say hello",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]
    )


async def _call(
    ctx: ServerRequestContext[Any], params: mcp_types.CallToolRequestParams
) -> mcp_types.CallToolResult:
    if params.name == "typed":
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="3")], structured_content=STRUCTURED
        )
    return mcp_types.CallToolResult(content=[mcp_types.TextContent(type="text", text="hello")])


async def _main() -> None:
    server: Server[Any] = Server("output-schema-server", on_list_tools=_list, on_call_tool=_call)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
