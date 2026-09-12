"""coffer agent native-memory — read the agent's OWN native memory stores.

Every agent-workspace operation exists on BOTH REST and CLI (spec
agent-registry FR-009/FR-010); this is the CLI half of

  ``GET /agents/{name}/native-memory`` → ``coffer agent native-memory <name>``

Read-only, like the route: it lists the stores and never writes them.

Kept out of ``agent_cmd.py`` to respect the 400-line backend file cap; the same
``attach``-on-the-existing-typer pattern as ``agent_workspace_cmd.py`` keeps the
user-facing tree at ``coffer agent native-memory ...``.
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def native_memory(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List the agent's OWN native per-project memory stores (read-only)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}/native-memory")
        if r.status_code == 404:
            typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=_verbose(ctx))
    items = r.json()["items"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    if not items:
        typer.echo("(no native memory)")
        return
    table = Table(title=f"Native memory — {name}")
    for col in ("Project", "Items", "Path"):
        table.add_column(col)
    for it in items:
        table.add_row(it["project"], str(it["item_count"]), it["path"] or "")
    _console.print(table)


def attach(agent_app: typer.Typer) -> None:
    """Register the native-memory command on agent_cmd's existing typer."""
    agent_app.command("native-memory")(native_memory)
