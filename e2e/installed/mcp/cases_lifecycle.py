"""Cancellation, request-id reuse, upstream faults and timeouts, crash recovery,
and a deleted server leaving no child behind."""

from __future__ import annotations

import asyncio
import time

import httpx

from e2e.installed._common.processes import wait_gone
from e2e.installed.mcp.context import Ctx
from e2e.installed.mcp.wire import code, ok

A = "qa-mcp-a"


async def run(ctx: Ctx) -> None:
    await _cancel(ctx)
    await _in_flight_id(ctx)
    await _unknown_cancel(ctx)
    await _dropped_connection(ctx)
    await _crash(ctx)
    await _timeout(ctx)
    await _launch_failures(ctx)
    await _http_faults(ctx)
    await _delete_leaves_no_child(ctx)


async def _cancel(ctx: Ctx) -> None:
    w = ctx.wire
    one, _ = await w.initialize("qa-agent-a")
    two, _ = await w.initialize("qa-agent-a")
    for sid in (one, two):  # spawn each session's own child before timing anything
        await w.call(sid, f"{A}__echo", {"text": "warm"})
    starts = ctx.count(A, name="slow")
    cancelled = ctx.count(A, "cancelled", "slow")
    done = ctx.count(A, "done", "slow")
    t0 = time.perf_counter()
    first = asyncio.create_task(
        w.call(one, f"{A}__slow", {"delay": 4}, rid="qa-cancel", timeout=20)
    )
    second = asyncio.create_task(
        w.call(two, f"{A}__slow", {"delay": 4}, rid="qa-cancel", timeout=20)
    )
    await ctx.wait_count(A, starts + 2, name="slow")
    note = await w.notify(
        "notifications/cancelled", {"requestId": "qa-cancel", "reason": "qa"}, one
    )
    first_reply = await first
    first_s = time.perf_counter() - t0
    second_reply = await second
    await ctx.wait_count(A, done + 1, "done", "slow", timeout=5)
    ledger = {
        "start": ctx.count(A, name="slow") - starts,
        "cancelled": ctx.count(A, "cancelled", "slow") - cancelled,
        "done": ctx.count(A, "done", "slow") - done,
    }
    ctx.rec.record(
        "a cancelled request stops upstream once and is not answered",
        "two sessions run a slow call under the same id; one cancels",
        expected="cancel 202; the cancelled call answered with an empty 202 well before 4 s; the "
        "other completes; the upstream records 2 starts, 1 cancellation, 1 completion",
        actual={
            "cancel_notification": note.status,
            "cancelled_call": [first_reply.status, first_reply.body, round(first_s, 2)],
            "other_call_ok": ok(second_reply),
            "ledger": ledger,
        },
        ok=note.status == 202
        and first_reply.status == 202
        and first_reply.body == ""
        and first_s < 3
        and ok(second_reply)
        and ledger == {"start": 2, "cancelled": 1, "done": 1},
        upstream=ledger,
    )


async def _in_flight_id(ctx: Ctx) -> None:
    w = ctx.wire
    sid, _ = await w.initialize("qa-agent-a")
    await w.call(sid, f"{A}__echo", {"text": "warm"})
    starts = ctx.count(A, name="slow")
    echoes = ctx.count(A, name="echo")
    task = asyncio.create_task(w.call(sid, f"{A}__slow", {"delay": 1.5}, rid="qa-dup", timeout=20))
    await ctx.wait_count(A, starts + 1, name="slow")
    reused = await w.call(sid, f"{A}__echo", {"text": "reused id"}, rid="qa-dup")
    original = await task
    ctx.rec.record(
        "L014",
        "a request id still in flight in a session is not used again",
        expected="the second request is -32600 and never runs; the first completes",
        actual={
            "reused": reused.body,
            "original_ok": ok(original),
            "echo_upstream_calls": ctx.count(A, name="echo") - echoes,
        },
        ok=code(reused) == -32600 and ok(original) and ctx.count(A, name="echo") == echoes,
        upstream={"echo": ctx.count(A, name="echo") - echoes},
    )


async def _unknown_cancel(ctx: Ctx) -> None:
    sid, _ = await ctx.wire.initialize("qa-agent-a")
    note = await ctx.wire.notify("notifications/cancelled", {"requestId": "qa-never-seen"}, sid)
    ping = await ctx.wire.rpc("ping", {}, sid)
    ctx.rec.record(
        "L015",
        "a cancellation for an id never seen is accepted and changes nothing",
        expected="202, and the session still answers",
        actual=[note.status, ping.body],
        ok=note.status == 202 and ok(ping),
    )


async def _dropped_connection(ctx: Ctx) -> None:
    sid, _ = await ctx.wire.initialize("qa-agent-a")
    await ctx.wire.call(sid, f"{A}__echo", {"text": "warm"})
    marker = {"delay": 1.5, "text": "qa-dropped-connection"}
    dropped = False
    try:
        await ctx.wire.call(sid, f"{A}__slow", marker, rid="qa-drop", timeout=0.5)
    except httpx.TimeoutException:
        dropped = True
    await asyncio.sleep(2.5)
    done = [e for e in ctx.events(A, "done", "slow") if e.get("arguments") == marker]
    cancelled = [e for e in ctx.events(A, "cancelled", "slow") if e.get("arguments") == marker]
    ctx.rec.record(
        "L016",
        "a dropped HTTP connection is not a cancellation",
        expected="the client gives up; the upstream still runs the call to its end",
        actual={"client_dropped": dropped, "done": len(done), "cancelled": len(cancelled)},
        ok=dropped and len(done) == 1 and not cancelled,
    )


async def _crash(ctx: Ctx) -> None:
    sid, _ = await ctx.wire.initialize("qa-agent-a")
    await ctx.wire.call(sid, f"{A}__echo", {"text": "warm"})
    crashed = await ctx.wire.call(sid, f"{A}__crash", timeout=30)
    after = await ctx.wire.call(sid, f"{A}__echo", {"text": "after crash"}, timeout=30)
    ctx.note_pids(A)
    ctx.rec.record(
        "upstream crash recovery",
        "the upstream dies mid-call; the next call respawns it",
        expected="the crashing call is an error; the next call succeeds",
        actual={"crash": crashed.body, "after": after.body},
        ok=("error" in crashed.json or crashed.json.get("result", {}).get("isError") is True)
        and ok(after),
    )


async def _timeout(ctx: Ctx) -> None:
    await ctx.register("qa-mcp-timeout", ctx.stdio("qa-mcp-timeout"), request_timeout_seconds=5)
    sid, _ = await ctx.wire.initialize("qa-agent-a")
    t0 = time.perf_counter()
    reply = await ctx.wire.call(sid, "qa-mcp-timeout__slow", {"delay": 8}, timeout=30)
    elapsed = time.perf_counter() - t0
    ctx.note_pids("qa-mcp-timeout")
    calls = ctx.count("qa-mcp-timeout", name="slow")
    ctx.rec.record(
        "L005",
        "an upstream past its request timeout is answered -32603, once",
        expected="-32603 after about 5 s (before the 8 s call ends), one upstream request",
        actual={"reply": reply.body, "seconds": round(elapsed, 2)},
        ok=code(reply) == -32603 and elapsed < 8 and calls == 1,
        upstream=calls,
    )


async def _launch_failures(ctx: Ctx) -> None:
    missing_cwd = ctx.run.out / "qa-missing-dir"
    for cid, name, transport, tolerated in (
        ("L006", "qa-mcp-no-command", {"type": "stdio", "command": "/qa-mcp-missing"}, False),
        ("L007", "qa-mcp-no-cwd", ctx.stdio("qa-mcp-no-cwd", cwd=missing_cwd), False),
        ("L008", "qa-mcp-exit", ctx.stdio("qa-mcp-exit", "exit"), False),
        ("L009", "qa-mcp-stdout", ctx.stdio("qa-mcp-stdout", "pollute"), True),
        ("L010", "qa-mcp-json", ctx.stdio("qa-mcp-json", "invalid-json"), True),
    ):
        server = await ctx.register(name, transport, spawn_timeout_seconds=5)
        sid, _ = await ctx.wire.initialize("qa-agent-a")
        t0 = time.perf_counter()
        reply = await ctx.wire.call(sid, f"{name}__echo", {"text": "qa"}, timeout=60)
        elapsed = time.perf_counter() - t0
        ctx.note_pids(name)
        deleted = await ctx.run.api.delete_resource(server["uid"])
        ctx.rec.record(
            cid,
            f"an upstream that cannot start or speaks bad wire ({name}) fails boundedly",
            expected="a JSON-RPC error within the spawn timeout"
            + (" (or a tolerated success past one bad stdout line)" if tolerated else ""),
            actual={"reply": reply.body, "seconds": round(elapsed, 2), "deleted": deleted.status},
            ok=("error" in reply.json or (tolerated and ok(reply))) and elapsed < 30,
        )


async def _http_faults(ctx: Ctx) -> None:
    port = ctx.http["qa-mcp-http"]["port"]
    for cid, name, suffix in (
        ("X012", "qa-mcp-fault-status", "/status/503"),
        ("X013", "qa-mcp-fault-drop", "/disconnect"),
    ):
        server = await ctx.register(
            name,
            {"type": "http", "url": f"http://127.0.0.1:{port}{suffix}"},
            spawn_timeout_seconds=5,
        )
        sid, _ = await ctx.wire.initialize("qa-agent-a")
        t0 = time.perf_counter()
        reply = await ctx.wire.call(sid, f"{name}__echo", {"text": "qa"}, timeout=90)
        elapsed = time.perf_counter() - t0
        deleted = await ctx.run.api.delete_resource(server["uid"])
        ctx.rec.record(
            cid,
            f"an HTTP upstream that answers {suffix} fails boundedly",
            expected="a JSON-RPC error, no hang",
            actual={"reply": reply.body, "seconds": round(elapsed, 2), "deleted": deleted.status},
            ok="error" in reply.json,
        )


async def _delete_leaves_no_child(ctx: Ctx) -> None:
    name = "qa-mcp-delete"
    server = await ctx.register(name, ctx.stdio(name))
    sessions = [(await ctx.wire.initialize("qa-agent-a"))[0] for _ in range(2)]
    for sid in sessions:
        await ctx.wire.call(sid, f"{name}__echo", {"text": "spawn"})
    pids = ctx.note_pids(name)
    deleted = await ctx.run.api.delete_resource(server["uid"])
    alive = await wait_gone(pids, 10)
    after = await ctx.wire.call(sessions[0], f"{name}__echo", {"text": "after delete"})
    ctx.rec.record(
        "L011",
        "deleting a server leaves no child of it in any session",
        expected="two sessions' children (by pid) exit after the delete; a later call is -32602",
        actual={
            "pids": sorted(pids),
            "deleted": deleted.status,
            "still_alive": alive,
            "after": after.body,
        },
        ok=deleted.status == 204 and len(pids) >= 2 and not alive and code(after) == -32602,
    )
