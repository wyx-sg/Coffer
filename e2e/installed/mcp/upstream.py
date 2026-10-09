"""A deterministic, local-only MCP upstream with a call ledger (run as a script).

``--transport stdio`` is what the target spawns for a stdio server.
``--transport http`` serves, on 127.0.0.1, the SDK's session-keeping
Streamable HTTP app at ``/mcp/`` — its back-channel lets the server ask its
client (sampling, roots) — and, on every other path, an echo receiver for a
custom HTTP tool. It writes ``{"port"}`` to ``--ready``.

Every call appends JSON lines to ``--ledger``: ``start`` and then ``done``,
``answered``, ``refused`` or ``exit``, each with this process's pid, so a test
counts how often the upstream really ran something and the run can check that
every child the target spawned is gone at the end. Values of ``QA_CANARY*``
environment variables are replaced by ``[CANARY]`` before anything is written.

It never reaches anything but its own client.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp import MCPError
from mcp.server import Server
from mcp.server.stdio import stdio_server

TOOLS = [
    "echo",
    "environment",
    "mutate",
    "sampling",
    "roots",
    "secret_stderr",
    "secret_stderr_split",
    "secret_stderr_exit",
]
state: dict[str, Any] = {"mutated": False}
args = argparse.Namespace()


def _mask(text: str) -> str:
    for key, value in os.environ.items():
        if key.startswith("QA_CANARY") and value:
            text = text.replace(value, "[CANARY]")
    return text


def record(event: str, **fields: Any) -> None:
    row = {"time": time.time(), "pid": os.getpid(), "tag": args.tag, "event": event, **fields}
    with open(args.ledger, "a") as out:
        out.write(_mask(json.dumps(row, default=str)) + "\n")


def _text(text: str, *, error: bool = False, structured: Any = None) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        is_error=error,
        structured_content=structured,
    )


async def list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
    names = [*TOOLS, "added"] if state["mutated"] else list(TOOLS)
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    return types.ListToolsResult(
        tools=[
            types.Tool(name=n, description=f"qa synthetic {args.tag} {n}", input_schema=schema)
            for n in names
        ]
    )


async def _ask_client(ctx: Any, name: str) -> types.CallToolResult:
    """Ask the client (sampling or roots) and return what it answered, in-band."""
    try:
        if name == "sampling":
            message = types.SamplingMessage(
                role="user", content=types.TextContent(type="text", text="qa synthetic sample")
            )
            result = await ctx.session.create_message(messages=[message], max_tokens=4)
            answer = getattr(result.content, "text", "")
        else:
            roots = await ctx.session.list_roots()
            answer = ",".join(str(r.uri) for r in roots.roots)
    except Exception as exc:
        record("refused", name=name, error=f"{type(exc).__name__}: {exc}")
        return _text(f"refused:{type(exc).__name__}:{exc}", error=True)
    record("answered", name=name, answer=answer)
    return _text(f"{name}:{answer}", structured={"tag": args.tag, "answer": answer})


async def _secret_stderr(name: str) -> None:
    value = os.environ.get("QA_CANARY_SECRET", "no-secret")
    if name == "secret_stderr":
        print("qa injected value=" + value, file=sys.stderr, flush=True)
    elif name == "secret_stderr_split":
        half = len(value) // 2
        sys.stderr.write("qa split value=" + value[:half])
        sys.stderr.flush()
        await asyncio.sleep(0.2)
        sys.stderr.write(value[half:] + "\n")
        sys.stderr.flush()
    else:
        sys.stderr.write("qa value before exit=" + value + "\n")
        sys.stderr.flush()
        record("exit", name=name)
        os._exit(3)


async def call(ctx: Any, params: Any) -> types.CallToolResult:
    name, a = params.name, params.arguments or {}
    record("start", name=name, arguments=a)
    if name not in [*TOOLS, "added"]:
        raise MCPError(-32602, "unknown fixture tool")
    if name in ("sampling", "roots"):
        return await _ask_client(ctx, name)
    if name.startswith("secret_stderr"):
        await _secret_stderr(name)
    if name == "mutate":
        state["mutated"] = True
        await ctx.session.send_tool_list_changed()
        await ctx.session.send_resource_list_changed()
        await ctx.session.send_prompt_list_changed()
    payload: dict[str, Any] = {"tag": args.tag, "name": name, "arguments": a, "pid": os.getpid()}
    if name == "environment":
        payload.update(
            cwd=os.getcwd(),
            env=os.environ.get("QA_ENV"),
            secret_present=bool(os.environ.get("QA_CANARY_SECRET")),
        )
    record("done", name=name, arguments=a)
    return _text(json.dumps(payload), structured=payload)


async def list_resources(ctx: Any, params: Any) -> types.ListResourcesResult:
    return types.ListResourcesResult(resources=[])


async def list_prompts(ctx: Any, params: Any) -> types.ListPromptsResult:
    return types.ListPromptsResult(prompts=[])


def server() -> Server[Any]:
    return Server(
        "qa-installed-upstream",
        on_list_tools=list_tools,
        on_call_tool=call,
        on_list_resources=list_resources,
        on_list_prompts=list_prompts,
    )


async def echo_receiver(request: Any) -> Any:
    """Records what a custom HTTP tool sent and answers it back."""
    from starlette.responses import JSONResponse

    body = (await request.body()).decode(errors="replace")
    raw = request.scope.get("raw_path")
    path = raw.decode("latin-1") if raw else str(request.url.path)
    record("http", method=request.method, path=path, query=request.url.query, body=body)
    return JSONResponse(
        {
            "tag": args.tag,
            "path": path,
            "query": request.url.query,
            "method": request.method,
            "env": request.headers.get("x-env"),
        }
    )


async def serve_http() -> None:
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    sdk_app = server().streamable_http_app(streamable_http_path="/", stateless_http=False)

    async def lifespan(app: Any) -> Any:
        async with sdk_app.router.lifespan_context(sdk_app):
            yield

    app = Starlette(
        routes=[
            Mount("/mcp", app=sdk_app),
            Route("/{path:path}", echo_receiver, methods=["GET", "POST"]),
        ],
        lifespan=lifespan,
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    record("process-start", transport="http", port=port)
    Path(args.ready).write_text(json.dumps({"port": port}))
    await uvicorn.Server(uvicorn.Config(app, log_level="warning")).serve(sockets=[sock])


async def main() -> None:
    record("process-start", transport=args.transport, cwd=os.getcwd())
    if args.transport == "http":
        await serve_http()
        return
    print("qa stderr plain line", file=sys.stderr, flush=True)
    s = server()
    async with stdio_server() as (r, w):
        await s.run(r, w, s.create_initialization_options())
    record("process-stop")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--transport", default="stdio", choices=["stdio", "http"])
    p.add_argument("--tag", required=True)
    p.add_argument("--ledger", required=True)
    p.add_argument("--ready")
    args = p.parse_args()
    asyncio.run(main())
