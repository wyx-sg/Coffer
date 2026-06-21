"""coffer agent native-memory / import-native-memory (spec 004, FR-040/FR-041).

Wraps the two spec-004 routes so every agent-workspace op exists on BOTH REST
and CLI (FR-009):

  * ``GET  /agents/{name}/native-memory``        → ``native-memory`` (read)
  * ``POST /agents/{name}/native-memory/import`` → ``import-native-memory``

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


def import_native_memory(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    memory_dir: str = typer.Argument(..., help="Absolute path to the native memory store"),
) -> None:
    """Adopt one native memory store into the matching Coffer project memory.

    A store that cannot be mapped to a Coffer project (not a git project, or an
    unresolvable path) yields a zero-import result, never an error.
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/agents/{name}/native-memory/import", json={"memory_dir": memory_dir})
        if r.status_code == 404:
            typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if data["store"] is None:
        typer.echo("could not map to a Coffer project (not a git project)")
        return
    typer.echo(
        f"imported {data['imported']} (skipped {data['skipped']}) "
        f"into {data['store']}; organizing in background"
    )


def attach(agent_app: typer.Typer) -> None:
    """Register the native-memory commands on agent_cmd's existing typer."""
    agent_app.command("native-memory")(native_memory)
    agent_app.command("import-native-memory")(import_native_memory)
