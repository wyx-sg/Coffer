"""coffer retention ... commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Manage data retention policies")
_console = Console()


@app.command("list")
def list_cmd(ctx: typer.Context) -> None:
    """List all retention policies."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/retention/policies")
        _cli_client.check(r, verbose=verbose)
    policies = r.json()["policies"]
    table = Table(title="Retention Policies")
    table.add_column("Table")
    table.add_column("Retention Days")
    table.add_column("Last Pruned At")
    table.add_column("Last Pruned Rows")
    for p in policies:
        days = str(p["retention_days"]) if p["retention_days"] is not None else "forever"
        last_at = p.get("last_pruned_at") or "—"
        last_rows = str(p.get("last_pruned_rows") or 0)
        table.add_row(p["table_name"], days, last_at, last_rows)
    _console.print(table)


@app.command("set")
def set_cmd(
    ctx: typer.Context,
    table: str = typer.Argument(..., help="Table name to configure"),
    days: int | None = typer.Option(None, "--days", help="Retention in days (>=1)"),
    forever: bool = typer.Option(False, "--forever", help="Keep rows forever (no pruning)"),
) -> None:
    """Set retention policy for a table."""
    verbose = (ctx.obj or {}).get("verbose", False)
    if forever and days is not None:
        typer.echo("Cannot use --forever and --days together", err=True)
        raise typer.Exit(1)
    if not forever and days is None:
        typer.echo("Specify --days N or --forever", err=True)
        raise typer.Exit(1)
    retention_days = None if forever else days
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/retention/policies/{table}", json={"retention_days": retention_days})
        if r.status_code == 404:
            typer.echo(r.json()["error"]["message"], err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    label = "forever" if forever else f"{days}d"
    typer.echo(f"retention for {table}: {label}")


@app.command("prune-now")
def prune_now(
    ctx: typer.Context,
    table: str | None = typer.Option(None, "--table", help="Prune a specific table only"),
) -> None:
    """Trigger an immediate prune run."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    payload: dict[str, object] = {}
    if table is not None:
        payload["table_name"] = table
    with c:
        r = c.post("/retention/prune", json=payload)
        _cli_client.check(r, verbose=verbose)
    result = r.json()["tables"]
    for tbl, rows in result.items():
        typer.echo(f"pruned {tbl}: {rows} rows deleted")
    if not result:
        typer.echo("nothing to prune")
