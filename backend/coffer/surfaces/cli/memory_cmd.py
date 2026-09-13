"""``coffer memory …`` — the memory layer from the terminal (spec memory
FR-061).

Every command but one is a thin HTTP shell over the daemon, matching
``knowledge_cmd.py``. ``context`` is the exception: it is the exact command
an agent's own session-start hook invokes
(``domain.memory.delivery.hook_command``), so it must be fast and must never
fail a session — no detect-or-spawn, a short timeout, and any failure at all
(daemon not running, a slow response, a malformed one) degrades to printing
nothing and exiting 0. FR-055 exists precisely because the previous injection
layer had no such safety net and nothing said so for two months; this command
must not repeat that by crashing a real session over its own plumbing.
"""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.infrastructure.daemon.bootstrap import live_daemon
from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Browse and manage Coffer's memory layer")
_console = Console()

#: Generous for a local loopback call, tiny next to the 10s detect-or-spawn
#: timeout `client_or_exit()` would otherwise impose on every session start.
_CONTEXT_TIMEOUT_S = 3.0

_OVERRIDE_FIELDS = ("hidden", "pinned", "superseded_by", "conflict_choice")


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def _echo_json_or(
    ctx: typer.Context, data: object, output_json: bool, render: Callable[[Any], None]
) -> None:
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    render(data)


@app.command("partitions")
def list_partitions(ctx: typer.Context, output_json: bool = typer.Option(False, "--json")) -> None:
    """List every partition."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/memory/partitions")
        _cli_client.check(r, verbose=_verbose(ctx))

    def render(data: dict[str, Any]) -> None:
        table = Table(title="Memory partitions")
        table.add_column("name")
        table.add_column("facts", justify="right")
        table.add_column("project root")
        for p in data["partitions"]:
            table.add_row(p["name"], str(p["fact_count"]), p["project_root"])
        _console.print(table)

    _echo_json_or(ctx, r.json(), output_json, render)


@app.command("facts")
def list_facts(
    ctx: typer.Context,
    partition: str = typer.Argument(..., help="Partition name (or 'global')"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List every fact in one partition."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/memory/partitions/{partition}/facts")
        _cli_client.check(r, verbose=_verbose(ctx))

    def render(data: dict[str, Any]) -> None:
        table = Table(title=f"memory:{partition}")
        for col in ("key", "slug", "title", "type", "status", "hidden", "pinned"):
            table.add_column(col)
        for f in data["facts"]:
            table.add_row(
                f["key"],
                f["slug"],
                f["title"],
                f["type"],
                f["status"],
                str(f["hidden"]),
                str(f["pinned"]),
            )
        _console.print(table)

    _echo_json_or(ctx, r.json(), output_json, render)


@app.command("fact")
def show_fact(
    ctx: typer.Context,
    partition: str = typer.Argument(...),
    slug: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one fact — its body, origins and conflicts."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/memory/partitions/{partition}/facts/{slug}")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"# {data['title']} ({data['key']})")
    typer.echo(f"type={data['type']} status={data['status']} partition={data['partition']}")
    if data["conflicts_with"]:
        typer.echo(f"conflicts with: {', '.join(data['conflicts_with'])}")
    if data["superseded_by"]:
        typer.echo(f"superseded by: {data['superseded_by']}")
    typer.echo("")
    typer.echo(data["body"])
    typer.echo("")
    for o in data["origins"]:
        typer.echo(f"origin: {o['agent']} <- {o['native_path']}")


@app.command("sync")
def sync(ctx: typer.Context, output_json: bool = typer.Option(False, "--json")) -> None:
    """Run aggregation: read every registered agent's native memory."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/memory/sync")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2) if output_json else r.text)


@app.command("organize")
def organize(
    ctx: typer.Context,
    partition: str = typer.Argument(..., help="Partition to organise"),
) -> None:
    """Run the organise pass by hand over one partition."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/memory/partitions/{partition}/organise")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))


@app.command("context")
def context(
    agent: str = typer.Option(..., "--agent", help="Calling agent's registered name"),
    cwd: str = typer.Option(..., "--cwd", help="The session's working directory"),
    budget_tokens: int = typer.Option(0, "--budget-tokens", help="0 = the server's default"),
) -> None:
    """Print the composed session-start context (L0 + L1) to stdout.

    This is exactly what an installed session-start hook invokes
    (``domain.memory.delivery.hook_command``) — see the module docstring for
    why every failure here is silent rather than raised.
    """
    try:
        info = live_daemon()
        if info is None:
            return
        payload: dict[str, object] = {"agent": agent, "cwd": cwd, "record_fired": True}
        if budget_tokens > 0:
            payload["budget_tokens"] = budget_tokens
        resp = httpx.post(
            f"http://127.0.0.1:{info.port}/api/v1/memory/context",
            json=payload,
            headers={"X-Coffer-Token": info.token, "X-Coffer-Actor": "cli"},
            timeout=_CONTEXT_TIMEOUT_S,
        )
        if resp.status_code != 200:
            return
        text = resp.json().get("text")
        if text:
            typer.echo(text)
    except Exception:
        return


def _patch_override(ctx: typer.Context, fact_key: str, changes: dict[str, Any]) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/memory/facts/{fact_key}/override", json=changes)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))


def _clear_override(ctx: typer.Context, fact_key: str, field: str) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/memory/facts/{fact_key}/override", params={"field": field})
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))


@app.command("hide")
def hide(ctx: typer.Context, fact_key: str = typer.Argument(...)) -> None:
    """Hide a fact from every delivery and retrieval result (FR-042)."""
    _patch_override(ctx, fact_key, {"hidden": True})


@app.command("unhide")
def unhide(ctx: typer.Context, fact_key: str = typer.Argument(...)) -> None:
    """Reverse ``hide``."""
    _clear_override(ctx, fact_key, "hidden")


@app.command("pin")
def pin(ctx: typer.Context, fact_key: str = typer.Argument(...)) -> None:
    """Pin a fact so the digest's budget always prefers it (FR-051)."""
    _patch_override(ctx, fact_key, {"pinned": True})


@app.command("unpin")
def unpin(ctx: typer.Context, fact_key: str = typer.Argument(...)) -> None:
    """Reverse ``pin``."""
    _clear_override(ctx, fact_key, "pinned")


@app.command("supersede")
def supersede(
    ctx: typer.Context,
    fact_key: str = typer.Argument(..., help="The older fact"),
    by: str = typer.Option(..., "--by", help="The fact key that replaces it"),
) -> None:
    """Mark a fact superseded by another, by hand."""
    _patch_override(ctx, fact_key, {"superseded_by": by})


@app.command("unsupersede")
def unsupersede(ctx: typer.Context, fact_key: str = typer.Argument(...)) -> None:
    """Reverse ``supersede``."""
    _clear_override(ctx, fact_key, "superseded_by")


@app.command("settle")
def settle(
    ctx: typer.Context,
    fact_key: str = typer.Argument(..., help="One side of the conflict"),
    winner: str = typer.Option(..., "--winner", help="The fact key that wins"),
) -> None:
    """Settle a conflict this fact was flagged in."""
    _patch_override(ctx, fact_key, {"conflict_choice": winner})


@app.command("unsettle")
def unsettle(ctx: typer.Context, fact_key: str = typer.Argument(...)) -> None:
    """Reverse ``settle``."""
    _clear_override(ctx, fact_key, "conflict_choice")


@app.command("overrides")
def list_overrides(ctx: typer.Context, output_json: bool = typer.Option(False, "--json")) -> None:
    """List every developer decision on record."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/memory/overrides")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Memory overrides")
    for col in _OVERRIDE_FIELDS:
        table.add_column(col)
    table.add_column("fact_key")
    for o in data["overrides"]:
        table.add_row(*(str(o[f]) for f in _OVERRIDE_FIELDS), o["fact_key"])
    _console.print(table)


@app.command("delivery")
def delivery_status(
    ctx: typer.Context,
    agent: str = typer.Option("", "--agent", help="Restrict to one agent"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show per-agent delivery installation state and last-fired time (FR-055)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/memory/delivery", params={"agent": agent} if agent else None)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Memory delivery")
    table.add_column("agent")
    table.add_column("installed")
    table.add_column("last fired")
    table.add_column("command")
    for d in data["delivery"]:
        table.add_row(d["agent"], str(d["installed"]), d["last_fired_at"] or "never", d["command"])
    _console.print(table)


@app.command("delivery-install")
def delivery_install(ctx: typer.Context, agent: str = typer.Argument(...)) -> None:
    """Install Coffer's session-start hook for an agent (FR-054)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/memory/delivery/{agent}/install")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))


@app.command("delivery-remove")
def delivery_remove(ctx: typer.Context, agent: str = typer.Argument(...)) -> None:
    """Remove Coffer's session-start hook for an agent."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/memory/delivery/{agent}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))
