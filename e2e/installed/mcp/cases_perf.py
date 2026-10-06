"""A light concurrency and latency observation, and the gateway overhead budget.

Shared-machine numbers: they show correlation and the order of magnitude, not a
benchmark. The one budget asserted is the spec's: at most 50 ms of median
overhead over 100 calls compared with calling the same fixture directly.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any

from e2e.installed.mcp.context import PYTHON, UPSTREAM, Ctx
from e2e.installed.mcp.wire import ok, structured

B, BENCH = "qa-mcp-b", "qa-mcp-bench"


async def run(ctx: Ctx) -> None:
    await _correlation(ctx)
    await _sessions(ctx)
    await _overhead(ctx)


async def _correlation(ctx: Ctx) -> None:
    sid, _ = await ctx.wire.initialize("qa-agent-a")
    await ctx.wire.call(sid, f"{B}__echo", {"text": "warm"})
    gate = asyncio.Semaphore(4)
    latencies: list[float] = []
    wrong: list[int] = []

    async def one(i: int) -> None:
        async with gate:
            t0 = time.perf_counter()
            reply = await ctx.wire.call(sid, f"{B}__echo", {"text": f"qa {i}"}, rid=f"load-{i}")
            latencies.append((time.perf_counter() - t0) * 1000)
            if not ok(reply) or structured(reply).get("arguments", {}).get("text") != f"qa {i}":
                wrong.append(i)

    t0 = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(40)))
    metrics = {
        "calls": 40,
        "concurrency": 4,
        "seconds": round(time.perf_counter() - t0, 2),
        "p50_ms": round(statistics.median(latencies), 1),
        "p95_ms": round(sorted(latencies)[37], 1),
        "wrong": wrong,
    }
    ctx.rec.record(
        "F001",
        "forty concurrent calls each get their own answer",
        expected="40 distinct correct replies (latency recorded as an observation)",
        actual=metrics,
        ok=not wrong,
        upstream=40,
    )


async def _sessions(ctx: Ctx) -> None:
    ids, failed = [], []
    for i in range(8):
        sid, _ = await ctx.wire.initialize(f"qa-agent-{i}")
        ids.append(sid)
        reply = await ctx.wire.call(sid, f"{B}__echo", {"text": str(i)})
        if not ok(reply):
            failed.append(i)
    ctx.note_pids(B)
    ctx.rec.record(
        "F002",
        "eight sessions in a row are distinct and each answered",
        expected="8 distinct session ids, every call answered",
        actual={"distinct": len(set(ids)), "failed": failed},
        ok=len(set(ids)) == 8 and not failed,
    )


async def _measure(client: Any, name: str) -> list[float]:
    samples = []
    for i in range(100):
        t0 = time.perf_counter()
        result = await client.call_tool(name, {"text": f"qa bench {i}"})
        samples.append((time.perf_counter() - t0) * 1000)
        if result.is_error:
            raise RuntimeError(f"benchmark call failed: {result}")
    return samples


async def _overhead(ctx: Ctx) -> None:
    import httpx2
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.client.streamable_http import streamable_http_client

    tag = "qa-mcp-bench-direct"
    params = StdioServerParameters(
        command=PYTHON, args=[str(UPSTREAM), "--tag", tag, "--ledger", str(ctx.ledger(tag))]
    )
    with (ctx.run.out / "bench-direct-stderr.log").open("w") as errlog:
        async with stdio_client(params, errlog=errlog) as (r, w):
            async with ClientSession(r, w, read_timeout_seconds=15) as direct:
                await direct.initialize()
                await direct.call_tool("echo", {"text": "warm"})
                direct_ms = await _measure(direct, "echo")
    await ctx.register(BENCH, ctx.stdio(BENCH))
    headers = {"X-Coffer-Token": ctx.run.target.token}
    async with httpx2.AsyncClient(headers=headers, trust_env=False) as http:
        url = ctx.run.target.base_url + "/mcp"
        async with (
            streamable_http_client(url, http_client=http) as (r, w),
            ClientSession(r, w, read_timeout_seconds=15) as gateway,
        ):
            await gateway.initialize()
            await gateway.call_tool(f"{BENCH}__echo", {"text": "warm"})
            gateway_ms = await _measure(gateway, f"{BENCH}__echo")
    ctx.note_pids(BENCH)
    added = statistics.median(gateway_ms) - statistics.median(direct_ms)
    ctx.rec.record(
        "F003",
        "the gateway adds at most 50 ms of median overhead over 100 calls",
        expected="median(gateway) - median(direct stdio) <= 50 ms, same fixture and arguments",
        actual={
            "direct_p50_ms": round(statistics.median(direct_ms), 2),
            "gateway_p50_ms": round(statistics.median(gateway_ms), 2),
            "gateway_p95_ms": round(sorted(gateway_ms)[94], 2),
            "median_added_ms": round(added, 2),
            "scope": "end to end over HTTP on a shared machine, warm",
        },
        ok=added <= 50,
        upstream=100,
    )
