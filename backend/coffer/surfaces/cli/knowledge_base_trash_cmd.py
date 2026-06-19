"""KB CLI: recoverable delete (trash / restore) + destructive ops (ADR-030).

Split out of ``knowledge_base_cmd`` to keep that module under the file-size cap;
these commands register onto the same ``kb`` Typer app it defines.
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.knowledge_base_cmd import _verbose, app

_console = Console()


@app.command("delete-doc")
def delete_doc(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
) -> None:
    """Delete a document. A live document moves to the recoverable trash; a
    document already in the trash is purged for good (ADR-030)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/knowledge_bases/{name}/documents/{document_id}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted document {document_id} from {name}")


@app.command("delete-kb")
def delete_kb(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    """Delete an entire knowledge base (raw files + index + rows, incl. trash)."""
    if not yes and not typer.confirm(f"Really delete knowledge_base:{name} and all its documents?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/resources/knowledge_base/{name}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted: knowledge_base:{name}")


@app.command("trash")
def trash(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List a knowledge base's trashed (soft-deleted) documents."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge_bases/{name}/documents", params={"deleted": "true"})
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title=f"Trash in {name} (total: {data['total']})")
    table.add_column("id")
    table.add_column("title")
    table.add_column("deleted_at")
    for d in data["documents"]:
        table.add_row(d["id"], d["title"], d.get("deleted_at") or "")
    _console.print(table)


@app.command("restore")
def restore(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
) -> None:
    """Restore a trashed document (re-converted from its kept original)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge_bases/{name}/documents/{document_id}/restore")
        _cli_client.check(r, verbose=_verbose(ctx))
    out = r.json()
    typer.echo(f"restored document {out['id']} in {name} (source_mode={out['source_mode']})")
