"""The catalogue: namespacing, routing, search, tiering and exposure, output
schemas, resources and prompts, list-changed notifications."""

from __future__ import annotations

import json

from e2e.installed._common.recorder import NA
from e2e.installed.mcp.context import Ctx
from e2e.installed.mcp.upstream import ECHO_OUTPUT_SCHEMA
from e2e.installed.mcp.wire import EventStream, code, in_band_error, ok, structured

A, B, HTTP = "qa-mcp-a", "qa-mcp-b", "qa-mcp-http"


async def run(ctx: Ctx) -> None:
    sid, _ = await ctx.wire.initialize("qa-agent-a")
    await _namespace_and_routing(ctx, sid)
    await _search(ctx, sid)
    await _output_schema(ctx, sid)
    await _results(ctx, sid)
    await _resources_prompts(ctx, sid)
    await _exposure(ctx, sid)
    await _list_changed(ctx, sid)


async def _namespace_and_routing(ctx: Ctx, sid: str) -> None:
    names = await ctx.wire.tool_names(sid)
    ctx.rec.record(
        "tool-name collision across servers is prevented",
        "two servers' echo are listed as qa-mcp-a__echo and qa-mcp-b__echo",
        expected="both prefixed names listed, no unprefixed echo, no duplicate names",
        actual={"qa_tools": sorted(n for n in names if n.startswith("qa-"))},
        ok={f"{A}__echo", f"{B}__echo"} <= set(names)
        and "echo" not in names
        and len(names) == len(set(names)),
    )
    routed = {}
    passed = True
    for tag in (A, B, HTTP):
        before = {t: ctx.count(t, name="echo") for t in (A, B, HTTP)}
        reply = await ctx.wire.call(sid, f"{tag}__echo", {"text": "qa route"})
        delta = {t: ctx.count(t, name="echo") - before[t] for t in (A, B, HTTP)}
        good = (
            structured(reply).get("tag") == tag
            and structured(reply).get("name") == "echo"
            and delta == {t: int(t == tag) for t in (A, B, HTTP)}
        )
        passed &= good
        routed[tag] = {"structured": structured(reply), "upstream_calls": delta}
    ctx.rec.record(
        "route a tool call to the correct upstream",
        "a prefixed call reaches only its own upstream, unprefixed, once",
        expected="each call answered by its own upstream (stdio a, stdio b, HTTP) and counted "
        "once there only",
        actual=routed,
        ok=passed,
        upstream={t: v["upstream_calls"] for t, v in routed.items()},
    )


async def _search(ctx: Ctx, sid: str) -> None:
    rec = ctx.rec
    reply = await ctx.wire.call(
        sid, "coffer__search_tools", {"query": "qa synthetic echo", "top_k": 5}
    )
    found = structured(reply).get("tools", [])
    rec.record(
        "B001",
        "coffer__search_tools returns at most top_k real upstream schemas",
        expected="1..5 results named <server>__<tool>, none coffer__, each with an inputSchema, "
        "and total_searched",
        actual=structured(reply),
        ok=ok(reply)
        and 0 < len(found) <= 5
        and all("__" in t["name"] and not t["name"].startswith("coffer__") for t in found)
        and all(isinstance(t.get("inputSchema"), dict) for t in found)
        and isinstance(structured(reply).get("total_searched"), int),
    )
    for cid, title, arguments in (
        ("B002", "search without a query is an in-band error", {}),
        ("B003", "a non-string query is an in-band error", {"query": 12}),
        (
            "B004",
            "an empty query with a negative top_k is an in-band error",
            {"query": "", "top_k": -1},
        ),
    ):
        reply = await ctx.wire.call(sid, "coffer__search_tools", arguments)
        rec.record(
            cid,
            title,
            expected="isError result or JSON-RPC -32602, never a crash",
            actual=reply.body,
            ok=in_band_error(reply) or code(reply) == -32602,
        )
    reply = await ctx.wire.call(sid, "coffer__search_tools", {"query": "echo", "top_k": 500})
    found = structured(reply).get("tools", [])
    rec.record(
        "B005",
        "top_k above the maximum is bounded to 20",
        expected="1..20 results",
        actual={"count": len(found)},
        ok=ok(reply) and 0 < len(found) <= 20,
    )


async def _output_schema(ctx: Ctx, sid: str) -> None:
    tools = {t["name"]: t for t in await ctx.wire.tools(sid)}
    searched = {
        t["name"]: t for t in await ctx.wire.search(sid, f"{A} qa synthetic echo image", 20)
    }
    reply = await ctx.wire.call(sid, f"{A}__echo", {"text": "qa schema"})
    upstream_payload = json.loads((reply.json.get("result") or {}).get("content", [{}])[0]["text"])
    typed_listed = tools.get(f"{A}__echo", {})
    plain_listed = tools.get(f"{A}__image", {})
    typed_found = searched.get(f"{A}__echo", {})
    plain_found = searched.get(f"{A}__image", {})
    ctx.rec.record(
        "pass an upstream tool's output schema through",
        "an upstream's outputSchema reaches the agent as declared, in the list and in search",
        expected="echo carries exactly the declared outputSchema in tools/list and search, image "
        "has no outputSchema key, and echo's structuredContent is what the upstream sent",
        actual={
            "listed": {
                "echo": typed_listed.get("outputSchema"),
                "image_keys": sorted(plain_listed),
            },
            "searched": {
                "echo": typed_found.get("outputSchema"),
                "image_keys": sorted(plain_found),
            },
            "structured_equals_upstream": structured(reply) == upstream_payload,
        },
        ok=bool(typed_listed and plain_listed and typed_found and plain_found)
        and typed_listed.get("outputSchema") == ECHO_OUTPUT_SCHEMA
        and typed_found.get("outputSchema") == ECHO_OUTPUT_SCHEMA
        and "outputSchema" not in plain_listed
        and "outputSchema" not in plain_found
        and structured(reply) == upstream_payload,
    )


async def _results(ctx: Ctx, sid: str) -> None:
    rec = ctx.rec
    reply = await ctx.wire.call(sid, f"{A}__business_error")
    rec.record(
        "D002",
        "an upstream's in-band tool error is passed through as isError",
        expected="result.isError true with the upstream's text",
        actual=reply.body,
        ok=in_band_error(reply) and "fixture business rejection" in json.dumps(reply.body),
    )
    reply = await ctx.wire.call(sid, f"{A}__image")
    content = (reply.json.get("result") or {}).get("content", [])
    rec.record(
        "D004",
        "image content is relayed intact",
        expected="first content item type image, png, same data",
        actual=content,
        ok=ok(reply)
        and bool(content)
        and content[0].get("type") == "image"
        and content[0].get("data") == "iVBORw0KGgo=",
    )
    reply = await ctx.wire.call(sid, f"{A}__large", {"n": 131072})
    rec.record(
        "D005",
        "a 128 KiB upstream result is relayed intact",
        expected="structuredContent.data is 131072 characters",
        actual={"bytes": len(json.dumps(reply.body))},
        ok=ok(reply) and len(structured(reply).get("data", "")) == 131072,
    )
    reply = await ctx.run.client.request(
        "PATCH", f"/api/v1/resources/{ctx.uid(A)}", {"name": "qa-mcp-renamed"}
    )
    rec.record(
        "D006",
        "an MCP server's name (its namespace) cannot be changed",
        expected="HTTP 409 NAME_IMMUTABLE",
        actual=[reply.status, reply.body],
        ok=reply.status == 409,
    )
    await ctx.register("qa-mcp-page", ctx.stdio("qa-mcp-page", "paged"))
    found = await ctx.wire.search(sid, "qa-mcp-page qa synthetic roots", 20)
    ctx.note_pids("qa-mcp-page")
    rec.record(
        "D007",
        "an upstream's second page of tools is read",
        expected="qa-mcp-page__roots (only on page two) is found by search",
        actual=[t["name"] for t in found],
        ok=any(t["name"] == "qa-mcp-page__roots" for t in found),
    )
    reply = await ctx.wire.rpc("tools/list", {"cursor": "qa-invalid"}, sid)
    rec.record(
        "D008",
        "observation: tools/list with an unknown string cursor",
        expected="unspecified by the contract; recorded only",
        actual={
            "http": reply.status,
            "error": reply.json.get("error"),
            "tools": len((reply.json.get("result") or {}).get("tools", [])),
        },
        status=NA,
    )


async def _resources_prompts(ctx: Ctx, sid: str) -> None:
    w, rec = ctx.wire, ctx.rec
    listed = await w.rpc("resources/list", {}, sid)
    uris = [r.get("uri") for r in (listed.json.get("result") or {}).get("resources", [])]
    reads = {}
    for tag in (A, B):
        reply = await w.rpc("resources/read", {"uri": f"coffer://{tag}/qa://same"}, sid)
        contents = (reply.json.get("result") or {}).get("contents", [{}])
        reads[tag] = {"text": contents[0].get("text"), "uri": contents[0].get("uri")}
    rec.record(
        "resources forward through the gateway",
        "a coffer:// resource URI is read from its own upstream",
        expected="both servers' qa://same listed under coffer://<server>/, each read answered by "
        "its own upstream",
        actual={"listed": uris, "reads": reads},
        ok={f"coffer://{A}/qa://same", f"coffer://{B}/qa://same"} <= set(uris)
        and all(reads[t]["text"] == t for t in (A, B)),
    )
    listed = await w.rpc("prompts/list", {}, sid)
    names = [p.get("name") for p in (listed.json.get("result") or {}).get("prompts", [])]
    gets = {}
    for tag in (A, B):
        reply = await w.rpc(
            "prompts/get", {"name": f"{tag}__same", "arguments": {"text": "hi"}}, sid
        )
        messages = (reply.json.get("result") or {}).get("messages", [{}])
        gets[tag] = messages[0].get("content", {}).get("text")
    rec.record(
        "prompts forward through the gateway",
        "a <server>__<prompt> is fetched from its own upstream under its own name",
        expected="both prompts listed prefixed; each get answered <tag>:hi",
        actual={"listed": names, "gets": gets},
        ok={f"{A}__same", f"{B}__same"} <= set(names) and gets == {A: f"{A}:hi", B: f"{B}:hi"},
    )
    reply = await w.rpc("resources/templates/list", {}, sid)
    rec.record(
        "R002",
        "an optional method is answered by the JSON-RPC rules",
        expected="HTTP 200 with a result or JSON-RPC -32601, never a 500",
        actual=[reply.status, reply.body],
        ok=reply.status == 200 and ("result" in reply.json or code(reply) == -32601),
    )


async def _exposure(ctx: Ctx, sid: str) -> None:
    rec = ctx.rec
    for cid, mode in (("E001", "search"), ("E002", "listed"), ("E003", "auto")):
        status = await ctx.expose(B, ["image"], mode)
        listed = f"{B}__image" in await ctx.wire.tool_names(sid)
        found = any(t["name"] == f"{B}__image" for t in await ctx.wire.search(sid, f"{B} image"))
        called = await ctx.wire.call(sid, f"{B}__image")
        expect_listed = {"search": False, "listed": True}.get(mode)
        rec.record(
            cid,
            f"exposure {mode}: only how the tool is listed changes, never whether it is callable",
            expected={
                "search": "not listed, found by search, callable",
                "listed": "listed, callable",
                "auto": "callable (listing left to the budget)",
            }[mode],
            actual={"set": status, "listed": listed, "searched": found, "called": ok(called)},
            ok=status in (200, 204)
            and ok(called)
            and (expect_listed is None or listed == expect_listed)
            and (mode != "search" or found),
        )
    reply = await ctx.run.client.request(
        "GET", f"/api/v1/resources/mcp_server/{ctx.uid(B)}/tiering"
    )
    rows = {r.get("tool"): r for r in reply.json.get("tools", [])}
    echo = rows.get("echo", {})
    rec.record(
        "E004",
        "the tiering read reports each tool's exposure",
        expected="echo reported mode listed, effective listed, reason pinned",
        actual={"http": reply.status, "echo": echo, "tool_count": reply.json.get("tool_count")},
        ok=reply.status == 200
        and echo.get("mode") == "listed"
        and echo.get("effective") == "listed"
        and echo.get("reason") == "pinned",
    )
    await ctx.expose(B, ["image"], "listed")


async def _list_changed(ctx: Ctx, sid: str) -> None:
    async with EventStream(ctx.wire, sid, seconds=20) as stream:
        await ctx.wire.call(sid, f"{A}__mutate")
        await stream.settle(1.0)
    methods = stream.methods()
    found = await ctx.wire.search(sid, f"{A} added", 20)
    ctx.rec.record(
        "upstream tool list changes mid-session",
        "an upstream's list-changed notifications reach the session and the catalogue refreshes",
        expected="tools, resources and prompts list_changed on the session's stream; search then "
        "finds the new qa-mcp-a__added",
        actual={"stream": methods, "found": [t["name"] for t in found]},
        ok=all(
            f"notifications/{k}/list_changed" in methods for k in ("tools", "resources", "prompts")
        )
        and any(t["name"] == f"{A}__added" for t in found),
    )
    async with EventStream(ctx.wire, sid, seconds=10) as stream:
        await ctx.wire.call(sid, f"{A}__progress", meta={"progressToken": "qa-progress"})
        await stream.settle(0.5)
    ctx.rec.record(
        "N003",
        "observation: upstream progress notifications",
        expected="not promised by the contract; recorded only",
        actual={
            "progress": [m for m in stream.messages if m.get("method") == "notifications/progress"]
        },
        status=NA,
    )
