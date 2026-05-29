"""coffer audit ... commands."""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Query the audit log")
_console = Console()


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    kind: str | None = typer.Option(None, "--kind", help="Filter by resource kind"),
    name: str | None = typer.Option(None, "--name", help="Filter by resource name"),
    event_type: str | None = typer.Option(None, "--event-type", help="Filter by event type"),
    since: str | None = typer.Option(None, "--since", help="ISO 8601 datetime lower bound"),
    limit: int = typer.Option(50, "--limit", help="Maximum entries to return (1-500)"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List audit log entries."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        params: dict[str, str | int] = {"limit": limit}
        if kind is not None:
            params["kind"] = kind
        if name is not None:
            params["name"] = name
        if event_type is not None:
            params["event_type"] = event_type
        if since is not None:
            params["since"] = since
        r = c.get("/audit", params=params)
        _cli_client.check(r, verbose=verbose)
    entries = r.json()["entries"]
    if output_json:
        typer.echo(_json.dumps({"audit_events": entries}, indent=2))
        return
    table = Table(title="Audit Log")
    table.add_column("Timestamp")
    table.add_column("Event Type")
    table.add_column("Resource")
    table.add_column("Actor")
    for entry in entries:
        resource_kind = entry.get("resource_kind") or ""
        resource_name = entry.get("resource_name") or ""
        resource = f"{resource_kind}:{resource_name}" if resource_kind else ""
        table.add_row(
            entry["timestamp"],
            entry["event_type"],
            resource,
            entry["actor"],
        )
    _console.print(table)
