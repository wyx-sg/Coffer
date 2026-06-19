"""coffer skill search / install — catalog discovery commands (FR-032/FR-033).

Registered on the shared ``skill_cmd.app`` (imported for its side effect in the
CLI root) and split out to keep ``skill_cmd.py`` under the file-size limit.
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.skill_cmd import app

_console = Console()


@app.command("search")
def search(
    query: str = typer.Argument("", help="Substring to match name/description/publisher."),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Browse/search the skill catalog for installable skills."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/catalog/skills", params={"q": query} if query else None)
        r.raise_for_status()
    items = r.json()["items"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    if not items:
        typer.echo("no matching catalog skills")
        return
    table = Table(title="Skill catalog")
    for col in ("Name", "Publisher", "Description"):
        table.add_column(col)
    for e in items:
        table.add_row(e["name"], e["publisher"], e["description"])
    _console.print(table)


@app.command("install")
def install(
    name: str = typer.Argument(..., help="Catalog skill name (see `coffer skill search`)."),
) -> None:
    """Install a skill from the catalog (fetches + validates + scans it)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/catalog/skills/{name}/install", timeout=120)
        if r.status_code >= 400:
            typer.echo(r.json().get("error", {}).get("message", str(r.text)), err=True)
            raise typer.Exit(2)
    typer.echo(f"installed: skill:{r.json()['name']}")
