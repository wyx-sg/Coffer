"""``coffer knowledge`` — the document half (ingest / read / edit / retrieve).

Registers onto the SAME ``knowledge`` Typer app as ``knowledge_cmd`` by import
side effect (imported by the CLI root right after it), so a scope's entries and
its ingested documents are one command group. Split out only to keep each module
under the project's file-size ceiling.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import typer
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.knowledge_cmd import _console, _verbose, app


@app.command("ingest")
def ingest(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    path: Path = typer.Argument(  # noqa: B008
        ..., exists=True, dir_okay=False, readable=True
    ),
    replace: bool = typer.Option(False, "--replace"),
) -> None:
    """Ingest a single file into a scope (any format → Markdown)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        with path.open("rb") as fp:
            files = {"file": (path.name, fp, "application/octet-stream")}
            # The CLI is a trusted client, so it records the external original's
            # absolute path (enabling later `check-sources` update detection).
            data = {"replace": str(replace).lower(), "source_path": str(path.resolve())}
            r = c.post(f"/knowledge/{name}/documents", files=files, data=data)
        _cli_client.check(r, verbose=_verbose(ctx))
    out = r.json()
    typer.echo(f"ingested {path.name} → id={out['id']} (source_mode={out['source_mode']})")


@app.command("documents")
def list_docs(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    limit: int = typer.Option(50, "--limit"),
    offset: int = typer.Option(0, "--offset"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List the documents ingested into a scope."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge/{name}/documents", params={"limit": limit, "offset": offset})
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title=f"Documents in {name} (total: {data['total']})")
    table.add_column("id")
    table.add_column("title")
    table.add_column("source_mode")
    for d in data["documents"]:
        table.add_row(d["id"], d["title"], d["source_mode"])
    _console.print(table)


@app.command("read")
def read_doc(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print a document's Markdown body."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge/{name}/documents/{document_id}")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(data["markdown"])


@app.command("edit")
def edit(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
    markdown: str = typer.Argument(..., help="New Markdown body (sets source_mode=edited)."),
) -> None:
    """Rewrite a document's Markdown body (reindexes)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put(f"/knowledge/{name}/documents/{document_id}", json={"markdown": markdown})
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"edited document {document_id}")


@app.command("reconvert")
def reconvert(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
) -> None:
    """Re-run conversion from the raw original (blocked once hand-edited)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge/{name}/documents/{document_id}/reconvert")
        _cli_client.check(r, verbose=_verbose(ctx))
    out = r.json()
    typer.echo(f"reconverted document {out['id']} (source_mode={out['source_mode']})")


@app.command("delete-doc")
def delete_doc(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
) -> None:
    """Delete a single document by id."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/knowledge/{name}/documents/{document_id}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted document {document_id} from {name}")


@app.command("reindex")
def reindex(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Rescan a scope's ingested files and rebuild the index from disk."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge/{name}/reindex")
        _cli_client.check(r, verbose=_verbose(ctx))
    out = r.json()
    typer.echo(
        f"reindexed: scanned={out['documents_scanned']} "
        f"reindexed={out['documents_reindexed']} skipped={out['documents_skipped']} "
        f"removed={out.get('documents_removed', 0)} "
        f"degraded={out.get('documents_degraded', 0)}"
    )


@app.command("search")
def search(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    query: str = typer.Argument(...),
    top_k: int = typer.Option(5, "--top-k"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Passage search over a scope (one query → one answer)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge/{name}/search", json={"query": query, "top_k": top_k})
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    for i, p in enumerate(data["passages"], start=1):
        typer.echo(f"{i}. {p['title']} (score={p['score']:.3f})")
        typer.echo(f"  {p['text'][:300]}")


@app.command("grep")
def grep(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    pattern: str = typer.Argument(...),
    max_matches: int = typer.Option(100, "--max-matches"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Grep (ripgrep) over every Markdown file in a scope."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            f"/knowledge/{name}/grep",
            json={"pattern": pattern, "max_matches": max_matches},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    for h in data["hits"]:
        typer.echo(f"{h['path']}:{h['line_number']}: {h['line']}")
    if data.get("truncated"):
        typer.echo("(results truncated)", err=True)
