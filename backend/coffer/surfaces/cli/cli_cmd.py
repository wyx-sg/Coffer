"""coffer cli — the command-line tools Coffer manages, for an agent to read.

The CLIs page is where a person manages them; this is the one read an agent
makes instead, because it has no page (spec skill-manager "Serve required
commands on REST and the web"). The coffer-guide skill names it. It reads what
Coffer last found — ``GET /api/v1/clis`` — and never runs a check, so it starts
no program and runs no login check.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Read the command-line tools Coffer manages.")
_console = Console()


def _needed_by(item: dict[str, Any]) -> str:
    users = [f"skill {n['skill_name']}" for n in item.get("needed_by", [])]
    users += [f"MCP server {s['server_name']}" for s in item.get("needed_by_servers", [])]
    if item.get("added"):
        users.append("added by hand")
    return ", ".join(users)


def _about(item: dict[str, Any]) -> str:
    parts = [p for p in (item.get("title"), item.get("description")) if p]
    return " — ".join(parts)


@app.command("list")
def list_clis(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List every command-line tool Coffer manages, problems first.

    The tools skills require, the launchers MCP servers start with, and the
    tools the developer added by hand: what each is for, who needs it, and
    whether it is ready, missing, outdated or logged out on this machine as of
    Coffer's last check. --json carries the full rows, including the prompt
    for an agent to install, update or log in to one that needs it.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/clis")
        _cli_client.check(r, verbose=verbose)
        items: list[dict[str, Any]] = r.json().get("items", [])
    if output_json:
        typer.echo(_json.dumps({"items": items}))
        return
    if not items:
        typer.echo("(no command-line tools: no skill or MCP server requires one, none added)")
        return
    table = Table(title="Command-line tools")
    table.add_column("Command")
    table.add_column("Status")
    table.add_column("Version")
    table.add_column("What it is for")
    table.add_column("Needed by")
    for item in items:
        table.add_row(
            item["command"],
            str(item.get("status", "")).replace("_", " "),
            item.get("version") or "—",
            _about(item) or "—",
            _needed_by(item) or "—",
        )
    _console.print(table)


__all__ = ["app"]
