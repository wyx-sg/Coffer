"""``coffer vault problems`` — hand edits the vault refused (spec vault-storage
"Keep the last valid version when a hand edit is invalid").

No page lists them, and editing files directly is the main way to change
knowledge, so this stays on the command line.
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(
    help="Hand edits the vault refused",
    no_args_is_help=True,
)
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


@app.command("problems")
def problems(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List hand edits that were refused: still on disk, not in effect until fixed."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/vault/problems")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    if not data["problems"]:
        typer.echo("no problems: every file on disk is in effect")
        return
    table = Table(title="Hand edits kept out (the last valid version stays in effect)")
    for column in ("path", "problem", "detail"):
        table.add_column(column)
    for p in data["problems"]:
        table.add_row(p["path"], p["code"], p["message"])
    _console.print(table)
