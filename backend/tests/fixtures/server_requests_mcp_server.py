"""An MCP server whose tools ask the CLIENT something: ``sample`` sends
``sampling/createMessage`` and ``roots`` sends ``roots/list``; each tool returns
what the client answered, so a test sees the round trip end to end.

``--transport stdio`` (default) or ``--transport http --ready <file>``: the HTTP
server is the SDK's stateful streamable HTTP app, which has the back-channel a
server-initiated request needs (a stateless one cannot ask the client anything).
It binds 127.0.0.1 on a free port and writes the port to ``--ready``.
"""

from __future__ import annotations

import argparse
import asyncio
import socket
from pathlib import Path
from typing import Any

import mcp.types as mcp_types
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
from mcp.server.stdio import stdio_server


async def _list(
    ctx: ServerRequestContext[Any], params: mcp_types.PaginatedRequestParams | None
) -> mcp_types.ListToolsResult:
    schema = {"type": "object", "properties": {}}
    return mcp_types.ListToolsResult(
        tools=[
            mcp_types.Tool(name="sample", description="ask the client's model", inputSchema=schema),
            mcp_types.Tool(name="roots", description="ask the client's roots", inputSchema=schema),
        ]
    )


def _text(text: str, *, error: bool = False) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)], is_error=error
    )


async def _call(
    ctx: ServerRequestContext[Any], params: mcp_types.CallToolRequestParams
) -> mcp_types.CallToolResult:
    try:
        if params.name == "sample":
            result = await ctx.session.create_message(
                messages=[
                    mcp_types.SamplingMessage(
                        role="user", content=mcp_types.TextContent(type="text", text="hello?")
                    )
                ],
                max_tokens=8,
            )
            content = result.content
            return _text("sampled:" + getattr(content, "text", ""))
        roots = await ctx.session.list_roots()
        return _text("roots:" + ",".join(str(r.uri) for r in roots.roots))
    except Exception as e:  # the client refused: say so in-band
        return _text(f"refused:{type(e).__name__}:{e}", error=True)


def _server() -> Server[Any]:
    return Server("server-requests", on_list_tools=_list, on_call_tool=_call)


async def _stdio() -> None:
    server = _server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


async def _http(ready: Path) -> None:
    import uvicorn

    app = _server().streamable_http_app(streamable_http_path="/mcp", stateless_http=False)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    ready.write_text(str(sock.getsockname()[1]))
    await uvicorn.Server(uvicorn.Config(app, log_level="warning")).serve(sockets=[sock])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--ready", type=Path)
    args = parser.parse_args()
    asyncio.run(_stdio() if args.transport == "stdio" else _http(args.ready))
