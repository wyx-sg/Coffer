"""Secrets with a fake canary: stdio injection and stderr masking, a custom
tool's secret header, its masked and capped response, and no redirect.

The canary is a random value minted for this run; it is registered with the
redactor, so no file the run writes holds it. A binding the target holds for a
person's approval (a signed build, whose approvals need Touch ID) makes the
dependent cases BLOCKED: nothing here approves anything.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from e2e.installed._common.recorder import BLOCKED, NA
from e2e.installed.mcp.context import Ctx
from e2e.installed.mcp.wire import in_band_error, ok, structured, text_of

SECRET, STDIO, AUTH, HTTP = "qa-mcp-canary", "qa-mcp-secret", "qa-mcp-auth", "qa-mcp-http"
MASK = "••••••"
PENDING = ("SECRET_BINDING_PENDING", "SECRET_BINDING_REJECTED")


def _pending(reply: Any) -> bool:
    text = json.dumps(reply.body)
    return any(p in text for p in PENDING)


def _raw(reply: Any) -> str:
    """The reply as sent, before the run's redaction (which happens only on write)."""
    return json.dumps(reply.body)


async def run(ctx: Ctx) -> None:
    made = await ctx.run.api.create_secret(SECRET, ctx.canary, "fake canary for installed QA")
    if made.status != 201:
        raise RuntimeError(f"storing the fake secret: HTTP {made.status} {made.body}")
    ref = made.json["ref"]
    await _stdio(ctx, ref)
    await _custom(ctx, ref)
    await _nowhere(ctx)


async def _stdio(ctx: Ctx, ref: str) -> None:
    transport = ctx.stdio(STDIO, env={"QA_ENV": "qa-secret-env"})
    transport["secret_refs"] = {"QA_CANARY_SECRET": ref}
    await ctx.register(STDIO, transport)
    sid, _ = await ctx.wire.initialize("qa-agent-a")
    reply = await ctx.wire.call(sid, f"{STDIO}__environment", timeout=30)
    pending = _pending(reply)
    ctx.note_pids(STDIO)
    ctx.rec.record(
        "S001",
        "a stdio server receives its approved secret in its environment",
        expected="the tool sees QA_CANARY_SECRET set",
        actual=reply.body,
        ok=ok(reply) and structured(reply).get("secret_present") is True,
        status=BLOCKED if pending else None,
    )
    title = "an injected secret a stdio server prints on stderr is masked before it is written"
    if pending:
        ctx.rec.blocked(
            title,
            "stderr masking of an injected secret",
            expected="masked log",
            reason="the binding waits for a person's approval",
        )
        return
    for tool in ("secret_stderr", "secret_stderr_split", "secret_stderr_exit"):
        await ctx.wire.call(sid, f"{STDIO}__{tool}", timeout=30)
    await ctx.wire.call(sid, f"{STDIO}__echo", {"text": "respawn after exit"}, timeout=30)
    ctx.note_pids(STDIO)
    await asyncio.sleep(0.5)
    log = await ctx.run.client.request(
        "GET", f"/api/v1/resources/mcp_server/{ctx.uid(STDIO)}/log?limit=200"
    )
    lines = [line.get("text", "") for line in log.json.get("lines", [])]
    raw_file = _raw_log(ctx, log.json.get("path"))
    page_text = "\n".join(lines)
    ctx.rec.record(
        title,
        "a canary printed on stderr (one write, split across two, just before exit) is masked",
        expected="no canary in the log page or the raw log file; three masked lines; the plain "
        "stderr line kept verbatim (diagnosis hand-off not checked here)",
        actual={
            "canary_in_page": ctx.canary in page_text,
            "canary_in_file": None if raw_file is None else ctx.canary in raw_file,
            "masked_lines": [t for t in lines if MASK in t],
            "plain_line_kept": "qa stderr plain line" in page_text,
        },
        ok=log.status == 200
        and ctx.canary not in page_text
        and (raw_file is None or ctx.canary not in raw_file)
        and sum(MASK in t for t in lines) >= 3
        and "qa stderr plain line" in page_text,
    )
    echoed = await ctx.wire.call(sid, f"{STDIO}__secret_echo", timeout=30)
    ctx.rec.record(
        "S002",
        "observation: a stdio tool that returns its own secret in its result",
        expected="a stdio result is the upstream's business data, not masked by contract; "
        "recorded only",
        actual={"canary_in_result": ctx.canary in _raw(echoed)},
        status=NA,
    )


def _raw_log(ctx: Ctx, path: str | None) -> str | None:
    """The server's own log file, read only when it lies under the target's ~/.coffer."""
    home = ctx.run.target.home
    if not path or home is None:
        return None
    file = Path(path).expanduser()
    if not file.is_absolute():
        file = home / ".coffer" / path
    if (home / ".coffer") not in file.resolve().parents or not file.is_file():
        return None
    return file.read_text(errors="replace")


async def _custom(ctx: Ctx, ref: str) -> None:
    name = ref.split("/", 1)[1]
    port = ctx.http[HTTP]["port"]
    base = f"http://127.0.0.1:{port}"
    basic = await ctx.run.api.create_group(
        {
            "name": "qa-mcp-auth-basic",
            "base_url": f"{base}/basic",
            "headers": [{"name": "Authorization", "secret": name, "scheme": "Basic"}],
            "tools": [{"name": "echo", "method": "GET", "path": "/echo"}],
        }
    )
    ctx.rec.record(
        "S003",
        "an unsupported header scheme (Basic) is refused when saved",
        expected="HTTP 422; the canary not in the answer",
        actual=[basic.status, basic.body],
        ok=basic.status == 422 and ctx.canary not in _raw(basic),
    )
    group = await ctx.run.api.create_group(
        {
            "name": AUTH,
            "environments": [
                {
                    "name": "Test",
                    "base_url": f"{base}/secret-test",
                    "headers": [{"name": "Authorization", "secret": name, "scheme": "Bearer"}],
                },
                {
                    "name": "uat",
                    "base_url": f"{base}/secret-uat",
                    "headers": [{"name": "Authorization", "secret": name, "scheme": "Token"}],
                },
            ],
            "tools": [
                {
                    "name": "get",
                    "method": "GET",
                    "path": "/invoices/{id}?status={status}",
                    "input_schema": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}, "status": {"type": "string"}},
                        "required": ["id"],
                    },
                },
                {"name": "mask", "method": "GET", "path": "/secret-echo"},
                {"name": "large", "method": "GET", "path": "/large-secret"},
                {
                    "name": "header",
                    "method": "GET",
                    "path": "/echo",
                    "headers": {"X-Arg": "{value}"},
                    "input_schema": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "required": ["value"],
                    },
                },
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
            ],
        }
    )
    if group.status != 201:
        raise RuntimeError(f"creating {AUTH}: HTTP {group.status} {group.body}")
    ctx.servers[AUTH] = group.json
    sid, _ = await ctx.wire.initialize("qa-agent-a")
    await _sends_secret(ctx, sid)
    await _masked_and_capped(ctx, sid)
    await _no_redirect(ctx, sid)
    await _crlf(ctx, sid)


def _received(ctx: Ctx) -> list[dict[str, Any]]:
    return ctx.events(HTTP, "http")


async def _sends_secret(ctx: Ctx, sid: str) -> None:
    before = len(_received(ctx))
    reply = await ctx.wire.call(sid, f"{AUTH}__get", {"coffer_environment": "Test", "id": "a/b"})
    hits = _received(ctx)[before:]
    hit = hits[0] if hits else {}
    rows = (await ctx.invocations(AUTH)).get("invocations", [])
    latest = rows[0] if rows else {}
    title = "a custom tool call sends the rendered request with the secret"
    if _pending(reply):
        ctx.rec.blocked(
            title,
            "the secret header reaches the API",
            expected="Bearer canary",
            reason="the binding waits for a person's approval",
        )
    else:
        ctx.rec.record(
            title,
            "the rendered request carries the secret behind its scheme",
            expected="GET /secret-test/invoices/a%2Fb with no query (status absent) and "
            "Authorization: Bearer <canary>; the agent gets HTTP 200; the invocation is one ok "
            "call naming Test, without arguments",
            actual={"reply_head": text_of(reply)[:60], "received": hit, "invocation": latest},
            ok=text_of(reply).startswith("HTTP 200")
            and len(hits) == 1
            and hit.get("path") == "/secret-test/invoices/a%2Fb"
            and not hit.get("query")
            and hit.get("auth_matches_canary") is True
            and latest.get("status") == "ok"
            and latest.get("environment") == "Test"
            and "a/b" not in json.dumps(latest),
            upstream=len(hits),
        )
    before = len(_received(ctx))
    reply = await ctx.wire.call(sid, f"{AUTH}__get", {"coffer_environment": "uat", "id": "x"})
    hit = (_received(ctx)[before:] or [{}])[0]
    ctx.rec.record(
        "X006",
        "each environment sends the secret behind its own scheme",
        expected="uat sends Authorization: Token <canary>",
        actual={
            "reply_head": text_of(reply)[:60],
            "auth": hit.get("headers", {}).get("authorization"),
            "matches": hit.get("auth_matches_canary"),
        },
        ok=text_of(reply).startswith("HTTP 200") and hit.get("auth_matches_canary") is True,
        status=BLOCKED if _pending(reply) else None,
    )


async def _masked_and_capped(ctx: Ctx, sid: str) -> None:
    reply = await ctx.wire.call(sid, f"{AUTH}__large", {"coffer_environment": "Test"}, timeout=30)
    text = text_of(reply)
    ctx.rec.record(
        "a custom tool's response is capped and masked",
        "a 2 MB answer holding the secret: at most 1 MiB, says so, secret masked",
        expected="at most 1 MiB of body, a truncation note, *** where the canary was, no canary",
        actual={
            "chars": len(text),
            "head": text[:80],
            "tail": text[-160:],
            "canary_present": ctx.canary in _raw(reply),
        },
        ok=ok(reply)
        and len(text) < 1_048_576 + 4096
        and "1048576" in text
        and "***" in text
        and ctx.canary not in _raw(reply),
        status=BLOCKED if _pending(reply) else None,
    )
    reply = await ctx.wire.call(sid, f"{AUTH}__mask", {"coffer_environment": "Test"})
    ctx.rec.record(
        "X007",
        "an API echoing the injected secret is answered masked",
        expected="*** in the result and no canary",
        actual={"result": text_of(reply)[:300], "canary_present": ctx.canary in _raw(reply)},
        ok=ok(reply) and "***" in text_of(reply) and ctx.canary not in _raw(reply),
        status=BLOCKED if _pending(reply) else None,
    )


async def _no_redirect(ctx: Ctx, sid: str) -> None:
    other = ctx.http[HTTP]["other_port"]
    before_main = len(_received(ctx))
    before_other = len([e for e in _received(ctx) if e.get("port") == other])
    reply = await ctx.wire.call(
        sid,
        f"{AUTH}__redirect",
        {
            "coffer_environment": "Test",
            "to": f"http://127.0.0.1:{other}/qa-redirect-target",
        },
    )
    received = _received(ctx)[before_main:]
    to_other = len([e for e in _received(ctx) if e.get("port") == other]) - before_other
    ctx.rec.record(
        "a redirect to another origin is never sent the secret",
        "a custom tool with a secret header is redirected to another origin",
        expected="one request to the first origin (with the secret); the 302 is reported, not "
        "followed; the second origin receives no request",
        actual={
            "reply": text_of(reply)[:300],
            "first_origin": len(received) - to_other,
            "second_origin": to_other,
            "secret_at_first": [e.get("auth_matches_canary") for e in received],
        },
        ok="302" in text_of(reply)
        and "not followed" in text_of(reply)
        and to_other == 0
        and len(received) == 1
        and received[0].get("auth_matches_canary") is True,
        upstream={"first": len(received) - to_other, "second": to_other},
        status=BLOCKED if _pending(reply) else None,
    )


async def _crlf(ctx: Ctx, sid: str) -> None:
    before = len(_received(ctx))
    reply = await ctx.wire.call(
        sid, f"{AUTH}__header", {"coffer_environment": "Test", "value": "x\r\nX-Fake: qa"}
    )
    n = len(_received(ctx)) - before
    ctx.rec.record(
        "X009",
        "a rendered header with CR/LF is refused before the secret is read or sent",
        expected="an in-band error; zero requests",
        actual={"reply": text_of(reply)[:300], "requests": n},
        ok=in_band_error(reply) and n == 0,
        upstream=n,
    )


async def _nowhere(ctx: Ctx) -> None:
    sid, _ = await ctx.wire.initialize("qa-agent-a")
    tools = await ctx.wire.rpc("tools/list", {}, sid)
    prompts = await ctx.wire.rpc("prompts/list", {}, sid)
    secrets = await ctx.run.client.request("GET", "/api/v1/secrets")
    group = await ctx.run.client.request("GET", f"/api/v1/custom-tools/{AUTH}")
    audit = await ctx.run.client.request("GET", "/api/v1/audit?limit=200")
    invocations = [await ctx.invocations(n) for n in (STDIO, AUTH)]
    where = {
        "tools/list": tools.body,
        "prompts/list": prompts.body,
        "secrets": secrets.body,
        "group": group.body,
        "audit": audit.body,
        "invocations": invocations,
    }
    found = [k for k, v in where.items() if ctx.canary in json.dumps(v)]
    ctx.rec.record(
        "S006",
        "the canary is in no listing, schema, metadata, audit entry or invocation record",
        expected="none of tools/list, prompts/list, the secrets list, the group, the audit log, "
        "the invocation logs holds the canary",
        actual={"holding_canary": found, "audit_http": audit.status},
        ok=not found and audit.status == 200,
    )
