"""The installed-build MCP acceptance run: fixtures and the case areas.

It keeps only what an installed build alone can show — the frozen daemon and
the installed shim connecting, the official SDK's sessions over Streamable
HTTP, SSE and the shim (server-initiated requests included), packaging
integrity, the installed configuration, and the cleanup checks. What the
gateway does with each message is pinned by the repository's own suites.

Case ids are the OpenSpec scenario title (``openspec/specs/mcp-gateway`` and
``secret``) when a case verifies that scenario, otherwise a short descriptive
id.
"""

from __future__ import annotations

import secrets

from e2e.installed._common.coffer_api import MCP_SERVER, SECRET
from e2e.installed._common.run import Run, main
from e2e.installed.mcp import (
    cases_bundled,
    cases_packaging,
    cases_perf,
    cases_relay,
    cases_sdk,
    cases_shim,
)
from e2e.installed.mcp.context import Ctx, phase
from e2e.installed.mcp.wire import Wire

SERVERS = ["qa-mcp-a", "qa-mcp-b", "qa-mcp-relay", "qa-mcp-secret", "qa-mcp-custom", "qa-mcp-bench"]
RESERVE = [(MCP_SERVER, name) for name in SERVERS] + [(SECRET, "qa-mcp-canary")]


async def _setup(ctx: Ctx) -> None:
    out = ctx.run.out
    await ctx.start_http("qa-mcp-relay")
    relay = ctx.http["qa-mcp-relay"]
    await ctx.register("qa-mcp-a", ctx.stdio("qa-mcp-a", env={"QA_ENV": "qa-env-value"}, cwd=out))
    await ctx.register("qa-mcp-b", ctx.stdio("qa-mcp-b"))
    await ctx.register(
        "qa-mcp-relay", {"type": "http", "url": f"http://127.0.0.1:{relay['port']}/mcp/"}
    )
    # A session's tools/list makes discovery save each server's tool list, which the
    # exposure route checks names against.
    sid = await ctx.wire.initialize("qa-agent-setup")
    await ctx.wire.tool_names(sid)
    # Pin what the cases read from tools/list, so a target with many tools (tiering)
    # still lists them; it changes only these qa servers' own exposure.
    for name in ("qa-mcp-a", "qa-mcp-b"):
        keys = await ctx.capabilities(name)
        if "echo" not in keys:
            raise RuntimeError(f"{name}: discovery never listed echo ({keys})")
        status = await ctx.expose(name, ["echo"], "listed")
        if status not in (200, 204):
            raise RuntimeError(f"{name}: pinning echo answered HTTP {status}")


async def suite(run: Run) -> None:
    canary = "qa-canary-" + secrets.token_hex(16)
    run.redactor.add(canary)
    ctx = Ctx(run=run, wire=Wire(run.client), canary=canary)
    run.recorder.area = "setup"
    await _setup(ctx)
    for area, module in (
        ("sdk-http", cases_sdk),
        ("relay", cases_relay),
        ("shim", cases_shim),
        ("bundled-modules", cases_bundled),
        ("performance", cases_perf),
        ("packaging", cases_packaging),
    ):
        await phase(ctx, area, module.run)
    for ledger in ctx.ledger_dir.glob("*.jsonl"):
        ctx.note_pids(ledger.stem)


def entry(argv: list[str] | None = None) -> int:
    return main(
        "Installed-build MCP acceptance: the installed daemon, its shim and the official MCP "
        "SDK against synthetic upstreams — only what an installed build can show.",
        "mcp",
        RESERVE,
        suite,
        argv,
    )
