"""An MCP server that writes every call's fate to a ledger file.

Tools:

* ``echo`` — ``text`` must be a string, so a wrong type is the SDK's own
  ``-32602``; answers ``json.dumps(arguments)`` and, as structured content,
  ``{"tag", "arguments"}``, so a test sees which server answered.
* ``slow`` — sleeps ``delay`` seconds.
* ``rpc_error`` — answers with JSON-RPC ``-32602`` itself (text
  :data:`RPC_ERROR_TEXT`, which a gateway must not relay).
* ``business_error`` — an in-band ``isError`` result whose text is
  :data:`BUSINESS_ERROR_TEXT`.
* ``image`` — one PNG image item (:data:`IMAGE_DATA`) and the tag as text.
* ``environment`` — the process's working directory, ``LEDGER_ENV`` and
  whether ``LEDGER_SECRET`` is set (never its value).
* ``mutate`` — adds a tool ``added`` and sends tools, resources and prompts
  ``list_changed``.
* ``tool_000`` … — ``--extra-tools N`` more echo-like tools, for a catalogue
  larger than a search's cap.

One resource ``ledger://same`` (its text is the tag) and one prompt ``same``
(argument ``text``; answers ``<tag>:<text>``).

Each call appends ``start``, then ``done`` or ``cancelled``, as JSON lines to
``--ledger`` with the tool and this process's pid, so a test counts how often
the upstream really ran something, whether a cancellation reached it, and
which child process ran it.

``--paged`` splits ``tools/list`` into two pages. ``--mode`` makes a stdio
server misbehave at start: ``exit`` (exits at once), ``pollute`` (one
non-JSON line on stdout before speaking MCP), ``invalid-json`` (one broken
JSON line first). ``--transport http --ready <file>`` serves the same server
over stateless Streamable HTTP at ``/mcp`` on a free 127.0.0.1 port and writes
the port to the file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

import mcp.types as mcp_types
from mcp import MCPError
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
from mcp.server.stdio import stdio_server

RPC_ERROR_TEXT = "rpc_error always refuses"
BUSINESS_ERROR_TEXT = "ledger business rejection"
IMAGE_DATA = "iVBORw0KGgo="

_args = argparse.Namespace()
_state: dict[str, bool] = {"mutated": False}


def _record(event: str, name: str) -> None:
    with Path(_args.ledger).open("a") as out:
        out.write(json.dumps({"event": event, "tool": name, "pid": os.getpid()}) + "\n")


def _names() -> list[str]:
    names = ["echo", "slow", "rpc_error", "business_error", "image", "environment", "mutate"]
    names += [f"tool_{i:03d}" for i in range(_args.extra_tools)]
    return [*names, "added"] if _state["mutated"] else names


async def _list(
    ctx: ServerRequestContext[Any], params: mcp_types.PaginatedRequestParams | None
) -> mcp_types.ListToolsResult:
    def tool(name: str) -> mcp_types.Tool:
        props: dict[str, Any] = {"text": {"type": "string"}, "delay": {"type": "number"}}
        required = ["text"] if name == "echo" else []
        schema = {"type": "object", "properties": props, "required": required}
        return mcp_types.Tool(name=name, description=f"ledger {name}", inputSchema=schema)

    names, cursor = _names(), params.cursor if params else None
    next_cursor = None
    if _args.paged:
        names, next_cursor = (names[:2], "page-2") if not cursor else (names[2:], None)
    return mcp_types.ListToolsResult(tools=[tool(n) for n in names], nextCursor=next_cursor)


def _text(text: str, *, error: bool = False, structured: Any = None) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)],
        isError=error,
        structuredContent=structured,
    )


async def _call(
    ctx: ServerRequestContext[Any], params: mcp_types.CallToolRequestParams
) -> mcp_types.CallToolResult:
    name, args = params.name, params.arguments or {}
    if name not in _names():
        raise MCPError(mcp_types.INVALID_PARAMS, "unknown ledger tool")
    if name == "echo" and not isinstance(args.get("text"), str):
        raise MCPError(mcp_types.INVALID_PARAMS, "text must be a string")
    if name == "rpc_error":
        raise MCPError(mcp_types.INVALID_PARAMS, RPC_ERROR_TEXT)
    _record("start", name)
    try:
        if name == "slow":
            await asyncio.sleep(float(args.get("delay", 1)))
    except asyncio.CancelledError:
        _record("cancelled", name)
        raise
    if name == "mutate":
        _state["mutated"] = True
        await ctx.session.send_tool_list_changed()
        await ctx.session.send_resource_list_changed()
        await ctx.session.send_prompt_list_changed()
    _record("done", name)
    if name == "business_error":
        return _text(BUSINESS_ERROR_TEXT, error=True)
    if name == "image":
        return mcp_types.CallToolResult(
            content=[
                mcp_types.ImageContent(type="image", data=IMAGE_DATA, mimeType="image/png"),
                mcp_types.TextContent(type="text", text=_args.tag),
            ]
        )
    if name == "environment":
        payload = {
            "tag": _args.tag,
            "cwd": os.getcwd(),
            "env": os.environ.get("LEDGER_ENV"),
            "secret_present": bool(os.environ.get("LEDGER_SECRET")),
        }
        return _text(json.dumps(payload), structured=payload)
    return _text(json.dumps(args), structured={"tag": _args.tag, "arguments": args})


async def _list_resources(ctx: ServerRequestContext[Any], params: Any) -> Any:
    return mcp_types.ListResourcesResult(
        resources=[mcp_types.Resource(uri="ledger://same", name="same", mimeType="text/plain")]
    )


async def _read(ctx: ServerRequestContext[Any], params: Any) -> Any:
    if str(params.uri) != "ledger://same":
        raise MCPError(-32002, "no such ledger resource")
    return mcp_types.ReadResourceResult(
        contents=[
            mcp_types.TextResourceContents(uri=params.uri, text=_args.tag, mimeType="text/plain")
        ]
    )


async def _list_prompts(ctx: ServerRequestContext[Any], params: Any) -> Any:
    argument = mcp_types.PromptArgument(name="text", required=True)
    return mcp_types.ListPromptsResult(
        prompts=[mcp_types.Prompt(name="same", arguments=[argument])]
    )


async def _prompt(ctx: ServerRequestContext[Any], params: Any) -> Any:
    text = (params.arguments or {}).get("text")
    if params.name != "same" or not text:
        raise MCPError(mcp_types.INVALID_PARAMS, "the ledger prompt needs text")
    message = mcp_types.PromptMessage(
        role="user", content=mcp_types.TextContent(type="text", text=f"{_args.tag}:{text}")
    )
    return mcp_types.GetPromptResult(messages=[message])


def _server() -> Server[Any]:
    return Server(
        "ledger",
        on_list_tools=_list,
        on_call_tool=_call,
        on_list_resources=_list_resources,
        on_read_resource=_read,
        on_list_prompts=_list_prompts,
        on_get_prompt=_prompt,
    )


async def _stdio() -> None:
    if _args.mode == "exit":
        return
    if _args.mode == "pollute":
        print("ledger: not a JSON-RPC line", flush=True)
    if _args.mode == "invalid-json":
        print("{ledger-invalid", flush=True)
    server = _server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


async def _http(ready: Path) -> None:
    import uvicorn

    app = _server().streamable_http_app(streamable_http_path="/mcp", stateless_http=True)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    ready.write_text(str(sock.getsockname()[1]))
    await uvicorn.Server(uvicorn.Config(app, log_level="warning")).serve(sockets=[sock])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--tag", default="ledger")
    parser.add_argument("--extra-tools", type=int, default=0)
    parser.add_argument("--paged", action="store_true")
    parser.add_argument("--mode", choices=["basic", "exit", "pollute", "invalid-json"])
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--ready", type=Path)
    _args = parser.parse_args()
    print("ledger: started", file=sys.stderr, flush=True)
    asyncio.run(_stdio() if _args.transport == "stdio" else _http(_args.ready))
