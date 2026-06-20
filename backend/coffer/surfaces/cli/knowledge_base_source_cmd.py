"""`coffer kb check-sources` / `update-source` — external source-file tracking.

Split out of ``knowledge_base_cmd.py`` to keep that module under the file-size
ceiling. These commands register onto the SAME ``kb`` Typer ``app`` (imported
from ``knowledge_base_cmd``); importing this module (done by the CLI root) is
what attaches them. Thin HTTP shells, like the rest of the ``kb`` subcommands.
"""

from __future__ import annotations

import json as _json

import typer
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.knowledge_base_cmd import _console, _verbose, app


@app.command("check-sources")
def check_sources(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Detect whether path-tracked documents' external originals have changed."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge_bases/{name}/check-sources")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title=f"Source status for {name}")
    table.add_column("document_id")
    table.add_column("title")
    table.add_column("status")
    table.add_column("source_path")
    for s in data["sources"]:
        table.add_row(s["document_id"], s["title"], s["status"], s["source_path"])
    _console.print(table)


@app.command("update-source")
def update_source(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
) -> None:
    """Re-ingest a document from its tracked external source (blocked once edited)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge_bases/{name}/documents/{document_id}/update-source")
        _cli_client.check(r, verbose=_verbose(ctx))
    out = r.json()
    typer.echo(f"updated document {out['id']} from source (source_mode={out['source_mode']})")
