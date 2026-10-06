"""Permissions: a switched-off capability or server, scope per session, and an
identity fixed by the one handshake. Every refusal must reach no upstream."""

from __future__ import annotations

from typing import Any

from e2e.installed.mcp.context import Ctx
from e2e.installed.mcp.wire import code, ok

A, T, PIN = "qa-mcp-a", "qa-mcp-toggle", "qa-mcp-pin"
AGENT_A, AGENT_B = "qa-agent-a", "qa-agent-b"


async def run(ctx: Ctx) -> None:
    # First, while nothing on qa-mcp-toggle is switched off: switching the only
    # switched-off tool back on is the case a stale document would hide.
    await _reenable(ctx)
    await _capability(ctx)
    await _server_switch(ctx)
    await _auto_clears_pin(ctx)
    await _scope(ctx)


async def _caps_enabled(ctx: Ctx, name: str, tool: str) -> bool | None:
    path = f"/api/v1/resources/mcp_server/{ctx.uid(name)}/capabilities"
    tools = (await ctx.run.client.request("GET", path, timeout=30)).json.get("tools", [])
    return next((t.get("enabled") for t in tools if t.get("original_name") == tool), None)


async def _reenable(ctx: Ctx) -> None:
    off = await ctx.toggle(T, "large", False)
    off_read = await _caps_enabled(ctx, T, "large")
    on = await ctx.toggle(T, "large", True)
    on_read = await _caps_enabled(ctx, T, "large")
    sid, _ = await ctx.wire.initialize(AGENT_A)
    reply = await ctx.wire.call(sid, f"{T}__large", {"n": 1})
    ctx.rec.record(
        "A009",
        "a tool switched off and back on is callable again",
        expected="disable 204 and read back off; enable 204 and read back on; a new session's "
        "call succeeds (the server has a pinned tool and no other switched-off tool)",
        actual={
            "disable": off,
            "read_after_disable": off_read,
            "enable": on,
            "read_after_enable": on_read,
            "call": reply.body,
        },
        ok=off in (200, 204)
        and off_read is False
        and on in (200, 204)
        and on_read is True
        and ok(reply),
    )


async def _capability(ctx: Ctx) -> None:
    sid, _ = await ctx.wire.initialize(AGENT_A)
    status = await ctx.toggle(T, "image", False)
    names = await ctx.wire.tool_names(sid)
    before = ctx.count(T, name="image")
    reply = await ctx.wire.call(sid, f"{T}__image")
    calls = ctx.count(T, name="image") - before
    ctx.rec.record(
        "disable an individual capability",
        "a switched-off tool leaves the list and its call is refused before the upstream",
        expected="tools/list omits qa-mcp-toggle__image (pinned listed before); the call is "
        "-32000; zero upstream calls",
        actual={"disable": status, "listed": f"{T}__image" in names, "reply": reply.body},
        ok=status in (200, 204)
        and f"{T}__image" not in names
        and f"{T}__echo" in names
        and code(reply) == -32000
        and calls == 0,
        upstream=calls,
    )


async def _server_switch(ctx: Ctx) -> None:
    sid, _ = await ctx.wire.initialize(AGENT_A)
    off = await ctx.run.client.request("POST", f"/api/v1/resources/{ctx.uid(T)}/disable")
    before = ctx.count(T)
    reply = await ctx.wire.call(sid, f"{T}__echo", {"text": "must be refused"})
    calls = ctx.count(T) - before
    on = await ctx.run.client.request("POST", f"/api/v1/resources/{ctx.uid(T)}/enable")
    ctx.rec.record(
        "A002",
        "a call to a switched-off server is refused before the upstream",
        expected="-32000 and zero upstream calls",
        actual={"disable": off.status, "reply": reply.body, "enable": on.status},
        ok=off.status == 200 and on.status == 200 and code(reply) == -32000 and calls == 0,
        upstream=calls,
    )


async def _auto_clears_pin(ctx: Ctx) -> None:
    await ctx.register(PIN, ctx.stdio(PIN))
    sid, _ = await ctx.wire.initialize(AGENT_A)
    await ctx.wire.tool_names(sid)
    await ctx.capabilities(PIN)
    off = await ctx.toggle(PIN, "large", False)
    pinned = await ctx.expose(PIN, ["image"], "listed")
    cleared = await ctx.expose(PIN, ["image"], "auto")
    reply = await ctx.run.client.request(
        "GET", f"/api/v1/resources/mcp_server/{ctx.uid(PIN)}/tiering"
    )
    row: dict[str, Any] = next(
        (r for r in reply.json.get("tools", []) if r.get("tool") == "image"), {}
    )
    ctx.note_pids(PIN)
    ctx.rec.record(
        "E005",
        "setting a pinned tool back to auto clears the pin",
        expected="with another tool switched off, image pinned listed then set auto reads back "
        "mode auto",
        actual={"disable_other": off, "pin": pinned, "auto": cleared, "image": row},
        ok=off in (200, 204)
        and pinned in (200, 204)
        and cleared in (200, 204)
        and row.get("mode") == "auto",
    )


async def _scope(ctx: Ctx) -> None:
    rec, w = ctx.rec, ctx.wire
    path = f"/api/v1/resources/{ctx.uid(A)}/scope"
    scoped = await ctx.run.client.request("PUT", path, {"scope": {"agents": [AGENT_A]}})
    try:
        denied_before = (await ctx.invocations(A, "denied")).get("total", 0)
        seen = {}
        refused_ok = True
        for label, sid in (
            ("other agent", (await w.initialize(AGENT_B))[0]),
            ("unidentified", (await w.initialize())[0]),
        ):
            names = await w.tool_names(sid)
            before = ctx.count(A)
            reply = await w.call(sid, f"{A}__echo", {"text": "must be refused"})
            calls = ctx.count(A) - before
            refused_ok &= (
                not any(n.startswith(f"{A}__") for n in names)
                and code(reply) == -32000
                and calls == 0
            )
            seen[label] = {
                "lists_a": any(n.startswith(f"{A}__") for n in names),
                "reply": reply.body,
                "upstream": calls,
            }
        denied_after = (await ctx.invocations(A, "denied")).get("total", 0)
        sid_a, _ = await w.initialize(AGENT_A)
        names_a = await w.tool_names(sid_a)
        reply_a = await w.call(sid_a, f"{A}__echo", {"text": "in scope"})
        rec.record(
            "an out-of-scope server is invisible to a session",
            "a server scoped to one agent: hidden from and refused to others, served to it",
            expected="other agent and unidentified: not listed, -32000, zero upstream, recorded "
            "denied; the named agent lists and calls it",
            actual={
                "scope": scoped.status,
                "sessions": seen,
                "denied_recorded": denied_after - denied_before,
                "named_agent": {"lists_a": f"{A}__echo" in names_a, "reply_ok": ok(reply_a)},
            },
            ok=scoped.status == 200
            and refused_ok
            and denied_after - denied_before >= 2
            and f"{A}__echo" in names_a
            and ok(reply_a),
        )
        sid_n, _ = await w.initialize(meta={"coffer/agent": AGENT_A})
        names_n = await w.tool_names(sid_n)
        rec.record(
            "a name-only handshake is treated as unidentified",
            "a handshake with only a name-based coffer/agent key reports no identity",
            expected="the scoped server's tools are not listed",
            actual={"lists_a": any(n.startswith(f"{A}__") for n in names_n)},
            ok=not any(n.startswith(f"{A}__") for n in names_n),
        )
        await _second_initialize(ctx)
    finally:
        await ctx.run.client.request("PUT", path, {"scope": None})


async def _second_initialize(ctx: Ctx) -> None:
    w = ctx.wire
    sid, _ = await w.initialize(AGENT_B)
    first = await w.call(sid, f"{A}__echo", {"text": "refused as B"})
    _, again = await w.initialize(AGENT_A, sid=sid)
    before = ctx.count(A)
    after = await w.call(sid, f"{A}__echo", {"text": "still refused"})
    calls = ctx.count(A) - before
    fresh, _ = await w.initialize(AGENT_A)
    fresh_reply = await w.call(fresh, f"{A}__echo", {"text": "new session as A"})
    ctx.rec.record(
        "a second initialize on a session changes nothing",
        "a session cannot change its identity with a second initialize",
        expected="first call -32000; second initialize -32600; the next call still -32000 with "
        "no upstream request; a new session as the scoped agent may call",
        actual={
            "first": first.body,
            "second_initialize": again.body,
            "after": after.body,
            "upstream": calls,
            "new_session_ok": ok(fresh_reply),
        },
        ok=code(first) == -32000
        and code(again) == -32600
        and code(after) == -32000
        and calls == 0
        and ok(fresh_reply),
        upstream=calls,
    )
