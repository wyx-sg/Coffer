"""`coffer kb …` — knowledge_base CLI commands."""

from __future__ import annotations

import json as _json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from coffer.domain.knowledge_base.config import DEFAULT_EMBEDDING_MODEL
from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Manage knowledge bases")
_console = Console()


@app.command("create")
def create(
    name: str = typer.Argument(...),
    description: str | None = typer.Option(None, "--description"),
    search_mode: str = typer.Option(
        "keyword",
        "--search-mode",
        help="keyword (plain text, no embeddings — default) or semantic (vector search)",
    ),
    embedding_model: str = typer.Option(DEFAULT_EMBEDDING_MODEL, "--embedding-model"),
    chunk_size: int = typer.Option(512, "--chunk-size"),
    chunk_overlap: int = typer.Option(64, "--chunk-overlap"),
    max_document_mb: int = typer.Option(25, "--max-document-mb"),
) -> None:
    """Create a new knowledge base."""
    body = {
        "name": name,
        "description": description,
        "config": {
            "search_mode": search_mode,
            "embedding_model": embedding_model,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "max_document_bytes": max_document_mb * 1024 * 1024,
        },
    }
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/knowledge_bases", json=body)
        if r.status_code == 409:
            typer.echo(f"knowledge_base {name!r} already exists", err=True)
            raise typer.Exit(5)
        if r.status_code in (400, 422):
            typer.echo(f"invalid config: {r.text}", err=True)
            raise typer.Exit(6)
        r.raise_for_status()
    typer.echo(f"created: knowledge_base:{name}")


@app.command("list")
def list_kbs(
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List knowledge bases."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/knowledge_bases")
        r.raise_for_status()
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Knowledge bases")
    table.add_column("name")
    table.add_column("description")
    table.add_column("embedding_model")
    for kb in data["knowledge_bases"]:
        table.add_row(
            kb["name"],
            kb.get("description") or "",
            kb["config"]["embedding_model"],
        )
    _console.print(table)


@app.command("describe")
def describe(
    name: str,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one KB's config + metrics."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge_bases/{name}")
        if r.status_code == 404:
            typer.echo(f"knowledge_base:{name} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
        kb = r.json()
        m = c.get(f"/knowledge_bases/{name}/metrics")
        m.raise_for_status()
        metrics = m.json()
    if output_json:
        typer.echo(_json.dumps({"knowledge_base": kb, "metrics": metrics}, indent=2))
        return
    typer.echo(f"name:       {kb['name']}")
    typer.echo(f"ref:        {kb['ref']}")
    typer.echo(f"enabled:    {kb['enabled']}")
    typer.echo(f"description:{kb.get('description') or ''}")
    typer.echo(f"config:     {_json.dumps(kb['config'], indent=2)}")
    typer.echo(f"documents:  {metrics['document_count']}")
    typer.echo(f"disk_bytes: {metrics['disk_bytes']}")


@app.command("ingest")
def ingest(
    name: str = typer.Argument(...),
    path: Path = typer.Argument(  # noqa: B008
        ..., exists=True, dir_okay=False, readable=True
    ),
    replace: bool = typer.Option(False, "--replace"),
) -> None:
    """Ingest a single file into the knowledge base."""
    c, _info = _cli_client.client_or_exit()
    with c:
        with path.open("rb") as fp:
            files = {"file": (path.name, fp, "application/octet-stream")}
            data = {"replace": str(replace).lower()}
            r = c.post(
                f"/knowledge_bases/{name}/documents",
                files=files,
                data=data,
            )
        if r.status_code == 404:
            typer.echo(f"knowledge_base:{name} not found", err=True)
            raise typer.Exit(4)
        if r.status_code == 409:
            typer.echo("duplicate document — pass --replace to overwrite", err=True)
            raise typer.Exit(5)
        if r.status_code == 413:
            typer.echo("file too large", err=True)
            raise typer.Exit(6)
        if r.status_code == 400:
            typer.echo(f"rejected: {r.text}", err=True)
            raise typer.Exit(6)
        if r.status_code == 503:
            typer.echo("KB engine unavailable", err=True)
            raise typer.Exit(7)
        r.raise_for_status()
    out = r.json()
    typer.echo(f"ingested {path.name} → id={out['id']} ({out['chunk_count']} chunks)")


@app.command("list-docs")
def list_docs(
    name: str = typer.Argument(...),
    limit: int = typer.Option(50, "--limit"),
    offset: int = typer.Option(0, "--offset"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List documents in a knowledge base."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(
            f"/knowledge_bases/{name}/documents",
            params={"limit": limit, "offset": offset},
        )
        if r.status_code == 404:
            typer.echo(f"knowledge_base:{name} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title=f"Documents in {name} (total: {data['total']})")
    table.add_column("id")
    table.add_column("filename")
    table.add_column("size")
    table.add_column("chunks")
    for d in data["documents"]:
        table.add_row(
            d["id"],
            d["filename"],
            str(d["size_bytes"]),
            str(d["chunk_count"]),
        )
    _console.print(table)


@app.command("search")
def search(
    name: str = typer.Argument(...),
    query: str = typer.Argument(...),
    top_k: int = typer.Option(5, "--top-k"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Search a knowledge base."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            f"/knowledge_bases/{name}/search",
            json={"query": query, "top_k": top_k},
        )
        if r.status_code == 404:
            typer.echo(f"knowledge_base:{name} not found", err=True)
            raise typer.Exit(4)
        if r.status_code == 503:
            typer.echo("KB engine unavailable", err=True)
            raise typer.Exit(7)
        r.raise_for_status()
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    for i, h in enumerate(data["hits"], start=1):
        typer.echo(f"{i}. {h['filename']} (score={h['score']:.3f})")
        snippet = h["text"][:300]
        typer.echo(f"  {snippet}")


@app.command("delete-doc")
def delete_doc(
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
) -> None:
    """Delete a single document by id."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/knowledge_bases/{name}/documents/{document_id}")
        if r.status_code == 404:
            typer.echo("document not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    typer.echo(f"deleted document {document_id} from {name}")


@app.command("delete-kb")
def delete_kb(
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    """Delete an entire knowledge base (raw files + index + rows)."""
    if not yes and not typer.confirm(f"Really delete knowledge_base:{name} and all its documents?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/resources/knowledge_base/{name}")
        if r.status_code == 404:
            typer.echo(f"knowledge_base:{name} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    typer.echo(f"deleted: knowledge_base:{name}")
