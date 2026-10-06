"""The /mcp endpoint by the JSON-RPC and MCP 2025-06-18 rules: envelope, codes,
session lifecycle, protocol header, version fallback, local auth."""

from __future__ import annotations

import json
from typing import Any

from e2e.installed._common.recorder import NA
from e2e.installed.mcp.context import Ctx
from e2e.installed.mcp.wire import CLIENT_INFO, PROTOCOL, EventStream, code, ok, text_of


async def _get_status(ctx: Ctx, headers: dict[str, str | None]) -> int:
    """Status of a ``GET /mcp`` without waiting on a stream that may open."""
    sent: dict[str, str | None] = {"Accept": "text/event-stream", **headers}
    async with ctx.wire.client.stream("GET", "/mcp", headers=sent, timeout=5) as response:
        return response.status_code


async def run(ctx: Ctx) -> None:
    w, rec = ctx.wire, ctx.rec
    sid, init = await w.initialize("qa-agent-a")
    result = init.json.get("result") or {}
    rec.record(
        "P001",
        "initialize answers MCP 2025-06-18 with tools, resources, prompts and instructions",
        expected="protocolVersion 2025-06-18, the three capabilities, an instructions string, "
        "an Mcp-Session-Id header",
        actual={"result": result, "session_header": bool(sid)},
        ok=result.get("protocolVersion") == PROTOCOL
        and {"tools", "resources", "prompts"} <= set(result.get("capabilities") or {})
        and isinstance(result.get("instructions"), str)
        and bool(sid),
    )
    reply = await w.rpc("ping", {}, sid, rid="qa-string-id")
    rec.record(
        "P002",
        "ping answers an empty result under the request's own string id",
        expected='{"jsonrpc":"2.0","id":"qa-string-id","result":{}}',
        actual=reply.body,
        ok=reply.body == {"jsonrpc": "2.0", "id": "qa-string-id", "result": {}},
    )
    reply = await w.rpc("ping", {}, sid, rid=None)
    rec.record(
        "P003",
        "a notification is answered with an empty 202",
        expected="HTTP 202, empty body",
        actual=[reply.status, reply.body],
        ok=reply.status == 202 and reply.body == "",
    )
    await _malformed(ctx)
    await _sessions(ctx, sid)
    await _versions(ctx, sid)
    await _codes(ctx, sid)
    await _builtins(ctx, sid)
    await _auth(ctx, sid)


async def _malformed(ctx: Ctx) -> None:
    w = ctx.wire
    init_without_version = {"capabilities": {}, "clientInfo": CLIENT_INFO}
    messages: list[tuple[str, Any, int, Any]] = [
        ("no method", {"jsonrpc": "2.0", "id": 3}, -32600, 3),
        ("jsonrpc 1.0", {"jsonrpc": "1.0", "id": 3, "method": "ping"}, -32600, 3),
        ("array id", {"jsonrpc": "2.0", "id": [], "method": "ping"}, -32600, None),
        ("null id", {"jsonrpc": "2.0", "id": None, "method": "ping"}, -32600, None),
        ("not an object", [], -32600, None),
        ("a string", "qa", -32600, None),
        (
            "initialize params array",
            {"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": ["qa"]},
            -32602,
            3,
        ),
        (
            "initialize without protocolVersion",
            {"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": init_without_version},
            -32602,
            3,
        ),
        (
            "initialize empty params",
            {"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {}},
            -32602,
            3,
        ),
    ]
    seen = []
    passed = True
    for label, body, want, want_id in messages:
        reply = await w.post(body)
        good = (
            reply.status == 200
            and code(reply) == want
            and reply.json.get("id") == want_id
            and "mcp-session-id" not in reply.headers
        )
        passed &= good
        seen.append({"message": label, "http": reply.status, "body": reply.body, "ok": good})
    ctx.rec.record(
        "a malformed message gets its JSON-RPC error",
        "malformed messages: no method, jsonrpc 1.0, bad ids, bad initialize params",
        expected="HTTP 200, -32600/-32602, the id echoed only when valid (else null), no session",
        actual=seen,
        ok=passed,
    )
    reply = await w.post(None, content="{qa-not-json", headers={"Content-Type": "application/json"})
    ctx.rec.record(
        "P031",
        "a body that is not JSON is HTTP 400 with -32700",
        expected="HTTP 400, JSON-RPC -32700",
        actual=[reply.status, reply.body],
        ok=reply.status == 400 and code(reply) == -32700,
    )


async def _sessions(ctx: Ctx, sid: str) -> None:
    w, rec = ctx.wire, ctx.rec
    listing = await w.rpc("tools/list", {})
    note = await w.notify("notifications/initialized", {}, None)
    rec.record(
        "only initialize opens a session",
        "tools/list or a notification without Mcp-Session-Id is refused",
        expected="each HTTP 400, no Mcp-Session-Id issued",
        actual=[[listing.status, listing.body], [note.status, note.body]],
        ok=listing.status == 400
        and note.status == 400
        and "mcp-session-id" not in listing.headers
        and "mcp-session-id" not in note.headers,
    )
    reply = await w.rpc("ping", {}, "qa-nonexistent-session")
    rec.record(
        "P017",
        "an unknown session id is answered 404",
        expected="HTTP 404",
        actual=[reply.status, reply.body],
        ok=reply.status == 404,
    )
    no_session = await _get_status(ctx, {})
    unknown = await _get_status(ctx, {"Mcp-Session-Id": "qa-unknown"})
    rec.record(
        "P021",
        "GET /mcp without a session is 400 and with an unknown one 404",
        expected="400, 404",
        actual=[no_session, unknown],
        ok=no_session == 400 and unknown == 404,
    )
    reply = await w.client.request("DELETE", "/mcp", headers={"Mcp-Session-Id": sid})
    rec.record(
        "P023",
        "DELETE /mcp (explicit session termination) is answered 405",
        expected="HTTP 405 — the spec lets a server refuse explicit termination",
        actual=reply.status,
        ok=reply.status == 405,
    )
    ping1 = await w.rpc("ping", {}, sid)
    async with EventStream(ctx.wire, sid, seconds=5):
        pass
    ping2 = await w.rpc("ping", {}, sid)
    rec.record(
        "P024",
        "a session stays usable across opening and closing its notification stream",
        expected="ping answers before and after the stream",
        actual=[ping1.body, ping2.body],
        ok=ok(ping1) and ok(ping2),
    )
    for cid, header in (
        ("P019", {"Accept": "text/plain"}),
        ("P020", {"Content-Type": "text/plain"}),
    ):
        reply = await w.rpc("ping", {}, sid, headers=header)
        rec.record(
            cid,
            f"observation: ping with {header}",
            expected="not part of Coffer's contract; recorded only",
            actual=[reply.status, reply.body],
            status=NA,
        )


async def _versions(ctx: Ctx, sid: str) -> None:
    w, rec = ctx.wire, ctx.rec
    answers = {}
    for name, value in (
        ("agreed", PROTOCOL),
        ("none", None),
        ("qa-invalid", "qa-invalid"),
        ("2024-11-05", "2024-11-05"),
    ):
        reply = await w.rpc("ping", {}, sid, headers={"MCP-Protocol-Version": value})
        answers[name] = reply.status
    answers["stream qa-invalid"] = await _get_status(
        ctx, {"Mcp-Session-Id": sid, "MCP-Protocol-Version": "qa-invalid"}
    )
    rec.record(
        "an unsupported MCP-Protocol-Version header is refused",
        "the protocol header after the handshake: agreed and absent answered, others 400",
        expected="agreed 200, none 200, qa-invalid 400, 2024-11-05 400, stream qa-invalid 400",
        actual=answers,
        ok=answers
        == {
            "agreed": 200,
            "none": 200,
            "qa-invalid": 400,
            "2024-11-05": 400,
            "stream qa-invalid": 400,
        },
    )
    fallback = {}
    for version in ("2024-11-05", "2025-11-25", "qa-unsupported"):
        _, reply = await w.initialize("qa-agent-a", version=version)
        fallback[version] = (reply.json.get("result") or {}).get("protocolVersion")
    rec.record(
        "P-V",
        "initialize asking for another version is answered 2025-06-18",
        expected="every answer names 2025-06-18",
        actual=fallback,
        ok=set(fallback.values()) == {PROTOCOL},
    )


async def _codes(ctx: Ctx, sid: str) -> None:
    w, rec = ctx.wire, ctx.rec
    a = "qa-mcp-a"
    unknown_method = await w.rpc("qa/unknown", {}, sid)
    no_server = await w.call(sid, "qa-no-server__echo", {"text": "x"})
    before = ctx.count(a)
    wrong_type = await w.call(sid, f"{a}__echo", {"text": 7})
    # Switched off for good: qa-mcp-b's secret_echo is used by no other case.
    off = "qa-mcp-b"
    await ctx.toggle(off, "secret_echo", False)
    before_disabled = ctx.count(off, name="secret_echo")
    disabled = await w.call(sid, f"{off}__secret_echo")
    disabled_calls = ctx.count(off, name="secret_echo") - before_disabled
    message = json.dumps(wrong_type.json.get("error"))
    rec.record(
        "each failure keeps its own JSON-RPC code",
        "unknown method, tool of no server, wrong argument type, switched-off tool",
        expected="-32601, -32602, -32602 without the upstream's text, -32000 with no upstream "
        "request",
        actual={
            "unknown_method": unknown_method.body,
            "no_server": no_server.body,
            "wrong_type": wrong_type.body,
            "disabled": disabled.body,
            "disabled_upstream_calls": disabled_calls,
        },
        ok=code(unknown_method) == -32601
        and code(no_server) == -32602
        and code(wrong_type) == -32602
        and "fixture says" not in message
        and code(disabled) == -32000
        and disabled_calls == 0,
        upstream={"wrong_type": ctx.count(a) - before, "disabled": disabled_calls},
    )
    for cid, title, params in (
        ("P005", "tools/call without a name is -32602", {}),
        ("P007", "an unknown tool of a known server is -32602", {"name": f"{a}__qa-unknown"}),
    ):
        reply = await w.rpc("tools/call", params, sid)
        rec.record(
            cid, title, expected="JSON-RPC -32602", actual=reply.body, ok=code(reply) == -32602
        )
    reply = await w.call(sid, f"{a}__rpc_error")
    rec.record(
        "D003",
        "an upstream's own JSON-RPC error keeps its code with Coffer's own message",
        expected="-32602, and the upstream's text is not forwarded",
        actual=reply.body,
        ok=code(reply) == -32602 and "fixture intentional" not in json.dumps(reply.body),
    )


async def _builtins(ctx: Ctx, sid: str) -> None:
    w, rec = ctx.wire, ctx.rec
    names = await w.tool_names(sid)
    unknown = await w.call(sid, "coffer__nosuchtool", {})
    same = {}
    for name, arguments in (
        ("coffer__write", {"collection": "x", "title": "t", "description": "d"}),
        ("coffer__recall", {"query": "x"}),
        ("coffer__diagnose", {"since_minutes": 5}),
    ):
        reply = await w.call(sid, name, arguments)
        same[name] = json.dumps(reply.body).replace(name, "coffer__nosuchtool") == json.dumps(
            unknown.body
        )
    builtins = sorted(n for n in names if n.startswith("coffer__"))
    rec.record(
        "advertise coffer__search_tools as the one built-in tool",
        "the only built-in listed is coffer__search_tools; removed ones answer as unknown",
        expected="coffer__ tools listed == [coffer__search_tools]; three removed names answered "
        "exactly like an unknown tool",
        actual={"builtins": builtins, "answered_as_unknown": same, "unknown": unknown.body},
        ok=builtins == ["coffer__search_tools"] and all(same.values()),
    )
    reply = await w.call(sid, "coffer__ask", {"questions": []})
    said = text_of(reply) + json.dumps(reply.json.get("error"))
    rec.record(
        "coffer__ask is not offered outside a Coffer turn",
        "coffer__ask outside a Coffer turn: not listed, and a call says why",
        expected="not in tools/list; the call fails saying it works only inside a Coffer "
        "conversation",
        actual={"listed": "coffer__ask" in names, "reply": reply.body},
        ok="coffer__ask" not in names and not ok(reply) and "Coffer conversation" in said,
    )


async def _auth(ctx: Ctx, sid: str) -> None:
    for cid, title, header in (
        ("A005", "an empty token is refused", {"X-Coffer-Token": ""}),
        ("A006", "a wrong token is refused", {"X-Coffer-Token": "qa-wrong-token"}),
        ("A007", "a foreign Origin is refused", {"Origin": "https://qa-attacker.invalid"}),
        ("A008", "a foreign Host is refused", {"Host": "qa-attacker.invalid"}),
    ):
        reply = await ctx.wire.rpc("ping", {}, sid, headers=header)
        ctx.rec.record(
            cid,
            title,
            expected="HTTP 401 or 403",
            actual=[reply.status, reply.body],
            ok=reply.status in (401, 403),
        )
