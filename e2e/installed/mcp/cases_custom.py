"""Custom HTTP tools: environments chosen per call, argument validation before any
request, error statuses and redirects, mixed-case environment management.

Every request goes to the runner's own echo receiver; its ledger (``http``
events) is the count of what really reached the API.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from e2e.installed.mcp.context import Ctx
from e2e.installed.mcp.wire import code, in_band_error, ok, text_of

GROUP, ENVCASE, HTTP = "qa-mcp-custom", "qa-mcp-envcase", "qa-mcp-http"
RENDER_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "q": {"type": "string"},
        "region": {"type": "string", "enum": ["sg", "ph"]},
    },
    "required": ["id", "q"],
    "additionalProperties": False,
}


def _base(ctx: Ctx, path: str) -> str:
    return f"http://127.0.0.1:{ctx.http[HTTP]['port']}{path}"


def _received(ctx: Ctx) -> list[dict[str, Any]]:
    return ctx.events(HTTP, "http")


def _refusal(reply: Any) -> str:
    """The text of a refusal, in-band or JSON-RPC."""
    return text_of(reply) + json.dumps(reply.json.get("error"))


async def run(ctx: Ctx) -> None:
    group = {
        "name": GROUP,
        "description": "qa synthetic custom tools",
        "timeout_seconds": 5,
        "environments": [
            {
                "name": "test",
                "base_url": _base(ctx, "/test"),
                "variables": {"CID": "sg"},
                "headers": [{"name": "X-Env", "value": "test"}],
                "timeout_seconds": 2,
            },
            {
                "name": "uat",
                "base_url": _base(ctx, "/uat"),
                "variables": {"CID": "ph"},
                "headers": [{"name": "X-Env", "value": "uat"}],
                "timeout_seconds": 1,
            },
            {"name": "live", "base_url": _base(ctx, "/live"), "enabled": False},
        ],
        "tools": [
            {
                "name": "render",
                "method": "POST",
                "path": "/echo/{id}?cid={env:CID}&q={q}",
                "headers": {"X-Arg": "{id}"},
                "body_template": '{"id":"{id}","cid":"{env:CID}"}',
                "input_schema": RENDER_SCHEMA,
            },
            {"name": "slow", "method": "GET", "path": "/slow"},
            {"name": "large", "method": "GET", "path": "/large"},
            {"name": "missing", "method": "GET", "path": "/status/404"},
            {
                "name": "redirect",
                "method": "GET",
                "path": "/redirect?to={to}",
                "input_schema": {
                    "type": "object",
                    "properties": {"to": {"type": "string"}},
                    "required": ["to"],
                },
            },
            {"name": "disabled", "method": "GET", "path": "/echo", "enabled": False},
        ],
    }
    reply = await ctx.run.api.create_group(group)
    if reply.status != 201:
        raise RuntimeError(f"creating {GROUP}: HTTP {reply.status} {reply.body}")
    ctx.servers[GROUP] = reply.json
    sid, _ = await ctx.wire.initialize("qa-agent-a")
    await _schema(ctx, sid)
    await _environments(ctx, sid)
    await _refusals(ctx, sid)
    await _responses(ctx, sid)
    await _concurrent(ctx, sid)
    await _mixed_case(ctx, sid)
    await _unsaved_private(ctx)


async def _render_schema(ctx: Ctx, sid: str, group: str, tool: str) -> dict[str, Any]:
    found = await ctx.wire.search(sid, f"{group} {tool}", 20)
    entry = next((t for t in found if t["name"] == f"{group}__{tool}"), {})
    return dict(entry.get("inputSchema") or {})


async def _schema(ctx: Ctx, sid: str) -> None:
    schema = await _render_schema(ctx, sid, GROUP, "render")
    selector = (schema.get("properties") or {}).get("coffer_environment", {})
    bad = {
        "name": "qa-mcp-reserved",
        "base_url": _base(ctx, "/reserved"),
        "tools": [
            {
                "name": "t",
                "method": "GET",
                "path": "/echo",
                "input_schema": {
                    "type": "object",
                    "properties": {"coffer_environment": {"type": "string"}},
                },
            }
        ],
    }
    refused = await ctx.run.api.create_group(bad)
    ctx.rec.record(
        "the advertised schema offers only enabled environments",
        "coffer_environment is a required enumeration of the enabled environments",
        expected="required, enum [test, uat] (live is off); a tool declaring coffer_environment "
        "itself is refused when saved",
        actual={
            "selector": selector,
            "required": schema.get("required"),
            "reserved_tool_save": [refused.status, refused.body],
        },
        ok="coffer_environment" in (schema.get("required") or [])
        and sorted(selector.get("enum") or []) == ["test", "uat"]
        and 400 <= refused.status < 500,
    )


async def _environments(ctx: Ctx, sid: str) -> None:
    seen = {}
    passed = True
    for env, cid in (("test", "sg"), ("uat", "ph")):
        before = len(_received(ctx))
        reply = await ctx.wire.call(
            sid,
            f"{GROUP}__render",
            {"coffer_environment": env, "id": "a/b", "q": "x & y", "region": "sg"},
        )
        got = _received(ctx)[before:]
        hit = got[0] if got else {}
        good = (
            ok(reply)
            and text_of(reply).startswith("HTTP 200")
            and len(got) == 1
            and hit.get("path") == f"/{env}/echo/a%2Fb"
            and f"cid={cid}" in (hit.get("query") or "")
            and (hit.get("headers") or {}).get("x-env") == env
            and json.loads(hit.get("body") or "{}") == {"id": "a/b", "cid": cid}
            and "coffer_environment" not in json.dumps(hit)
        )
        passed &= good
        seen[env] = {"reply_head": text_of(reply)[:80], "received": hit}
    ctx.rec.record(
        "C002",
        "each environment's call reaches its own base URL with its own variable and header",
        expected="one request per call to /<env>/echo/a%2Fb with cid=<env's CID>, X-Env=<env>, "
        "the body template filled, and no coffer_environment anywhere in it",
        actual=seen,
        ok=passed,
        upstream=2,
    )


async def _refused_before_request(
    ctx: Ctx, sid: str, arguments: dict[str, Any], tool: str = "render"
) -> tuple[Any, int]:
    before = len(_received(ctx))
    reply = await ctx.wire.call(sid, f"{GROUP}__{tool}", arguments)
    return reply, len(_received(ctx)) - before


async def _refusals(ctx: Ctx, sid: str) -> None:
    rec = ctx.rec
    answers = {}
    sent = 0
    for label, env in (("UNKNOWN", "prod"), ("DISABLED", "live"), ("REQUIRED", None)):
        arguments: dict[str, Any] = {"id": "x", "q": "y"}
        if env:
            arguments["coffer_environment"] = env
        reply, n = await _refused_before_request(ctx, sid, arguments)
        sent += n
        answers[label] = _refusal(reply)[:300]
    rec.record(
        "an environment that is not registered or is off is refused before any request",
        "an unknown, a switched-off and a missing environment are each refused",
        expected="CUSTOM_TOOL_ENVIRONMENT_UNKNOWN, _DISABLED and _REQUIRED; zero requests",
        actual={"answers": answers, "requests": sent},
        ok=all(f"CUSTOM_TOOL_ENVIRONMENT_{k}" in v for k, v in answers.items()) and sent == 0,
        upstream=sent,
    )
    for cid, title, arguments in (
        ("C005", "a wrong argument type is refused before any request", {"id": 7, "q": "y"}),
        (
            "C006",
            "an enum violation is refused before any request",
            {"id": "x", "q": "y", "region": "xx"},
        ),
        (
            "C007",
            "an undeclared argument is refused before any request",
            {"id": "x", "q": "y", "note": "n"},
        ),
    ):
        reply, n = await _refused_before_request(
            ctx, sid, {"coffer_environment": "test", **arguments}
        )
        rec.record(
            cid,
            title,
            expected="CUSTOM_TOOL_ARGUMENTS_INVALID in-band; zero requests",
            actual={"reply": _refusal(reply)[:400], "requests": n},
            ok=in_band_error(reply)
            and "CUSTOM_TOOL_ARGUMENTS_INVALID" in _refusal(reply)
            and n == 0,
            upstream=n,
        )
    reply, n = await _refused_before_request(
        ctx, sid, {"coffer_environment": "test", "id": "x\r\nX-Fake: y", "q": "y"}
    )
    rec.record(
        "C004",
        "a header value with CR/LF is refused before any request",
        expected="an error; zero requests",
        actual={"reply": _refusal(reply)[:300], "requests": n},
        ok=(in_band_error(reply) or "error" in reply.json) and n == 0,
        upstream=n,
    )
    found = await ctx.wire.search(sid, f"{GROUP} disabled", 20)
    denied_before = (await ctx.invocations(GROUP, "denied")).get("total", 0)
    reply, n = await _refused_before_request(ctx, sid, {"coffer_environment": "test"}, "disabled")
    denied = (await ctx.invocations(GROUP, "denied")).get("total", 0) - denied_before
    rec.record(
        "a switched-off custom tool is hidden and refused",
        "a switched-off tool is not offered and its call is refused",
        expected="absent from search; the call is -32000 (TOOL_DISABLED), recorded denied; zero "
        "requests",
        actual={
            "searched": [t["name"] for t in found],
            "reply": reply.body,
            "denied": denied,
            "requests": n,
        },
        ok=not any(t["name"] == f"{GROUP}__disabled" for t in found)
        and code(reply) == -32000
        and denied == 1
        and n == 0,
        upstream=n,
    )


async def _responses(ctx: Ctx, sid: str) -> None:
    rec, w = ctx.rec, ctx.wire
    reply = await w.call(sid, f"{GROUP}__slow", {"coffer_environment": "uat"}, timeout=30)
    rec.record(
        "C009",
        "a custom tool past its environment's timeout is an error",
        expected="an error result within about 1 s (uat's timeout)",
        actual={"reply": _refusal(reply)[:300], "ms": round(reply.elapsed_ms)},
        ok=(in_band_error(reply) or "error" in reply.json) and reply.elapsed_ms < 2900,
    )
    reply = await w.call(sid, f"{GROUP}__large", {"coffer_environment": "test"}, timeout=30)
    text = text_of(reply)
    rec.record(
        "C011",
        "a response larger than 1 MiB is cut and says so",
        expected="a result of at most 1 MiB of body that names the cut",
        actual={"chars": len(text), "tail": text[-200:]},
        ok=ok(reply) and len(text) < 1_048_576 + 4096 and "1048576" in text,
    )
    missing = await w.call(sid, f"{GROUP}__missing", {"coffer_environment": "test"})
    other = ctx.http[HTTP]["other_port"]
    before = [e for e in _received(ctx) if e.get("port") == other]
    target = f"http://127.0.0.1:{other}/qa-redirect-target"
    redirected = await w.call(
        sid, f"{GROUP}__redirect", {"coffer_environment": "test", "to": target}
    )
    reached = [e for e in _received(ctx) if e.get("port") == other][len(before) :]
    rec.record(
        "an error status is an error result and a redirect is not followed",
        "a 404 is an in-band error; a 302 to another origin is reported, not followed",
        expected="the 404 result is isError starting HTTP 404; the 302 result reports the "
        "location as not followed; the other origin receives nothing",
        actual={
            "404": text_of(missing)[:200],
            "302": text_of(redirected)[:300],
            "other_origin_requests": len(reached),
        },
        ok=in_band_error(missing)
        and text_of(missing).startswith("HTTP 404")
        and "302" in text_of(redirected)
        and "not followed" in text_of(redirected)
        and not reached,
        upstream={"other_origin": len(reached)},
    )


async def _concurrent(ctx: Ctx, sid: str) -> None:
    calls = [("test" if i % 2 == 0 else "uat", f"qa-{i}") for i in range(20)]
    before = len(_received(ctx))
    replies = await asyncio.gather(
        *(
            ctx.wire.call(
                sid,
                f"{GROUP}__render",
                {"coffer_environment": env, "id": ident, "q": "c"},
                rid=f"qa-env-{ident}",
            )
            for env, ident in calls
        )
    )
    received = _received(ctx)[before:]
    wrong = []
    for (env, ident), reply in zip(calls, replies, strict=True):
        body = text_of(reply)
        if not ok(reply) or f"/{env}/echo/{ident}" not in body:
            wrong.append({"env": env, "id": ident, "reply": body[:200]})
    mixed = [
        r
        for r in received
        if r.get("path", "").split("/")[1] == "test"
        and (r.get("headers") or {}).get("x-env") != "test"
    ]
    ctx.rec.record(
        "C014",
        "twenty concurrent calls alternating two environments do not mix",
        expected="each answer comes from its own environment's path; every request carries its "
        "own environment's header; none carries coffer_environment",
        actual={"wrong": wrong, "requests": len(received), "mixed_headers": mixed},
        ok=not wrong
        and len(received) == 20
        and not mixed
        and "coffer_environment" not in json.dumps(received),
        upstream=len(received),
    )


async def _mixed_case(ctx: Ctx, sid: str) -> None:
    api = ctx.run.client
    group = {
        "name": ENVCASE,
        "environments": [
            {"name": "Test", "base_url": _base(ctx, "/Test")},
            {"name": "live", "base_url": _base(ctx, "/live")},
        ],
        "tools": [{"name": "echo", "method": "GET", "path": "/echo"}],
    }
    created = await ctx.run.api.create_group(group)
    if created.status != 201:
        raise RuntimeError(f"creating {ENVCASE}: HTTP {created.status} {created.body}")
    root = f"/api/v1/custom-tools/{ENVCASE}/environments"
    steps: dict[str, Any] = {}

    def envs(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {e["name"]: e for e in doc.get("environments", [])}

    changed = await api.request("PATCH", f"{root}/test", {"description": "qa changed"})
    read = (await api.request("GET", f"/api/v1/custom-tools/{ENVCASE}")).json
    steps["describe test"] = [changed.status, envs(read).get("Test", {}).get("description")]
    renamed = await api.request("PATCH", f"{root}/TEST", {"name": "test"})
    read = (await api.request("GET", f"/api/v1/custom-tools/{ENVCASE}")).json
    enum_after_rename = sorted(
        ((await _render_schema(ctx, sid, ENVCASE, "echo")).get("properties") or {})
        .get("coffer_environment", {})
        .get("enum")
        or []
    )
    steps["rename TEST->test"] = [renamed.status, sorted(envs(read)), enum_after_rename]
    deleted = await api.request("DELETE", f"{root}/TeSt")
    read = (await api.request("GET", f"/api/v1/custom-tools/{ENVCASE}")).json
    steps["delete TeSt"] = [deleted.status, sorted(envs(read))]
    nobody = await api.request("PATCH", f"{root}/nobody", {"description": "x"})
    after = (await api.request("GET", f"/api/v1/custom-tools/{ENVCASE}")).json
    steps["unknown name"] = [
        nobody.status,
        (nobody.json.get("error") or {}).get("code"),
        sorted(envs(after)),
    ]
    ctx.rec.record(
        "an environment named in another case is changed or deleted",
        "environment routes find a name regardless of case",
        expected="'test' describes Test (read back); 'TEST' renamed to 'test' and the advertised "
        "choices follow; 'TeSt' deleted; an unknown name is 404 with nothing changed",
        actual=steps,
        ok=steps["describe test"] == [200, "qa changed"]
        and steps["rename TEST->test"] == [200, ["live", "test"], ["live", "test"]]
        and steps["delete TeSt"] == [200, ["live"]]
        and steps["unknown name"][0] == 404
        and steps["unknown name"][2] == ["live"],
    )


async def _unsaved_private(ctx: Ctx) -> None:
    before = len(_received(ctx))
    reply = await ctx.run.client.request(
        "POST",
        "/api/v1/custom-tools/test",
        {
            "base_url": _base(ctx, ""),
            "tool": {"name": "qa", "method": "GET", "path": "/echo"},
            "arguments": {},
        },
    )
    n = len(_received(ctx)) - before
    ctx.rec.record(
        "an unsaved group on a private address is not tested",
        "a draft request to a loopback address is refused before sending",
        expected="nothing reaches the receiver and the result says the address was refused",
        actual={"http": reply.status, "body": reply.body, "requests": n},
        ok=n == 0 and (reply.json.get("failure") == "blocked" or reply.status >= 400),
        upstream=n,
    )
