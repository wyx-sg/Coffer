"""`coffer kb …` — knowledge_base CLI commands (spec 006 redesign).

Thin HTTP shells over the daemon's REST surface, matching the existing CLI
patterns + exit-code mapping (`_cli_client.check`). Retrieval has three modes:
grep / keyword / vector.
"""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Manage knowledge bases")
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


@app.command("create")
def create(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    description: str | None = typer.Option(None, "--description"),
    mode: list[str] = typer.Option(  # noqa: B008
        ["keyword", "grep"],
        "--mode",
        help="Enabled retrieval modes (repeatable): grep / keyword / vector.",
    ),
    default_mode: str = typer.Option("keyword", "--default-mode"),
    chunk_size: int = typer.Option(512, "--chunk-size"),
    chunk_overlap: int = typer.Option(64, "--chunk-overlap"),
    max_document_mb: int = typer.Option(25, "--max-document-mb"),
) -> None:
    """Create a new knowledge base."""
    body = {
        "name": name,
        "description": description,
        "config": {
            "enabled_modes": mode,
            "default_mode": default_mode,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "max_document_bytes": max_document_mb * 1024 * 1024,
        },
    }
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/knowledge_bases", json=body)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"created: knowledge_base:{name}")


@app.command("list")
def list_kbs(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List knowledge bases."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/knowledge_bases")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Knowledge bases")
    table.add_column("name")
    table.add_column("description")
    table.add_column("modes")
    for kb in data["knowledge_bases"]:
        table.add_row(
            kb["name"],
            kb.get("description") or "",
            ",".join(kb["config"]["enabled_modes"]),
        )
    _console.print(table)


@app.command("describe")
def describe(
    ctx: typer.Context,
    name: str,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one KB's config + metrics."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge_bases/{name}")
        _cli_client.check(r, verbose=_verbose(ctx))
        kb = r.json()
        m = c.get(f"/knowledge_bases/{name}/metrics")
        _cli_client.check(m, verbose=_verbose(ctx))
        metrics = m.json()
    if output_json:
        typer.echo(_json.dumps({"knowledge_base": kb, "metrics": metrics}, indent=2))
        return
    typer.echo(f"name:        {kb['name']}")
    typer.echo(f"ref:         {kb['ref']}")
    typer.echo(f"enabled:     {kb['enabled']}")
    typer.echo(f"description: {kb.get('description') or ''}")
    typer.echo(f"config:      {_json.dumps(kb['config'], indent=2)}")
    typer.echo(f"documents:   {metrics['document_count']}")
    typer.echo(f"chunks:      {metrics['chunk_count']}")
    typer.echo(f"disk_bytes:  {metrics['disk_bytes']}")


@app.command("ingest")
def ingest(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    path: Path = typer.Argument(  # noqa: B008
        ..., exists=True, dir_okay=False, readable=True
    ),
    replace: bool = typer.Option(False, "--replace"),
) -> None:
    """Ingest a single file into the knowledge base (any format → Markdown)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        with path.open("rb") as fp:
            files = {"file": (path.name, fp, "application/octet-stream")}
            # The CLI is a trusted client, so it records the external original's
            # absolute path (enabling later `kb check-sources` update detection).
            data = {"replace": str(replace).lower(), "source_path": str(path.resolve())}
            r = c.post(f"/knowledge_bases/{name}/documents", files=files, data=data)
        _cli_client.check(r, verbose=_verbose(ctx))
    out = r.json()
    typer.echo(f"ingested {path.name} → id={out['id']} (source_mode={out['source_mode']})")


@app.command("list-docs")
def list_docs(
    ctx: typer.Context,
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


@app.command("get-doc")
@app.command("read", help="Alias of get-doc.")
def get_doc(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print a document's Markdown body."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge_bases/{name}/documents/{document_id}")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(data["markdown"])


def _patch_kb_config(
    ctx: typer.Context, name: str, mutate: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    """GET the KB's current config, apply ``mutate(config)``, PATCH it back."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge_bases/{name}")
        _cli_client.check(r, verbose=_verbose(ctx))
        config: dict[str, Any] = r.json()["config"]
        mutate(config)
        patched = c.patch(f"/resources/knowledge_base/{name}", json={"config": config})
        _cli_client.check(patched, verbose=_verbose(ctx))
    return config


@app.command("set-embedding")
def set_embedding(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    provider: str = typer.Option(..., "--provider", help="openai / openrouter / … / local"),
    model: str = typer.Option(..., "--model"),
    dimensions: int = typer.Option(..., "--dimensions"),
    base_url: str | None = typer.Option(None, "--base-url"),
    credential_ref: str | None = typer.Option(
        None, "--credential-ref", help="Stored credential ref (never a raw key)."
    ),
) -> None:
    """Configure embeddings + enable vector mode (re-embeds the corpus)."""

    def mutate(config: dict[str, Any]) -> None:
        config["embedding"] = {
            "provider": provider,
            "model": model,
            "dimensions": dimensions,
            "base_url": base_url,
            "credential_ref": credential_ref,
        }
        modes = list(config.get("enabled_modes") or [])
        if "vector" not in modes:
            modes.append("vector")
        config["enabled_modes"] = modes

    _patch_kb_config(ctx, name, mutate)
    typer.echo(f"embedding set on {name}: {provider}/{model} ({dimensions}d); vector enabled")


@app.command("set-chunking")
def set_chunking(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    chunk_size: int = typer.Option(..., "--chunk-size"),
    chunk_overlap: int = typer.Option(..., "--chunk-overlap"),
) -> None:
    """Change chunk parameters (re-chunks/re-indexes the corpus)."""

    def mutate(config: dict[str, Any]) -> None:
        config["chunk_size"] = chunk_size
        config["chunk_overlap"] = chunk_overlap

    _patch_kb_config(ctx, name, mutate)
    typer.echo(f"chunking set on {name}: size={chunk_size} overlap={chunk_overlap}")


@app.command("reconvert")
def reconvert(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
) -> None:
    """Re-run conversion from the raw source (blocked once hand-edited)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge_bases/{name}/documents/{document_id}/reconvert")
        _cli_client.check(r, verbose=_verbose(ctx))
    out = r.json()
    typer.echo(f"reconverted document {out['id']} (source_mode={out['source_mode']})")


@app.command("edit")
def edit(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
    markdown: str = typer.Argument(..., help="New Markdown body (sets source_mode=edited)."),
) -> None:
    """Edit a document's Markdown body (reindexes)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put(
            f"/knowledge_bases/{name}/documents/{document_id}",
            json={"markdown": markdown},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"edited document {document_id}")


@app.command("reindex")
def reindex(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Rescan files and rebuild the index from disk."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge_bases/{name}/reindex")
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
    mode: str | None = typer.Option(None, "--mode", help="keyword / vector (overrides default)."),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Search a knowledge base (keyword / vector)."""
    payload: dict[str, object] = {"query": query, "top_k": top_k}
    if mode is not None:
        payload["mode"] = mode
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge_bases/{name}/search", json=payload)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    if data.get("fallback"):
        typer.echo(f"(vector unavailable — fell back to {data['fallback']})", err=True)
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
    """Grep (ripgrep) over the KB's Markdown files."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            f"/knowledge_bases/{name}/grep",
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


@app.command("delete-doc")
def delete_doc(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    document_id: str = typer.Argument(...),
) -> None:
    """Delete a single document by id."""
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
    """Delete an entire knowledge base (raw files + index + rows)."""
    if not yes and not typer.confirm(f"Really delete knowledge_base:{name} and all its documents?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/resources/knowledge_base/{name}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted: knowledge_base:{name}")
