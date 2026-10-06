"""An upstream's sampling and roots requests, relayed to the right client.

First a control: the fixture's sampling and roots tools work with the official
SDK directly, outside Coffer, so a failure through the gateway is the gateway's.
"""

from __future__ import annotations

import asyncio
from typing import Any

from e2e.installed.mcp.context import PYTHON, UPSTREAM, Ctx
from e2e.installed.mcp.wire import EventStream, answering, in_band_error, text_of

A, RELAY = "qa-mcp-a", "qa-mcp-relay"
CAPS = {"sampling": {}, "roots": {"listChanged": True}}


async def run(ctx: Ctx) -> None:
    await _direct_control(ctx)
    await _two_clients(ctx)
    await _undeclared(ctx)


async def _direct_control(ctx: Ctx) -> None:
    import mcp.types as types
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def sampling(_ctx: Any, _params: Any) -> types.CreateMessageResult:
        return types.CreateMessageResult(
            model="qa-direct",
            role="assistant",
            content=types.TextContent(type="text", text="direct"),
        )

    async def roots(_ctx: Any) -> types.ListRootsResult:
        return types.ListRootsResult(roots=[types.Root(uri="file:///qa-direct", name="qa")])

    tag = "qa-mcp-direct"
    params = StdioServerParameters(
        command=PYTHON,
        args=[str(UPSTREAM), "--tag", tag, "--ledger", str(ctx.ledger(tag))],
        env={"PATH": "/usr/bin:/bin"},
    )
    with (ctx.run.out / "direct-control-stderr.log").open("w") as errlog:
        async with stdio_client(params, errlog=errlog) as (r, w):
            async with ClientSession(
                r, w, sampling_callback=sampling, list_roots_callback=roots, read_timeout_seconds=15
            ) as session:
                await session.initialize()
                sample = await session.call_tool("sampling", {})
                listed = await session.call_tool("roots", {})
    texts = [c.text for c in sample.content if hasattr(c, "text")]
    texts += [c.text for c in listed.content if hasattr(c, "text")]
    ctx.rec.record(
        "CTRL001",
        "control: the fixture's sampling and roots work with the official SDK directly",
        expected="sampling:direct and roots:file:///qa-direct, outside Coffer",
        actual=texts,
        ok=texts == ["sampling:direct", "roots:file:///qa-direct"],
    )


async def _two_clients(ctx: Ctx) -> None:
    w = ctx.wire
    one, _ = await w.initialize("qa-agent-a", caps=CAPS)
    two, _ = await w.initialize("qa-agent-a", caps=CAPS)
    answers = {one: ("qa-answer-one", "file:///qa-one"), two: ("qa-answer-two", "file:///qa-two")}
    async with (
        EventStream(w, one, answering(*answers[one]), seconds=40) as s1,
        EventStream(w, two, answering(*answers[two]), seconds=40) as s2,
    ):
        calls = [
            (sid, server, tool)
            for sid in (one, two)
            for server in (A, RELAY)
            for tool in ("sampling", "roots")
        ]
        replies = await asyncio.gather(
            *(
                w.call(sid, f"{server}__{tool}", rid=f"qa-{server}-{tool}", timeout=30)
                for sid, server, tool in calls
            )
        )
        await s1.settle(0.3)
    results = {}
    passed = True
    for (sid, server, tool), reply in zip(calls, replies, strict=True):
        sample, root = answers[sid]
        want = f"sampling:{sample}" if tool == "sampling" else f"roots:{root}"
        got = text_of(reply)
        passed &= got == want
        results[f"{'one' if sid == one else 'two'} {server} {tool}"] = got
    asked = {
        name: {m: len(stream.requests(m)) for m in ("sampling/createMessage", "roots/list")}
        for name, stream in (("one", s1), ("two", s2))
    }
    ctx.rec.record(
        "two clients each answer their own upstream's sampling and roots",
        "stdio and stateful HTTP upstreams ask two clients at once; each gets its own answer",
        expected="every call returns its own client's answer; each client asked exactly once per "
        "tool per server (2 sampling, 2 roots)",
        actual={"results": results, "asked": asked},
        ok=passed
        and all(v == {"sampling/createMessage": 2, "roots/list": 2} for v in asked.values()),
    )


async def _undeclared(ctx: Ctx) -> None:
    w = ctx.wire
    sid, _ = await w.initialize("qa-agent-a")
    async with EventStream(
        w, sid, answering("qa-should-not-be-asked", "file:///qa-no"), seconds=30
    ) as s:
        replies = {
            f"{server} {tool}": await w.call(sid, f"{server}__{tool}", timeout=30)
            for server in (A, RELAY)
            for tool in ("sampling", "roots")
        }
        await s.settle(0.3)
    asked = [m for m in s.messages if "id" in m and "method" in m]
    ctx.rec.record(
        "a client that declared no sampling is never asked to sample",
        "a session that declared neither capability is never asked",
        expected="all four tools report the client refused (in-band error); the client's stream "
        "carries no request",
        actual={"replies": {k: text_of(v) for k, v in replies.items()}, "asked": asked},
        ok=all(in_band_error(v) and text_of(v).startswith("refused") for v in replies.values())
        and not asked,
    )
