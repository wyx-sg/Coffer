"""coffer resource ... commands.

Every command here takes a KIND and a NAME, because that is what a person
knows. The uid the daemon addresses resources by is looked up once, in
``_resolve``, and never asked of the user
(ADR resource-identity-is-an-immutable-uid).

The ``<kind>:<name>`` argument these commands used to take is gone with the
string form itself: two arguments say the same thing without inventing a
syntax, and without leaving a spelling of identity alive for a reader to
mistake for one.
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

app = typer.Typer(help="Manage resources (kind-agnostic)")
_console = Console()

_KIND = typer.Argument(..., help="Resource kind, e.g. mcp_server")
_NAME = typer.Argument(..., help="Resource name")


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
    table.add_column("Kind")
    table.add_column("Name")
    table.add_column("Enabled")
    # The uid is deliberately NOT a column. It is an address, not information —
    # nobody reading a list is looking for one, and a column of them would
    # crowd out the two things a reader actually scans. `--json` carries it for
    # a script that wants to act on a row.
    for item in data:
        table.add_row(item["kind"], item["name"], str(item["enabled"]))
    _console.print(table)


@app.command("show")
def show(
    ctx: typer.Context,
    kind: str = _KIND,
    name: str = _NAME,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show details of a single resource."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, kind, name, verbose=verbose)
        r = c.get(f"/resources/{uid}")
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
    else:
        typer.echo(f"kind:     {data['kind']}")
        typer.echo(f"name:     {data['name']}")
        typer.echo(f"uid:      {data['uid']}")
        typer.echo(f"enabled:  {data['enabled']}")
        typer.echo(f"config:   {_json.dumps(data['config'])}")


@app.command("rename")
def rename(
    ctx: typer.Context,
    kind: str = _KIND,
    name: str = _NAME,
    new_name: str = typer.Argument(..., help="The new name"),
) -> None:
    """Rename a resource.

    A label change and nothing else: the resource keeps its identity, so its
    reach, its credentials, its bindings and its history all follow it without
    being rewritten. Available for every kind — while the name WAS the
    identity, only connections could be renamed at all.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, kind, name, verbose=verbose)
        r = c.patch(f"/resources/{uid}", json={"name": new_name})
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"renamed: {kind} {name} → {r.json()['name']}")


@app.command("enable")
def enable(
    ctx: typer.Context,
    kind: str = _KIND,
    name: str = _NAME,
) -> None:
    """Enable a resource."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, kind, name, verbose=verbose)
        r = c.post(f"/resources/{uid}/enable")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"enabled: {kind} {name}")


@app.command("disable")
def disable(
    ctx: typer.Context,
    kind: str = _KIND,
    name: str = _NAME,
) -> None:
    """Disable a resource."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, kind, name, verbose=verbose)
        r = c.post(f"/resources/{uid}/disable")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"disabled: {kind} {name}")


@app.command("delete")
def delete(
    ctx: typer.Context,
    kind: str = _KIND,
    name: str = _NAME,
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Delete a resource."""
    verbose = (ctx.obj or {}).get("verbose", False)
    if not force and not typer.confirm(f"Really delete {kind} {name}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, kind, name, verbose=verbose)
        r = c.delete(f"/resources/{uid}")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"deleted: {kind} {name}")
