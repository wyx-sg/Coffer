"""A controllable real MCP server for tests.

Run as a subprocess; coffer's StdioUpstreamConnection talks to it over
stdin/stdout JSON-RPC just like any real upstream MCP server.

CLI flags shape its behaviour:

    --scenario {basic,slow,crash,mutating}   Default: basic
    --tools TOOL [TOOL ...]                  Names to expose as tools
    --resources URI [URI ...]                Resource URIs
    --prompts NAME [NAME ...]                Prompt names
    --crash-after-calls N                    Exit after Nth tools/call (scenario=crash)
    --init-delay-ms N                        Sleep before initialize (scenario=slow)
    --notify-list-changed-after N            Emit tools/list_changed after Nth call
    --no-resources                           Do NOT register a resources/list handler,
                                             so the SDK replies -32601 METHOD_NOT_FOUND
                                             (models a tools-only upstream)
    --no-prompts                             Do NOT register a prompts/list handler,
                                             so the SDK replies -32601 METHOD_NOT_FOUND
    --transport {stdio,http}                 Transport mode (default: stdio)
    --port PORT                              HTTP port (only used with --transport http)

The server uses the official `mcp` SDK's `stdio_server` helper so
framing + lifecycle match real upstreams exactly.  When --transport http is
given, the server is exposed via the MCP SDK's StreamableHTTP ASGI app on
the specified port (default 0 = kernel-assigned, printed to stdout as
"READY port=<N>").
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
from typing import Any

import mcp.types as mcp_types
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from pydantic import AnyUrl


def _build_server(args: argparse.Namespace) -> tuple[Server[Any, Any], dict[str, Any]]:
    """Return the configured mcp.Server plus a mutable state dict for hooks."""
    server: Server[Any, Any] = Server("fake-mcp-server")

    state: dict[str, Any] = {
        "scenario": args.scenario,
        "tools": list(args.tools or []),
        "resources": list(args.resources or []),
        "prompts": list(args.prompts or []),
        "calls": 0,
        "crash_after": args.crash_after_calls,
        "init_delay_ms": args.init_delay_ms,
        "notify_list_changed_after": args.notify_list_changed_after,
        "list_changed_fired": False,
        "progress_steps": args.progress_steps,
        "progress_delay_ms": args.progress_delay_ms,
    }

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def list_tools() -> list[mcp_types.Tool]:
        # In the `mutating` scenario, after the list_changed has fired,
        # remove the first tool from the published set.
        tools = list(state["tools"])
        if state["scenario"] == "mutating" and state["list_changed_fired"]:
            tools = tools[1:]
        return [
            mcp_types.Tool(
                name=name,
                description=f"fake tool {name}",
                inputSchema={"type": "object", "properties": {}},
            )
            for name in tools
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[mcp_types.TextContent]:
        state["calls"] += 1
        # crash_after applies to any scenario so tests can combine crash+mutating.
        if state["crash_after"] is not None and state["calls"] == state["crash_after"]:
            # os._exit bypasses Python cleanup and immediately terminates the process,
            # ensuring the subprocess dies and the stdio pipe closes for the client.
            # sys.exit() only raises SystemExit which gets swallowed by asyncio TaskGroups.
            os._exit(1)
        if (
            state["scenario"] == "mutating"
            and state["notify_list_changed_after"] is not None
            and state["calls"] == state["notify_list_changed_after"]
        ):
            state["list_changed_fired"] = True
            # send_tool_list_changed() is called from inside a request handler,
            # so server.request_context is always set here.  Any error means the
            # fixture is broken and tests should fail loudly rather than silently
            # passing with no notification delivered.
            ctx = server.request_context
            await ctx.session.send_tool_list_changed()
        if state["scenario"] == "progress":
            # Emit a series of progress notifications with a configurable delay between
            # them, then return a final result.  This lets tests verify that:
            # (a) progress notifications reach the client, and
            # (b) the call completes without premature timeout when read_timeout_seconds
            #     is used (the SDK resets its idle-read timer on each progress event).
            steps: int = state["progress_steps"] or 3
            delay_s: float = (state["progress_delay_ms"] or 100) / 1000.0
            ctx = server.request_context
            # Extract the progressToken from the request metadata (if provided).
            progress_token = ctx.meta.progressToken if ctx.meta else None
            for step in range(steps):
                if progress_token is not None:
                    await ctx.session.send_progress_notification(
                        progress_token=progress_token,
                        progress=float(step + 1),
                        total=float(steps),
                        message=f"step {step + 1}/{steps}",
                    )
                await asyncio.sleep(delay_s)
            return [
                mcp_types.TextContent(
                    type="text",
                    text=f"done:{name}:steps={steps}",
                )
            ]
        return [mcp_types.TextContent(type="text", text=f"echo:{name}:{arguments or {}}")]

    # When --no-resources / --no-prompts are given, the corresponding handlers
    # are NOT registered. The MCP SDK then has no handler for resources/list or
    # prompts/list and replies with JSON-RPC -32601 METHOD_NOT_FOUND, exactly as
    # a real tools-only upstream does. This is the only way to drive a genuine
    # method-not-found: a registered handler returning [] would reply 200/empty.
    if not args.no_resources:

        @server.list_resources()  # type: ignore[no-untyped-call, untyped-decorator]
        async def list_resources() -> list[mcp_types.Resource]:
            return [
                mcp_types.Resource(
                    uri=AnyUrl(uri),
                    name=f"resource {uri}",
                    description=f"fake resource {uri}",
                    mimeType="text/plain",
                )
                for uri in state["resources"]
            ]

        @server.read_resource()  # type: ignore[no-untyped-call, untyped-decorator]
        async def read_resource(uri: Any) -> list[ReadResourceContents]:
            return [ReadResourceContents(content=f"content of {uri}", mime_type="text/plain")]

    if not args.no_prompts:

        @server.list_prompts()  # type: ignore[no-untyped-call, untyped-decorator]
        async def list_prompts() -> list[mcp_types.Prompt]:
            return [
                mcp_types.Prompt(
                    name=name,
                    description=f"fake prompt {name}",
                    arguments=[],
                )
                for name in state["prompts"]
            ]

        @server.get_prompt()  # type: ignore[no-untyped-call, untyped-decorator]
        async def get_prompt(
            name: str, arguments: dict[str, str] | None
        ) -> mcp_types.GetPromptResult:
            return mcp_types.GetPromptResult(
                description=f"fake prompt {name}",
                messages=[
                    mcp_types.PromptMessage(
                        role="user",
                        content=mcp_types.TextContent(type="text", text=f"prompt-text:{name}"),
                    )
                ],
            )

    return server, state


async def _run_stdio(args: argparse.Namespace) -> None:
    if args.scenario == "slow" and args.init_delay_ms:
        # Deliberately slow startup; coffer's spawn_timeout will trip.
        await asyncio.sleep(args.init_delay_ms / 1000)
    server, _state = _build_server(args)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


async def _run_http(args: argparse.Namespace) -> None:
    """Serve the fake MCP server over streamable-HTTP using uvicorn.

    Prints "READY port=<N>" to stdout once the server is listening so the
    test harness can pick up the actual port (important when --port 0 is
    used to let the kernel assign a free port).
    """
    # These imports are deferred because they are only needed for HTTP mode
    # (uvicorn + Starlette + MCP streamable-HTTP classes are not installed in
    # stdio-only environments).
    import contextlib
    import socket
    import sys
    from collections.abc import AsyncIterator

    import uvicorn
    from mcp.server.fastmcp.server import StreamableHTTPASGIApp
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.routing import Mount

    mcp_server, _state = _build_server(args)
    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        stateless=True,  # stateless is simplest for test upstreams
    )
    asgi_handler = StreamableHTTPASGIApp(session_manager)

    @contextlib.asynccontextmanager
    async def _lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    starlette_app = Starlette(
        routes=[Mount("/mcp", app=asgi_handler)],
        lifespan=_lifespan,
    )

    # Bind a socket up-front so the OS assigns a free port atomically —
    # avoids the TOCTOU race where we close a probe socket and another process
    # steals the port before uvicorn can bind.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))  # args.port==0 → kernel assigns
    port = sock.getsockname()[1]  # read back the actual assigned port

    config = uvicorn.Config(
        starlette_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    # Patch the startup so we can print the port after the server is actually
    # listening but before uvicorn's serve() yields control to the ASGI app.
    original_startup = server.startup

    async def _startup_with_announce(sockets: list | None = None) -> None:
        await original_startup(sockets=sockets)
        # Announce the actual port once uvicorn is listening.
        print(f"READY port={port}", flush=True)
        sys.stdout.flush()

    server.startup = _startup_with_announce  # type: ignore[method-assign]

    # Pass the already-bound socket directly — do NOT close it before serving.
    await server.serve(sockets=[sock])


async def _run(args: argparse.Namespace) -> None:
    if args.transport == "http":
        await _run_http(args)
    else:
        await _run_stdio(args)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--scenario",
        choices=["basic", "slow", "crash", "mutating", "progress"],
        default="basic",
    )
    p.add_argument("--tools", nargs="*", default=["read_file", "write_file"])
    p.add_argument("--resources", nargs="*", default=[])
    p.add_argument("--prompts", nargs="*", default=[])
    p.add_argument("--crash-after-calls", type=int, default=None)
    p.add_argument("--init-delay-ms", type=int, default=0)
    p.add_argument("--notify-list-changed-after", type=int, default=None)
    p.add_argument(
        "--no-resources",
        action="store_true",
        help="Skip registering the resources/list handler (SDK replies -32601)",
    )
    p.add_argument(
        "--no-prompts",
        action="store_true",
        help="Skip registering the prompts/list handler (SDK replies -32601)",
    )
    p.add_argument(
        "--progress-steps",
        type=int,
        default=3,
        help="Number of progress notifications to emit (scenario=progress)",
    )
    p.add_argument(
        "--progress-delay-ms",
        type=int,
        default=100,
        help="Milliseconds between progress notifications (scenario=progress)",
    )
    p.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
    )
    p.add_argument("--port", type=int, default=0)
    return p.parse_args()


def start_http_fake(
    tools: list[str],
    *,
    scenario: str = "basic",
    timeout: float = 10.0,
) -> tuple[subprocess.Popen[str], int]:
    """Start fake_mcp_server in HTTP mode; return ``(proc, port)``.

    Launches the fake server as a subprocess, waits for the ``READY port=N``
    line on stdout, and returns the process handle and the assigned port.
    Runs the port-reading loop in a background thread so it does not block an
    asyncio event loop.

    Raises ``AssertionError`` if the server does not become ready within
    ``timeout`` seconds.
    """
    import queue
    import sys
    import threading
    import time

    proc: subprocess.Popen[str] = subprocess.Popen(
        [
            sys.executable,
            __file__,
            "--transport",
            "http",
            "--port",
            "0",
            "--scenario",
            scenario,
            "--tools",
            *tools,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    q: queue.Queue[str] = queue.Queue()

    def _read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            q.put(line)
            if line.startswith("READY port="):
                return

    threading.Thread(target=_read, daemon=True).start()

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = q.get(timeout=0.1)
            if line.startswith("READY port="):
                return proc, int(line.strip().split("=")[1])
        except queue.Empty:
            if proc.poll() is not None:
                raise AssertionError(
                    f"fake HTTP server exited unexpectedly (rc={proc.returncode})"
                ) from None
    proc.terminate()
    raise AssertionError("fake HTTP server did not announce its port in time")


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
