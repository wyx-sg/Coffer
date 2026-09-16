"""``coffer memory …`` — the memory layer from the terminal (spec memory FR-028).

Every command but one is a thin HTTP shell over the daemon, matching
``knowledge_cmd.py``. ``context`` is the exception: it is the exact command
an agent's own session-start hook invokes
(``domain.memory.delivery.hook_command``), so it must be fast and must never
fail a session — no detect-or-spawn, a short timeout, and any failure at all
(daemon not running, a slow response, a malformed one) degrades to printing
nothing and exiting 0. FR-026 exists precisely because the previous injection
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
        for col in ("key", "slug", "title", "type", "status"):
            table.add_column(col)
        for f in data["facts"]:
            table.add_row(f["key"], f["slug"], f["title"], f["type"], f["status"])
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


@app.command("ls")
def list_files(
    ctx: typer.Context,
    partition: str = typer.Argument(..., help="Partition name (or 'global')"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List a partition's own directory as a tree (FR-029).

    The whole tree rather than one level, unlike `coffer knowledge ls`: a
    partition is two levels deep by construction (a README, a `facts/` folder,
    a file per fact), so stopping at the root would never show a fact.
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/memory/partitions/{partition}/files")
        _cli_client.check(r, verbose=_verbose(ctx))

    def render(data: dict[str, Any]) -> None:
        table = Table(title=f"memory:{partition}")
        table.add_column("path")
        table.add_column("type")
        table.add_column("size", justify="right")
        for node in _walk(data["root"]):
            size = node.get("size")
            table.add_row(
                node["path"] + ("/" if node["type"] == "dir" else ""),
                node["type"],
                "" if size is None else str(size),
            )
        _console.print(table)

    _echo_json_or(ctx, r.json(), output_json, render)


def _walk(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Every descendant of ``node``, depth-first, excluding the root itself.

    The root's own path is ``""`` — a row for it would say nothing and sort
    above everything, so it is the one node left out.
    """
    out: list[dict[str, Any]] = []
    for child in node.get("children", []):
        out.append(child)
        out.extend(_walk(child))
    return out


@app.command("read")
def read_file(
    ctx: typer.Context,
    partition: str = typer.Argument(..., help="Partition name (or 'global')"),
    path: str = typer.Argument(..., help="File path inside the partition, e.g. facts/foo.md"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print one file out of a partition's directory.

    Read-only, like the route: everything under ``~/.coffer/memory/`` is
    derived (FR-016), so there is no matching write for an edit to survive.
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/memory/partitions/{partition}/files/content", params={"path": path})
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    if data["binary"]:
        typer.echo(f"{data['path']}: binary file, {data['size']} bytes")
        return
    typer.echo(data["content"])
    if data["truncated"]:
        typer.echo("… truncated", err=True)


@app.command("sync")
def sync(ctx: typer.Context, output_json: bool = typer.Option(False, "--json")) -> None:
    """Run aggregation: read every registered agent's native memory."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/memory/sync")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2) if output_json else r.text)


@app.command("organise")
def organise(
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


@app.command("delivery")
def delivery_status(
    ctx: typer.Context,
    agent: str = typer.Option("", "--agent", help="Restrict to one agent"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show per-agent delivery installation state (FR-025)."""
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
    table.add_column("command")
    for d in data["delivery"]:
        table.add_row(d["agent"], str(d["installed"]), d["command"])
    _console.print(table)


@app.command("delivery-install")
def delivery_install(ctx: typer.Context, agent: str = typer.Argument(...)) -> None:
    """Install Coffer's session-start hook for an agent (FR-025)."""
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
