"""``coffer knowledge …`` — the one knowledge CLI (was ``memory`` + ``kb``).

Thin HTTP shells over the daemon, matching the existing CLI patterns and
exit-code mapping (``_cli_client.check``). One command group over three scopes:
``global`` and ``project-<ulid>`` auto-provision (the user never "creates" one),
a named collection is created with ``create`` and removed with ``delete``.

The document half (ingest / read / edit / reindex / search / grep) lives in
``knowledge_document_cmd`` and external-source tracking in
``knowledge_source_cmd``; both register onto the SAME ``app`` by import side
effect, purely so no module runs past the project's file-size ceiling.
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Manage knowledge scopes (entries + documents)")
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


@app.command("list")
def list_scopes(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List every knowledge scope."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/knowledge")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Knowledge scopes")
    table.add_column("name")
    table.add_column("scope")
    table.add_column("entries")
    table.add_column("documents")
    table.add_column("description")
    table.add_column("modes")
    for s in data["scopes"]:
        table.add_row(
            s["name"],
            s["scope"],
            str(s["entry_count"]),
            str(s["document_count"]),
            s.get("description") or "",
            ",".join(s["config"]["retrieval_modes"]),
        )
    _console.print(table)


@app.command("describe")
def describe(
    ctx: typer.Context,
    name: str,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one scope's config + metrics."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge/{name}")
        _cli_client.check(r, verbose=_verbose(ctx))
        s = r.json()
        m = c.get(f"/knowledge/{name}/metrics")
        _cli_client.check(m, verbose=_verbose(ctx))
        metrics = m.json()
    if output_json:
        typer.echo(_json.dumps({"scope": s, "metrics": metrics}, indent=2))
        return
    typer.echo(f"name:        {s['name']}")
    typer.echo(f"scope:       {s['scope']}")
    typer.echo(f"ref:         {s['ref']}")
    typer.echo(f"enabled:     {s['enabled']}")
    typer.echo(f"description: {s.get('description') or ''}")
    typer.echo(f"config:      {_json.dumps(s['config'], indent=2)}")
    typer.echo(f"entries:     {metrics['entry_count']}")
    typer.echo(f"documents:   {metrics['document_count']}")
    typer.echo(f"chunks:      {metrics['chunk_count']}")
    typer.echo(f"disk_bytes:  {metrics['disk_bytes']}")


@app.command("create")
def create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Collection name (not 'global' / 'project-*')."),
    description: str | None = typer.Option(None, "--description"),
    enable_vector: bool = typer.Option(
        False,
        "--enable-vector/--no-enable-vector",
        help="Enable vector retrieval (adds 'vector'; the config validator then "
        "auto-adds 'hybrid' and makes it the default). Off → keyword + grep only.",
    ),
    chunk_size: int = typer.Option(512, "--chunk-size"),
    chunk_overlap: int = typer.Option(64, "--chunk-overlap"),
    max_document_mb: int = typer.Option(25, "--max-document-mb"),
) -> None:
    """Create a named collection. ``global`` and per-project scopes are created
    on first use, not here."""
    modes = ["keyword", "grep", "vector"] if enable_vector else ["keyword", "grep"]
    body = {
        "name": name,
        "description": description,
        "config": {
            "retrieval_modes": modes,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "max_document_bytes": max_document_mb * 1024 * 1024,
        },
    }
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/knowledge", json=body)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"created: knowledge:{name}")


@app.command("configure")
def configure(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    enable_vector: bool = typer.Option(
        False, "--enable-vector", help="Add 'vector' to retrieval_modes."
    ),
    max_entry_chars: int | None = typer.Option(None, "--max-entry-chars"),
    chunk_size: int | None = typer.Option(None, "--chunk-size"),
    chunk_overlap: int | None = typer.Option(None, "--chunk-overlap"),
    auto_update_sources: bool | None = typer.Option(
        None,
        "--auto-update-sources/--no-auto-update-sources",
        help="Refresh documents whose tracked external original changed.",
    ),
) -> None:
    """Update a scope's config. Changing a retrieval or chunking field
    re-indexes it; the files on disk stay the source of truth.

    Embedding is installation-wide (``coffer settings``), not per scope — a
    scope only opts in by listing ``vector``."""
    patch: dict[str, object] = {}
    if max_entry_chars is not None:
        patch["max_entry_chars"] = max_entry_chars
    if chunk_size is not None:
        patch["chunk_size"] = chunk_size
    if chunk_overlap is not None:
        patch["chunk_overlap"] = chunk_overlap
    if auto_update_sources is not None:
        patch["auto_update_sources"] = auto_update_sources
    c, _info = _cli_client.client_or_exit()
    with c:
        if enable_vector:
            current = c.get(f"/knowledge/{name}")
            _cli_client.check(current, verbose=_verbose(ctx))
            modes = list(current.json()["config"]["retrieval_modes"])
            if "vector" not in modes:
                modes.append("vector")
            patch["retrieval_modes"] = modes
        if not patch:
            typer.echo("nothing to configure (no options given)", err=True)
            raise typer.Exit(1)
        r = c.patch(f"/knowledge/{name}", json=patch)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"configured {name}")


@app.command("label")
def label(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    text: str | None = typer.Argument(None, help="Display label; omit to clear it."),
) -> None:
    """Set or clear a scope's display label."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/knowledge/{name}/label", json={"label": text})
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"labelled {name}: {text or '(cleared)'}")


@app.command("delete")
def delete_scope(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    """Delete a whole scope (files + index + rows)."""
    if not yes and not typer.confirm(f"Really delete knowledge:{name} and everything in it?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/resources/knowledge/{name}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted: knowledge:{name}")


# --- entries ----------------------------------------------------------------


@app.command("remember")
def remember(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Scope name (e.g. 'global' or 'project-<ulid>')."),
    text: str = typer.Argument(...),
    entry_title: str | None = typer.Option(None, "--title", "--name"),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Write an entry into a scope (actor=user)."""
    body: dict[str, object] = {"text": text}
    if entry_title is not None:
        body["title"] = entry_title
    if description is not None:
        body["description"] = description
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            f"/knowledge/{name}/entries",
            json=body,
            headers={"X-Coffer-Actor": "user"},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"added entry id={r.json()['id']}")


@app.command("entries")
def list_entries(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    limit: int = typer.Option(50, "--limit"),
    offset: int = typer.Option(0, "--offset"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List the entries in a scope."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge/{name}/entries", params={"limit": limit, "offset": offset})
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title=f"Entries in {name} (total: {data['total']})")
    table.add_column("id")
    table.add_column("actor")
    table.add_column("title")
    table.add_column("text")
    for e in data["entries"]:
        table.add_row(e["id"][:8], e["actor"], e["title"][:40], e["text"][:60])
    _console.print(table)


@app.command("get")
def get_entry(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    entry_id: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show a single entry."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/knowledge/{name}/entries/{entry_id}")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"id:    {data['id']}")
    typer.echo(f"title: {data['title']}")
    typer.echo(f"path:  {data['path']}")
    typer.echo("")
    typer.echo(data["text"])


@app.command("edit-entry")
def edit_entry(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    entry_id: str = typer.Argument(...),
    text: str = typer.Argument(...),
) -> None:
    """Rewrite an entry's text."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(
            f"/knowledge/{name}/entries/{entry_id}",
            json={"text": text},
            headers={"X-Coffer-Actor": "user"},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"updated {entry_id}")


@app.command("forget")
def forget(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    entry_id: str = typer.Argument(...),
) -> None:
    """Delete a single entry."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(
            f"/knowledge/{name}/entries/{entry_id}",
            headers={"X-Coffer-Actor": "user"},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted {entry_id}")


@app.command("clear")
def clear(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    """Clear every entry in a scope (the scope itself is preserved)."""
    if not yes and not typer.confirm(f"Really clear all entries in {name}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.request(
            "DELETE",
            f"/knowledge/{name}/entries",
            headers={"X-Coffer-Actor": "user"},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"cleared {r.json()['cleared']} entry(ies)")


@app.command("recall")
def recall(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    query: str = typer.Argument(...),
    top_k: int = typer.Option(5, "--top-k"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Recall from a scope (one query → one answer)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/knowledge/{name}/recall", json={"query": query, "top_k": top_k})
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    for i, h in enumerate(data["hits"], start=1):
        typer.echo(f"{i}. (score={h['score']:.3f}) {h['text']}")


# --- the tidy pass ----------------------------------------------------------


@app.command("organize")
def organize(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Tidy a scope's notes now with Coffer's internal model: merge duplicates,
    split what has grown over-long. The same pass also runs on its own after a
    quiet spell and on a periodic sweep; this only says "now".

    Each replaced revision is copied into ``.history/`` first, so a rewrite
    is always recoverable."""
    c, _info = _cli_client.client_or_exit()
    with c:
        # An agentic loop over the whole lane, far beyond the client's default
        # 15s timeout.
        r = c.post(f"/knowledge/{name}/organize", timeout=600.0)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    status = data["status"]
    if status == "no_model":
        typer.echo("no internal model configured — nothing tidied", err=True)
        return
    if status == "empty":
        typer.echo("no notes — nothing to tidy")
        return
    typer.echo(
        f"tidied: {data['notes_written']} written, {data['notes_archived']} archived "
        f"(before: {data['notes_before']}, after: {data['notes_after']}, "
        f"model: {data.get('model')})"
    )
