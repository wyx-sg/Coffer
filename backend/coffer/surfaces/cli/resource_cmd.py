"""coffer resource ... commands."""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Manage resources (kind-agnostic)")
_console = Console()


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    kind: str | None = typer.Option(None, "--kind", help="Filter by kind"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List all registered resources."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        params = {"kind": kind} if kind else {}
        r = c.get("/resources", params=params)
        _cli_client.check(r, verbose=verbose)
    data = r.json()["resources"]
    if output_json:
        typer.echo(_json.dumps({"resources": data}, indent=2))
        return
    table = Table(title="Resources")
    table.add_column("Ref")
    table.add_column("Kind")
    table.add_column("Name")
    table.add_column("Enabled")
    for item in data:
        table.add_row(item["ref"], item["kind"], item["name"], str(item["enabled"]))
    _console.print(table)


@app.command("show")
def show(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="<kind>:<name>"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show details of a single resource."""
    verbose = (ctx.obj or {}).get("verbose", False)
    kind, _, name = ref.partition(":")
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/resources/{kind}/{name}")
        if r.status_code == 404:
            typer.echo(r.json()["error"]["message"], err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
    else:
        typer.echo(f"ref:      {data['ref']}")
        typer.echo(f"enabled:  {data['enabled']}")
        typer.echo(f"config:   {_json.dumps(data['config'])}")


@app.command("enable")
def enable(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="<kind>:<name>"),
) -> None:
    """Enable a resource."""
    verbose = (ctx.obj or {}).get("verbose", False)
    kind, _, name = ref.partition(":")
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/resources/{kind}/{name}/enable")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"enabled: {ref}")


@app.command("disable")
def disable(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="<kind>:<name>"),
) -> None:
    """Disable a resource."""
    verbose = (ctx.obj or {}).get("verbose", False)
    kind, _, name = ref.partition(":")
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/resources/{kind}/{name}/disable")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"disabled: {ref}")


@app.command("delete")
def delete(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="<kind>:<name>"),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Delete a resource."""
    verbose = (ctx.obj or {}).get("verbose", False)
    if not force and not typer.confirm(f"Really delete {ref}?"):
        raise typer.Exit(1)
    kind, _, name = ref.partition(":")
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/resources/{kind}/{name}")
        if r.status_code == 404:
            typer.echo(r.json()["error"]["message"], err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"deleted: {ref}")
