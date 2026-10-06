"""The official MCP SDK as a real client: over Streamable HTTP, and over stdio
through the installed ``coffer-mcp-shim``."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from e2e.installed._common.recorder import BLOCKED
from e2e.installed.mcp.context import Ctx

A, B, T = "qa-mcp-a", "qa-mcp-b", "qa-mcp-toggle"


async def run(ctx: Ctx) -> None:
    await _over_http(ctx)
    await _over_shim(ctx)


async def _over_http(ctx: Ctx) -> None:
    import httpx2
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {"X-Coffer-Token": ctx.run.target.token}
    async with httpx2.AsyncClient(headers=headers, trust_env=False) as http:
        url = ctx.run.target.base_url + "/mcp"
        async with (
            streamable_http_client(url, http_client=http) as (r, w),
            ClientSession(r, w, read_timeout_seconds=15) as client,
        ):
            init = await client.initialize()
            listing = await client.list_tools()
            result = await client.call_tool(f"{B}__echo", {"text": "qa SDK HTTP"})
            resource = await client.read_resource(f"coffer://{B}/qa://same")
            prompt = await client.get_prompt(f"{B}__same", {"text": "sdk"})
    sc = result.structured_content or {}
    ctx.rec.record(
        "SDK001",
        "the official SDK initializes, lists and calls over Streamable HTTP",
        expected="protocol 2025-06-18, a non-empty list, qa-mcp-b's echo answers with its tag",
        actual={"protocol": init.protocol_version, "tools": len(listing.tools), "structured": sc},
        ok=init.protocol_version == "2025-06-18"
        and bool(listing.tools)
        and sc.get("tag") == B
        and not result.is_error,
    )
    texts = [getattr(c, "text", None) for c in resource.contents]
    message = prompt.messages[0].content if prompt.messages else None
    ctx.rec.record(
        "SDK002",
        "the official SDK reads a namespaced resource and gets a namespaced prompt",
        expected="resource text qa-mcp-b; prompt text qa-mcp-b:sdk",
        actual={"resource": texts, "prompt": getattr(message, "text", None)},
        ok=texts == [B] and getattr(message, "text", None) == f"{B}:sdk",
    )


def _shim_blocker(ctx: Ctx) -> str | None:
    target = ctx.run.target
    if target.shim is None or not target.shim.is_file():
        return f"no installed coffer-mcp-shim found (looked at {target.shim}); pass --shim"
    if target.home is None:
        return "the shim reads $HOME/.coffer/daemon.json; --daemon-json is not at that place"
    return None


SHIM_CASES = (
    ("SDK003", "the official SDK over the installed stdio shim initializes, lists and calls"),
    ("aggregate tools across servers in one client", "the shim lists both servers' tools"),
    ("SDK004", "the shim answers a ping while a slow call is in flight"),
    ("disabled capability rejected through the shim", "a switched-off tool through the shim"),
)


async def _over_shim(ctx: Ctx) -> None:
    blocker = _shim_blocker(ctx)
    if blocker:
        for cid, title in SHIM_CASES:
            ctx.rec.record(
                cid,
                title,
                expected="runs through the shim",
                actual={"reason": blocker},
                status=BLOCKED,
            )
        return
    # The target must answer right now: a shim that finds no daemon starts one itself.
    status = await ctx.run.client.request("GET", "/api/v1/daemon/status")
    if status.status != 200 or status.json.get("pid") != ctx.run.target.pid:
        raise RuntimeError("target daemon not answering before the shim starts")
    await _shim_session(ctx)


async def _shim_session(ctx: Ctx) -> None:
    from mcp import MCPError
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    target = ctx.run.target
    params = StdioServerParameters(
        command=str(target.shim),
        args=["--agent-uid", "qa-agent-shim"],
        env={"HOME": str(target.home)},
        cwd=str(ctx.run.out),
    )
    with (ctx.run.out / "shim-stderr.log").open("w") as errlog:
        async with stdio_client(params, errlog=errlog) as (r, w):
            async with ClientSession(r, w, read_timeout_seconds=20) as client:
                await client.initialize()
                listing = await client.list_tools()
                names = [t.name for t in listing.tools]
                reply = await client.call_tool(f"{A}__environment", {})
                sc = reply.structured_content or {}
                ctx.rec.record(
                    "SDK003",
                    SHIM_CASES[0][1],
                    expected="the stdio server's own cwd and env reach its tool through the shim",
                    actual={"structured": sc, "tools": len(names)},
                    ok=bool(names)
                    and sc.get("env") == "qa-env-value"
                    and sc.get("cwd") == str(ctx.run.out),
                )
                ctx.rec.record(
                    "aggregate tools across servers in one client",
                    SHIM_CASES[1][1],
                    expected="qa-mcp-a__echo and qa-mcp-b__echo listed, every name unique",
                    actual={"qa_tools": sorted(n for n in names if n.startswith("qa-"))},
                    ok={f"{A}__echo", f"{B}__echo"} <= set(names) and len(names) == len(set(names)),
                )
                await _pipelined_ping(ctx, client)
                await ctx.toggle(T, "business_error", False)
                try:
                    listing = await client.list_tools()
                    names = [t.name for t in listing.tools]
                    error: Any = None
                    try:
                        await client.call_tool(f"{T}__business_error", {})
                    except MCPError as exc:
                        error = exc.code
                finally:
                    await ctx.toggle(T, "business_error", True)
                ctx.rec.record(
                    "disabled capability rejected through the shim",
                    SHIM_CASES[3][1],
                    expected="tools/list omits qa-mcp-toggle__business_error (pinned) but keeps "
                    "qa-mcp-toggle__echo; the call "
                    "is a JSON-RPC -32000",
                    actual={
                        "disabled_listed": f"{T}__business_error" in names,
                        "echo_listed": f"{T}__echo" in names,
                        "error_code": error,
                    },
                    ok=f"{T}__business_error" not in names
                    and f"{T}__echo" in names
                    and error == -32000,
                )


async def _pipelined_ping(ctx: Ctx, client: Any) -> None:
    task = asyncio.create_task(client.call_tool(f"{A}__slow", {"delay": 1.0}))
    await asyncio.sleep(0.1)
    t0 = time.perf_counter()
    await client.send_ping()
    ping_ms = (time.perf_counter() - t0) * 1000
    in_flight = not task.done()
    await task
    ctx.rec.record(
        "SDK004",
        SHIM_CASES[2][1],
        expected="the ping returns while the 1 s call is still running",
        actual={"ping_ms": round(ping_ms, 1), "slow_still_running": in_flight},
        ok=in_flight,
    )
