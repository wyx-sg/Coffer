"""The installed-build MCP acceptance run: fixtures, the case areas, the cases it cannot run.

Case ids are the OpenSpec scenario title (``openspec/specs/mcp-gateway`` and
``secret``) when a case verifies that scenario, otherwise a short stable local
id (the letter families follow the original full-test case pack: P protocol,
D/B/E catalogue, A permissions, L lifecycle, C custom tools, S/X secrets and
extended, SDK, F performance).
"""

from __future__ import annotations

import secrets

from e2e.installed._common.coffer_api import MCP_SERVER, SECRET
from e2e.installed._common.run import Run, main
from e2e.installed.mcp import (
    cases_catalogue,
    cases_custom,
    cases_lifecycle,
    cases_perf,
    cases_permissions,
    cases_protocol,
    cases_relay,
    cases_sdk,
    cases_secrets,
)
from e2e.installed.mcp.context import Ctx, phase
from e2e.installed.mcp.wire import Wire

SERVERS = [
    "qa-mcp-a",
    "qa-mcp-b",
    "qa-mcp-toggle",
    "qa-mcp-pin",
    "qa-mcp-http",
    "qa-mcp-relay",
    "qa-mcp-page",
    "qa-mcp-renamed",
    "qa-mcp-timeout",
    "qa-mcp-no-command",
    "qa-mcp-no-cwd",
    "qa-mcp-exit",
    "qa-mcp-stdout",
    "qa-mcp-json",
    "qa-mcp-fault-status",
    "qa-mcp-fault-drop",
    "qa-mcp-delete",
    "qa-mcp-custom",
    "qa-mcp-envcase",
    "qa-mcp-reserved",
    "qa-mcp-secret",
    "qa-mcp-auth",
    "qa-mcp-auth-basic",
    "qa-mcp-bench",
]
RESERVE = [(MCP_SERVER, name) for name in SERVERS] + [(SECRET, "qa-mcp-canary")]

NOT_AUTOMATED = [
    ("P026", "a restarted daemon refuses the old token", "needs a daemon restart"),
    ("P027", "a restarted daemon answers an old session 404", "needs a daemon restart"),
    ("P028", "after a restart a fresh initialize and call work", "needs a daemon restart"),
    ("P029", "an idle session is reaped", "needs the idle reaper's hours-long window"),
    (
        "a tool call is not re-run after the daemon restarts mid-call",
        "the shim answers a call cut by a restart without re-running it",
        "needs the daemon killed mid-call and restarted",
    ),
    (
        "a dropped session is answered 404 and the client handshakes again",
        "the shim replays initialize after its session was reaped",
        "needs the idle reaper or a restart",
    ),
]


async def _setup(ctx: Ctx) -> None:
    out = ctx.run.out
    http = await ctx.start_http("qa-mcp-http")
    relay = await ctx.start_http("qa-mcp-relay", stateful=True)
    await ctx.register("qa-mcp-a", ctx.stdio("qa-mcp-a", env={"QA_ENV": "qa-env-value"}, cwd=out))
    await ctx.register("qa-mcp-b", ctx.stdio("qa-mcp-b"))
    await ctx.register(
        "qa-mcp-http", {"type": "http", "url": f"http://127.0.0.1:{http['port']}/mcp/"}
    )
    await ctx.register(
        "qa-mcp-relay", {"type": "http", "url": f"http://127.0.0.1:{relay['port']}/mcp/"}
    )
    await ctx.register("qa-mcp-toggle", ctx.stdio("qa-mcp-toggle"))
    # A session's tools/list makes discovery save each server's tool list, which the
    # exposure and switch routes check names against.
    sid, _ = await ctx.wire.initialize("qa-agent-setup")
    await ctx.wire.tool_names(sid)
    # Pin what the cases read from tools/list, so a target with many tools (tiering)
    # still lists them; it changes only these qa servers' own exposure.
    for name, tools in (
        ("qa-mcp-a", ["echo", "image"]),
        ("qa-mcp-b", ["echo", "image"]),
        ("qa-mcp-toggle", ["echo", "image", "business_error"]),
    ):
        keys = await ctx.capabilities(name)
        if "echo" not in keys:
            raise RuntimeError(f"{name}: discovery never listed echo ({keys})")
        status = await ctx.expose(name, tools, "listed")
        if status not in (200, 204):
            raise RuntimeError(f"{name}: pinning {tools} answered HTTP {status}")


async def suite(run: Run) -> None:
    canary = "qa-canary-" + secrets.token_hex(16)
    run.redactor.add(canary)
    ctx = Ctx(run=run, wire=Wire(run.client), canary=canary)
    run.recorder.area = "setup"
    await _setup(ctx)
    for area, module in (
        ("protocol", cases_protocol),
        ("catalogue", cases_catalogue),
        ("permissions", cases_permissions),
        ("relay", cases_relay),
        ("lifecycle", cases_lifecycle),
        ("sdk", cases_sdk),
        ("custom-tools", cases_custom),
        ("secrets", cases_secrets),
        ("performance", cases_perf),
    ):
        await phase(ctx, area, module.run)
    run.recorder.area = "not-automated"
    for case_id, title, reason in NOT_AUTOMATED:
        run.recorder.blocked(case_id, title, expected="see the spec", reason=reason)
    for ledger in ctx.ledger_dir.glob("*.jsonl"):
        ctx.note_pids(ledger.stem)


def entry(argv: list[str] | None = None) -> int:
    return main(
        "Installed-build MCP acceptance: drives an installed Coffer's /mcp, its shim and the "
        "official MCP SDK against synthetic upstreams.",
        "mcp",
        RESERVE,
        suite,
        argv,
    )
