"""The installed ``coffer-mcp-shim`` connects to the frozen daemon: the
official SDK over the shim's stdio, a round trip to a synthetic stdio upstream,
and server-initiated requests (sampling, roots) relayed back through it.

Only an installed build shows this: the shim is its own frozen binary, it finds
the daemon through ``$HOME/.coffer/daemon.json`` and relays the daemon's
notification stream to stdout. Its stderr is kept for the packaging case (a
shim of another version than the daemon warns there).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from e2e.installed.mcp.cases_relay import answering_client, texts
from e2e.installed.mcp.context import Ctx

A, B = "qa-mcp-a", "qa-mcp-b"
ROUND_TRIP = "the installed shim carries a stdio session to the daemon"
RELAY = "server-initiated requests reach a client through the installed shim"


def shim_blocker(ctx: Ctx) -> str | None:
    target = ctx.run.target
    if target.shim is None or not target.shim.is_file():
        return f"no installed coffer-mcp-shim found (looked at {target.shim}); pass --shim"
    if target.home is None:
        return "the shim reads $HOME/.coffer/daemon.json; --daemon-json is not at that place"
    return None


@asynccontextmanager
async def shim_session(ctx: Ctx, log_name: str, **callbacks: Any) -> Any:
    """An official-SDK ClientSession over the installed shim's stdio."""
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    target = ctx.run.target
    params = StdioServerParameters(
        command=str(target.shim),
        args=["--agent-uid", "qa-agent-shim"],
        env={"HOME": str(target.home)},
        cwd=str(ctx.run.out),
    )
    log = ctx.run.out / log_name
    ctx.facts.setdefault("shim_logs", []).append(log)
    with log.open("w") as errlog:
        async with stdio_client(params, errlog=errlog) as (r, w):
            async with ClientSession(r, w, read_timeout_seconds=30, **callbacks) as client:
                yield client


async def run(ctx: Ctx) -> None:
    blocker = shim_blocker(ctx)
    if blocker:
        for cid in (ROUND_TRIP, RELAY):
            ctx.rec.blocked(cid, cid, expected="runs through the shim", reason=blocker)
        return
    # The target must answer right now: a shim that finds no daemon starts one itself.
    status = await ctx.run.client.request("GET", "/api/v1/daemon/status")
    if status.status != 200 or status.json.get("pid") != ctx.run.target.pid:
        raise RuntimeError("target daemon not answering before the shim starts")
    await _round_trip(ctx)
    await _relay(ctx)


async def _round_trip(ctx: Ctx) -> None:
    async with shim_session(ctx, "shim-stderr.log") as client:
        init = await client.initialize()
        names = [t.name for t in (await client.list_tools()).tools]
        before = ctx.count(A, name="environment")
        reply = await client.call_tool(f"{A}__environment", {})
        calls = ctx.count(A, name="environment") - before
    sc = reply.structured_content or {}
    ctx.rec.record(
        ROUND_TRIP,
        "initialize, tools/list and tools/call through the installed shim",
        expected="the handshake answers 2025-06-18; both qa servers' echo are listed; "
        "qa-mcp-a's environment tool runs once in its own cwd with its own env",
        actual={
            "protocol": init.protocol_version,
            "qa_tools": sorted(n for n in names if n.startswith("qa-")),
            "structured": sc,
            "upstream_calls": calls,
        },
        ok=init.protocol_version == "2025-06-18"
        and {f"{A}__echo", f"{B}__echo"} <= set(names)
        and sc.get("env") == "qa-env-value"
        and sc.get("cwd") == str(ctx.run.out)
        and calls == 1,
        upstream=calls,
    )


async def _relay(ctx: Ctx) -> None:
    callbacks, asked = answering_client("qa-answer-shim", "file:///qa-shim")
    async with shim_session(ctx, "shim-relay-stderr.log", **callbacks) as client:
        await client.initialize()
        sample = await client.call_tool(f"{A}__sampling", {})
        roots = await client.call_tool(f"{A}__roots", {})
    got = texts(sample) + texts(roots)
    ctx.rec.record(
        RELAY,
        "an upstream's sampling and roots requests travel daemon → shim → client and back",
        expected="sampling:qa-answer-shim and roots:file:///qa-shim; the client asked once each",
        actual={"results": got, "asked": asked},
        ok=got == ["sampling:qa-answer-shim", "roots:file:///qa-shim"]
        and asked == {"sampling": 1, "roots": 1},
    )
