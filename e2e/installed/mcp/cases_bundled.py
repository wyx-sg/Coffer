"""Modules a frozen build loads only when a path first needs them.

PyInstaller bundles what its analysis finds; a module imported lazily on a
rarely taken path can be missing from the bundle or broken by a swapped build
(a daemon restarted mid-install throws ``zlib.error`` on such an import), and
only the installed build shows it. Two such paths:

* a stdio upstream with an injected (fake) secret, whose stderr goes through
  the stderr masker before it is written to the server's log;
* a custom HTTP tool call, which goes through the HTTP API client.

The canary is a random value minted for this run; it is registered with the
redactor, so no file the run writes holds it. A binding the target holds for a
person's approval (a signed build, whose approvals need Touch ID) makes the
masking case BLOCKED: nothing here approves anything.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from e2e.installed._common.recorder import BLOCKED
from e2e.installed.mcp.context import Ctx
from e2e.installed.mcp.wire import ok, structured, text_of

SECRET, STDIO, CUSTOM, HTTP = "qa-mcp-canary", "qa-mcp-secret", "qa-mcp-custom", "qa-mcp-relay"
MASK = "••••••"
PENDING = ("SECRET_BINDING_PENDING", "SECRET_BINDING_REJECTED", "waiting for approval")
MASKED = "an injected secret a stdio server prints on stderr is masked before it is written"


async def run(ctx: Ctx) -> None:
    await _stderr_masked(ctx)
    await _custom_tool(ctx)


async def _stderr_masked(ctx: Ctx) -> None:
    made = await ctx.run.api.create_secret(SECRET, ctx.canary, "fake canary for installed QA")
    if made.status != 201:
        raise RuntimeError(f"storing the fake secret: HTTP {made.status} {made.body}")
    transport = ctx.stdio(STDIO, env={"QA_ENV": "qa-secret-env"})
    transport["secret_refs"] = {"QA_CANARY_SECRET": made.json["ref"]}
    await ctx.register(STDIO, transport)
    sid = await ctx.wire.initialize("qa-agent-a")
    injected = await ctx.wire.call(sid, f"{STDIO}__environment", timeout=30)
    ctx.note_pids(STDIO)
    if any(p in json.dumps(injected.body) for p in PENDING):
        ctx.rec.record(
            MASKED,
            "stderr masking of an injected secret",
            expected="masked log",
            actual={"reason": "the binding waits for a person's approval"},
            status=BLOCKED,
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
        MASKED,
        "a canary printed on stderr (one write, split across two, just before exit) is masked",
        expected="the server received the secret; no canary in the log page or the raw log file; "
        "three masked lines; the plain stderr line kept verbatim",
        actual={
            "secret_present": structured(injected).get("secret_present"),
            "canary_in_page": ctx.canary in page_text,
            "canary_in_file": None if raw_file is None else ctx.canary in raw_file,
            "masked_lines": [t for t in lines if MASK in t],
            "plain_line_kept": "qa stderr plain line" in page_text,
        },
        ok=structured(injected).get("secret_present") is True
        and log.status == 200
        and ctx.canary not in page_text
        and (raw_file is None or ctx.canary not in raw_file)
        and sum(MASK in t for t in lines) >= 3
        and "qa stderr plain line" in page_text,
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


async def _custom_tool(ctx: Ctx) -> None:
    port = ctx.http[HTTP]["port"]
    group: dict[str, Any] = {
        "name": CUSTOM,
        "description": "qa synthetic custom tool",
        "base_url": f"http://127.0.0.1:{port}/qa",
        "tools": [
            {
                "name": "get",
                "method": "GET",
                "path": "/items/{id}",
                "input_schema": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                },
            }
        ],
    }
    reply = await ctx.run.api.create_group(group)
    if reply.status != 201:
        raise RuntimeError(f"creating {CUSTOM}: HTTP {reply.status} {reply.body}")
    ctx.servers[CUSTOM] = reply.json
    sid = await ctx.wire.initialize("qa-agent-a")
    before = len(ctx.events(HTTP, "http"))
    called = await ctx.wire.call(sid, f"{CUSTOM}__get", {"id": "qa-1"}, timeout=30)
    received = ctx.events(HTTP, "http")[before:]
    ctx.rec.record(
        "a custom HTTP tool call reaches its API through the installed build",
        "a custom tool call renders and sends one HTTP request and returns the answer",
        expected="one GET /qa/items/qa-1 at the receiver; the agent gets an HTTP 200 result",
        actual={
            "reply_head": text_of(called)[:120],
            "received": [{k: r.get(k) for k in ("method", "path")} for r in received],
        },
        ok=ok(called)
        and text_of(called).startswith("HTTP 200")
        and [(r.get("method"), r.get("path")) for r in received] == [("GET", "/qa/items/qa-1")],
        upstream=len(received),
    )
