"""An upstream's sampling and roots requests, relayed through the installed
daemon to the right official-SDK client over Streamable HTTP and SSE.

First a control: the fixture's sampling and roots tools work with the official
SDK directly, outside Coffer, so a failure through the gateway is the
gateway's. Which client is asked, and that an undeclared capability is never
asked, is pinned by the repository's suites; here the point is that the
server-initiated request rides the frozen daemon's notification stream and the
client's answer comes back over its HTTP POST.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from e2e.installed.mcp.cases_sdk import http_session
from e2e.installed.mcp.context import PYTHON, UPSTREAM, Ctx

A, RELAY = "qa-mcp-a", "qa-mcp-relay"


def answering_client(sample_text: str, root_uri: str) -> tuple[dict[str, Any], Counter[str]]:
    """SDK callbacks answering sampling with ``sample_text`` and roots with
    ``root_uri``, and a counter of how often each was asked."""
    import mcp.types as types

    asked: Counter[str] = Counter()

    async def sampling(_ctx: Any, _params: Any) -> types.CreateMessageResult:
        asked["sampling"] += 1
        return types.CreateMessageResult(
            model="qa-synthetic-no-provider",
            role="assistant",
            content=types.TextContent(type="text", text=sample_text),
        )

    async def roots(_ctx: Any) -> types.ListRootsResult:
        asked["roots"] += 1
        return types.ListRootsResult(roots=[types.Root(uri=root_uri, name="qa root")])

    return {"sampling_callback": sampling, "list_roots_callback": roots}, asked


def texts(result: Any) -> list[str]:
    return [c.text for c in result.content if hasattr(c, "text")]


async def run(ctx: Ctx) -> None:
    await _direct_control(ctx)
    await _two_clients(ctx)


async def _direct_control(ctx: Ctx) -> None:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    callbacks, _ = answering_client("direct", "file:///qa-direct")
    tag = "qa-mcp-direct"
    params = StdioServerParameters(
        command=PYTHON,
        args=[str(UPSTREAM), "--tag", tag, "--ledger", str(ctx.ledger(tag))],
        env={"PATH": "/usr/bin:/bin"},
    )
    with (ctx.run.out / "direct-control-stderr.log").open("w") as errlog:
        async with stdio_client(params, errlog=errlog) as (r, w):
            async with ClientSession(r, w, read_timeout_seconds=15, **callbacks) as session:
                await session.initialize()
                got = texts(await session.call_tool("sampling", {}))
                got += texts(await session.call_tool("roots", {}))
    ctx.rec.record(
        "fixture control: sampling and roots answered by the SDK directly",
        "control: the fixture's sampling and roots work with the official SDK, outside Coffer",
        expected="sampling:direct and roots:file:///qa-direct",
        actual=got,
        ok=got == ["sampling:direct", "roots:file:///qa-direct"],
    )


async def _client(ctx: Ctx, sample: str, root: str) -> dict[str, Any]:
    callbacks, asked = answering_client(sample, root)
    async with http_session(ctx, **callbacks) as client:
        await client.initialize()
        calls = [(server, tool) for server in (A, RELAY) for tool in ("sampling", "roots")]
        replies = await asyncio.gather(*(client.call_tool(f"{s}__{t}", {}) for s, t in calls))
    return {
        "results": {f"{s} {t}": texts(r) for (s, t), r in zip(calls, replies, strict=True)},
        "asked": dict(asked),
    }


async def _two_clients(ctx: Ctx) -> None:
    one, two = await asyncio.gather(
        _client(ctx, "qa-answer-one", "file:///qa-one"),
        _client(ctx, "qa-answer-two", "file:///qa-two"),
    )

    def answered(seen: dict[str, Any], sample: str, root: str) -> bool:
        want = {
            f"{s} {t}": [f"sampling:{sample}" if t == "sampling" else f"roots:{root}"]
            for s in (A, RELAY)
            for t in ("sampling", "roots")
        }
        return seen["results"] == want and seen["asked"] == {"sampling": 2, "roots": 2}

    ctx.rec.record(
        "two clients each answer their own upstream's sampling and roots",
        "stdio and stateful HTTP upstreams ask two SDK clients at once through the installed "
        "daemon; each gets its own answer",
        expected="every call returns its own client's answer; each client asked exactly once per "
        "tool per server (2 sampling, 2 roots)",
        actual={"one": one, "two": two},
        ok=answered(one, "qa-answer-one", "file:///qa-one")
        and answered(two, "qa-answer-two", "file:///qa-two"),
    )
