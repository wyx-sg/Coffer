"""The installed build's gateway overhead budget.

The spec's budget — at most 50 ms of median overhead over 100 calls compared
with calling the same fixture directly — measured end to end over HTTP against
the frozen daemon, whose import and runtime costs differ from the source tree
the repository's in-process benchmark measures. A shared-machine number: it
shows the order of magnitude, not a benchmark.
"""

from __future__ import annotations

import statistics
import time
from typing import Any

from e2e.installed.mcp.context import PYTHON, UPSTREAM, Ctx

BENCH = "qa-mcp-bench"


async def run(ctx: Ctx) -> None:
    await _overhead(ctx)


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
        "the installed gateway adds at most 50 ms of median overhead",
        "100 warm calls through the installed daemon against the same fixture called directly",
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
