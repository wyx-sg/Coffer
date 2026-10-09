"""Packaging integrity and the installed configuration, read-only.

* One build: the daemon answering the port is the binary ``daemon.json``
  names, the handshake reports the version its status does, and the shim the
  run started raised no version-skew warning (the shim warns on stderr when
  the daemon it attached to is another version than its own).
* The shim under test is the one in the daemon's install directory.
* Every registered agent's Coffer entry points at that shim (read through the
  daemon's agent routes; nothing is written).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from e2e.installed._common.recorder import NA
from e2e.installed._common.target import fingerprint
from e2e.installed.mcp.context import Ctx

SKEW = "attached to a Coffer daemon at version"


def _same(a: str | Path | None, b: str | Path | None) -> bool:
    return a is not None and b is not None and Path(a).resolve() == Path(b).resolve()


async def run(ctx: Ctx) -> None:
    _one_build(ctx)
    _shim_directory(ctx)
    await _agent_entries(ctx)


def _one_build(ctx: Ctx) -> None:
    target, status = ctx.run.target, ctx.run.status
    logs: list[Path] = ctx.facts.get("shim_logs", [])
    skew = [line for log in logs if log.is_file() for line in log.read_text().splitlines()]
    skew = [line for line in skew if SKEW in line]
    version = status.get("version")
    ctx.rec.record(
        "the daemon, its handshake and the shim are one build",
        "the binary daemon.json names answers the port, reports one version, and the shim "
        "attached to it without a version-skew warning",
        expected="status.executable is daemon.json's binary_path; the handshake's serverInfo "
        "version equals status.version; the daemon binary is fingerprinted; the shim ran and "
        "printed no version-skew warning",
        actual={
            "status_version": version,
            "status_commit": status.get("commit"),
            "status_executable": status.get("executable"),
            "daemon_json_binary": str(target.binary_path),
            "server_info_version": ctx.facts.get("server_info_version"),
            "daemon_binary": fingerprint(target.binary_path),
            "shim": fingerprint(target.shim),
            "shim_logs": [log.name for log in logs],
            "skew_warnings": skew,
        },
        ok=isinstance(version, str)
        and bool(version)
        and _same(status.get("executable"), target.binary_path)
        and ctx.facts.get("server_info_version") == version
        and fingerprint(target.binary_path) is not None
        and bool(logs)
        and not skew,
    )


def _shim_directory(ctx: Ctx) -> None:
    target = ctx.run.target
    facts = {
        "shim": str(target.shim) if target.shim else None,
        "daemon_binary": str(target.binary_path),
        "chosen_by": "--shim" if ctx.run.args.shim else "default resolution",
        "same_directory": bool(target.shim)
        and _same(target.shim.parent if target.shim else None, target.binary_path.parent),
    }
    title = "the shim under test is the one in the daemon's install directory"
    if ctx.run.args.shim:
        ctx.rec.record(
            title,
            title,
            expected="only checked when the shim is found by default resolution",
            actual=facts,
            status=NA,
        )
        return
    ctx.rec.record(
        title,
        title,
        expected="coffer-mcp-shim sits next to the daemon binary daemon.json names",
        actual=facts,
        ok=facts["same_directory"] is True,
    )


async def _agent_entries(ctx: Ctx) -> None:
    client, shim = ctx.run.client, ctx.run.target.shim
    agents = (await client.request("GET", "/api/v1/agents")).json.get("items", [])
    entries: list[dict[str, Any]] = []
    for agent in agents:
        reply = await client.request("GET", f"/api/v1/agents/{agent['uid']}/mcp-entries")
        for entry in reply.json.get("items", []):
            if entry.get("is_coffer"):
                entries.append(
                    {
                        "agent": agent.get("name"),
                        "source": entry.get("source"),
                        "command": entry.get("command"),
                        "is_tested_shim": _same(entry.get("command"), shim),
                    }
                )
    title = "every agent's Coffer entry points at the tested shim"
    facts = {"shim": str(shim) if shim else None, "agents": len(agents), "entries": entries}
    if not entries or ctx.run.args.shim:
        why = "no agent here carries Coffer's entry" if not entries else "--shim chose the shim"
        ctx.rec.record(title, title, expected=f"not checked: {why}", actual=facts, status=NA)
        return
    ctx.rec.record(
        title,
        title,
        expected="each agent config's coffer command resolves to the shim this run tested",
        actual=facts,
        ok=all(e["is_tested_shim"] for e in entries),
    )
