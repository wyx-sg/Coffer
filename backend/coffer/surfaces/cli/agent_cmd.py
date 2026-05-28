"""coffer agent ... commands."""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Manage registered AI agents")
_console = Console()


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List registered agents."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/agents")
        _cli_client.check(r, verbose=verbose)
    items = r.json()["items"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    table = Table(title="Agents")
    for col in ("Name", "Type", "Skill Dir", "Auto", "Enabled"):
        table.add_column(col)
    for it in items:
        table.add_row(
            it["name"],
            it["type"],
            it["skill_dir"],
            "✓" if it["auto_detected"] else "",
            "✓" if it["enabled"] else "✗",
        )
    _console.print(table)


@app.command("add")
def add(
    ctx: typer.Context,
    agent_type: str = typer.Argument(..., help="claude_code | claude_desktop | cursor | codex_cli"),
    name: str = typer.Option(..., "--name", "-n", help="Resource name (unique within `agent`)."),
    skill_dir: str | None = typer.Option(None, "--skill-dir", help="Override default path."),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Register an agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    body = {
        "type": agent_type,
        "name": name,
        "skill_dir": skill_dir,
        "description": description,
    }
    with c:
        r = c.post("/agents", json=body)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"registered: agent:{name}")


@app.command("show")
def show(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}")
        if r.status_code == 404:
            typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
    else:
        for k in ("name", "type", "skill_dir", "auto_detected", "enabled"):
            typer.echo(f"{k}: {data[k]}")


@app.command("edit")
def edit(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    skill_dir: str | None = typer.Option(None, "--skill-dir"),
    description: str | None = typer.Option(None, "--description"),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled"),
) -> None:
    """Update an agent's fields."""
    if skill_dir is None and description is None and enabled is None:
        typer.echo("nothing to update", err=True)
        raise typer.Exit(1)
    verbose = (ctx.obj or {}).get("verbose", False)
    body: dict[str, object] = {}
    if skill_dir is not None:
        body["skill_dir"] = skill_dir
    if description is not None:
        body["description"] = description
    if enabled is not None:
        body["enabled"] = enabled
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/agents/{name}", json=body)
        if r.status_code == 404:
            typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"updated: agent:{name}")


@app.command("rm")
def rm(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Remove an agent (auto-detected ones are suppressed from future scans)."""
    if not force and not typer.confirm(f"Really remove agent:{name}?"):
        raise typer.Exit(1)
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/agents/{name}")
        if r.status_code == 404:
            typer.echo("not found", err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed: agent:{name}")


@app.command("detect")
def detect(ctx: typer.Context) -> None:
    """Re-run auto-detection."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/agents/detect")
        _cli_client.check(r, verbose=verbose)
    added = r.json()["registered"]
    if not added:
        typer.echo("no new agents detected")
        return
    for a in added:
        typer.echo(f"detected: {a['type']} -> {a['name']} ({a['skill_dir']})")
