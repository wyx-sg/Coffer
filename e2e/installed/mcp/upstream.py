"""A deterministic, local-only MCP upstream with a call ledger (run as a script).

``--transport stdio`` is what the target spawns for a stdio server.
``--transport http`` serves, on 127.0.0.1, the SDK's Streamable HTTP app at
``/mcp/`` — stateless by default, or with ``--stateful`` the session-keeping
app whose back-channel lets the server ask its client (sampling, roots) — and,
on every other path, an echo receiver for custom HTTP tools. It listens on two
ports and writes ``{"port", "other_port"}`` to ``--ready``: the second port is
"another origin" a redirect can point at, so a test can count requests that
reached it.

Every call appends JSON lines to ``--ledger``: ``start`` and then ``done``,
``cancelled`` or ``error``, each with this process's pid, so a test counts how
often the upstream really ran something. Values of ``QA_CANARY*`` environment
variables are replaced by ``[CANARY]`` before anything is written.

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
    "image",
    "business_error",
    "rpc_error",
    "slow",
    "mutate",
    "progress",
    "crash",
    "environment",
    "large",
    "secret_echo",
    "secret_stderr",
    "secret_stderr_split",
    "secret_stderr_exit",
    "sampling",
    "roots",
]
ECHO_OUTPUT_SCHEMA = {"type": "object", "properties": {"tag": {"type": "string"}}}
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
    cursor = params.cursor if params else None
    record("tools/list", cursor=cursor)
    names = [*TOOLS, "added"] if state["mutated"] else list(TOOLS)
    next_cursor = None
    if args.mode == "paged":
        names, next_cursor = (names[:2], "qa-next") if not cursor else (names[2:], None)
    schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "delay": {"type": "number"},
            "n": {"type": "integer"},
        },
    }
    return types.ListToolsResult(
        tools=[
            types.Tool(
                name=n,
                description=f"qa synthetic {args.tag} {n}",
                input_schema={**schema, "required": ["text"] if n == "echo" else []},
                annotations=types.ToolAnnotations(read_only_hint=True),
                output_schema=ECHO_OUTPUT_SCHEMA if n == "echo" else None,
            )
            for n in names
        ],
        next_cursor=next_cursor,
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
    if name == "echo" and not isinstance(a.get("text"), str):
        raise MCPError(-32602, "fixture says: text must be a string")
    if name == "rpc_error":
        raise MCPError(-32602, "fixture intentional protocol error")
    if name == "crash":
        record("exit", name=name)
        os._exit(17)
    if name == "slow":
        try:
            await asyncio.sleep(float(a.get("delay", 6)))
        except asyncio.CancelledError:
            record("cancelled", name=name, arguments=a)
            raise
    if name in ("sampling", "roots"):
        return await _ask_client(ctx, name)
    if name.startswith("secret_stderr"):
        await _secret_stderr(name)
    if name == "business_error":
        record("done", name=name)
        return _text("fixture business rejection", error=True)
    if name == "mutate":
        state["mutated"] = True
        await ctx.session.send_tool_list_changed()
        await ctx.session.send_resource_list_changed()
        await ctx.session.send_prompt_list_changed()
    if name == "progress":
        token = (ctx.meta or {}).get("progressToken", (ctx.meta or {}).get("progress_token"))
        if token is not None:
            for i in range(3):
                await ctx.session.send_progress_notification(
                    progress_token=token, progress=i + 1, total=3, message="qa progress"
                )
    if name == "image":
        record("done", name=name)
        return types.CallToolResult(
            content=[
                types.ImageContent(type="image", data="iVBORw0KGgo=", mime_type="image/png"),
                types.TextContent(type="text", text=args.tag),
            ]
        )
    payload: dict[str, Any] = {"tag": args.tag, "name": name, "arguments": a, "pid": os.getpid()}
    if name == "environment":
        payload.update(
            cwd=os.getcwd(),
            env=os.environ.get("QA_ENV"),
            secret_present=bool(os.environ.get("QA_CANARY_SECRET")),
        )
    if name == "secret_echo":
        payload["echo"] = os.environ.get("QA_CANARY_SECRET", "no-secret")
    if name == "large":
        payload["data"] = "x" * int(a.get("n", 262144))
    record("done", name=name, arguments=a)
    return _text(json.dumps(payload), structured=payload)


async def list_resources(ctx: Any, params: Any) -> types.ListResourcesResult:
    record("resources/list")
    return types.ListResourcesResult(
        resources=[types.Resource(uri="qa://same", name="qa same", mime_type="text/plain")]
    )


async def read(ctx: Any, params: Any) -> types.ReadResourceResult:
    record("resources/read", uri=str(params.uri))
    if str(params.uri) != "qa://same":
        raise MCPError(-32002, "fixture resource not found")
    return types.ReadResourceResult(
        contents=[types.TextResourceContents(uri=params.uri, text=args.tag, mime_type="text/plain")]
    )


async def list_prompts(ctx: Any, params: Any) -> types.ListPromptsResult:
    record("prompts/list")
    argument = types.PromptArgument(name="text", required=True)
    return types.ListPromptsResult(prompts=[types.Prompt(name="same", arguments=[argument])])


async def prompt(ctx: Any, params: Any) -> types.GetPromptResult:
    record("prompts/get", name=params.name, arguments=params.arguments)
    if params.name != "same" or not (params.arguments or {}).get("text"):
        raise MCPError(-32602, "fixture prompt needs text")
    text = f"{args.tag}:{params.arguments['text']}"
    return types.GetPromptResult(
        messages=[
            types.PromptMessage(role="user", content=types.TextContent(type="text", text=text))
        ]
    )


def server() -> Server[Any]:
    return Server(
        "qa-installed-upstream",
        on_list_tools=list_tools,
        on_call_tool=call,
        on_list_resources=list_resources,
        on_read_resource=read,
        on_list_prompts=list_prompts,
        on_get_prompt=prompt,
    )


def _raw_path(request: Any) -> str:
    """The path exactly as sent (``%2F`` kept), which Starlette's ``url.path`` decodes."""
    raw = request.scope.get("raw_path")
    return raw.decode("latin-1") if raw else str(request.url.path)


async def echo_receiver(request: Any) -> Any:
    """Records what a custom HTTP tool sent; answers by path."""
    from starlette.responses import JSONResponse, RedirectResponse, Response

    body = (await request.body()).decode(errors="replace")
    auth = request.headers.get("authorization") or ""
    expected = os.environ.get("QA_CANARY_EXPECTED", "")
    port = request.scope.get("server", (None, None))[1]
    record(
        "http",
        method=request.method,
        path=_raw_path(request),
        query=request.url.query,
        port=port,
        headers={
            k: ("[AUTH]" if k.lower() in {"authorization", "x-api-key"} else v)
            for k, v in request.headers.items()
        },
        body=body,
        auth_matches_canary=bool(expected) and auth.split(" ")[-1] == expected,
    )
    path = _raw_path(request)
    if "/slow" in path:
        await asyncio.sleep(3)
    if "/redirect" in path:
        return RedirectResponse(request.query_params["to"], status_code=302)
    if "/status/" in path:
        return Response("qa failure body", status_code=int(path.rsplit("/", 1)[1]))
    if "/large-secret" in path:
        return Response(f"head {expected} " + "x" * 2_000_000, media_type="text/plain")
    if "/large" in path:
        return Response("x" * 2_000_000, media_type="text/plain")
    if "/secret-echo" in path:
        return JSONResponse({"echo": auth})
    if "/disconnect" in path:
        raise RuntimeError("qa simulated upstream failure")
    scheme = auth.split(" ")[0] if " " in auth else ("raw" if auth else "none")
    return JSONResponse(
        {
            "tag": args.tag,
            "path": path,
            "query": request.url.query,
            "method": request.method,
            "body": body,
            "env": request.headers.get("x-env"),
            "arg": request.headers.get("x-arg"),
            "auth_present": bool(auth),
            "auth_scheme": scheme,
            "auth_matches_canary": bool(expected) and auth.split(" ")[-1] == expected,
        }
    )


async def serve_http() -> None:
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    sdk_app = server().streamable_http_app(
        streamable_http_path="/", stateless_http=not args.stateful
    )

    async def lifespan(app: Any) -> Any:
        async with sdk_app.router.lifespan_context(sdk_app):
            yield

    methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    app = Starlette(
        routes=[Mount("/mcp", app=sdk_app), Route("/{path:path}", echo_receiver, methods=methods)],
        lifespan=lifespan,
    )
    sockets = []
    for _ in range(2):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        sockets.append(sock)
    ports = {"port": sockets[0].getsockname()[1], "other_port": sockets[1].getsockname()[1]}
    record("process-start", transport="http", stateful=args.stateful, **ports)
    Path(args.ready).write_text(json.dumps(ports))
    await uvicorn.Server(uvicorn.Config(app, log_level="warning")).serve(sockets=sockets)


async def main() -> None:
    record("process-start", transport=args.transport, cwd=os.getcwd(), mode=args.mode)
    if args.transport == "http":
        await serve_http()
        return
    print("qa stderr plain line", file=sys.stderr, flush=True)
    if args.mode == "exit":
        return
    if args.mode == "pollute":
        print("qa invalid stdout line", flush=True)
    if args.mode == "invalid-json":
        print("{qa-invalid", flush=True)
    s = server()
    async with stdio_server() as (r, w):
        await s.run(r, w, s.create_initialization_options())
    record("process-stop")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--transport", default="stdio", choices=["stdio", "http"])
    p.add_argument("--mode", default="basic")
    p.add_argument("--stateful", action="store_true")
    p.add_argument("--tag", required=True)
    p.add_argument("--ledger", required=True)
    p.add_argument("--ready")
    args = p.parse_args()
    asyncio.run(main())
