"""`coffer memory …` — memory CLI commands (spec 007 redesign).

Thin HTTP shells over the daemon. Memory stores are auto-provisioned per scope
(``global`` / ``project-<ulid>``); the user never "creates" one. NO LLM-provider
flags and no 503 path — writes hand Coffer a clean fact and ``recall`` degrades
vector→keyword (flagged) instead of erroring.
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Manage memory stores")
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


@app.command("list")
def list_stores(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List memory stores (one per scope)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/memory_stores")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Memory stores")
    table.add_column("name")
    table.add_column("scope")
    table.add_column("description")
    table.add_column("modes")
    for s in data["memory_stores"]:
        table.add_row(
            s["name"],
            s["scope"],
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
    """Show one memory store's config + metrics."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/memory_stores/{name}")
        _cli_client.check(r, verbose=_verbose(ctx))
        s = r.json()
        m = c.get(f"/memory_stores/{name}/metrics")
        _cli_client.check(m, verbose=_verbose(ctx))
        metrics = m.json()
    if output_json:
        typer.echo(_json.dumps({"memory_store": s, "metrics": metrics}, indent=2))
        return
    typer.echo(f"name:       {s['name']}")
    typer.echo(f"scope:      {s['scope']}")
    typer.echo(f"ref:        {s['ref']}")
    typer.echo(f"config:     {_json.dumps(s['config'], indent=2)}")
    typer.echo(f"facts:      {metrics['fact_count']}")
    typer.echo(f"disk_bytes: {metrics['disk_bytes']}")


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Store name (e.g. 'global' or 'project-<ulid>')."),
    text: str = typer.Argument(...),
    fact_name: str | None = typer.Option(None, "--name"),
    description: str | None = typer.Option(None, "--description"),
    fact_type: str | None = typer.Option(None, "--type"),
) -> None:
    """Add a fact (actor=user)."""
    body: dict[str, object] = {"text": text}
    if fact_name is not None:
        body["name"] = fact_name
    if description is not None:
        body["description"] = description
    if fact_type is not None:
        body["type"] = fact_type
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            f"/memory_stores/{name}/facts",
            json=body,
            headers={"X-Coffer-Actor": "user"},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    out = r.json()
    typer.echo(f"added fact id={out['id']}")


@app.command("facts")
def list_facts(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    limit: int = typer.Option(50, "--limit"),
    offset: int = typer.Option(0, "--offset"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List facts in a store."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(
            f"/memory_stores/{name}/facts",
            params={"limit": limit, "offset": offset},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title=f"Facts in {name} (total: {data['total']})")
    table.add_column("id")
    table.add_column("actor")
    table.add_column("name")
    table.add_column("text")
    for f in data["facts"]:
        table.add_row(f["id"][:8], f["actor"], f["name"][:40], f["text"][:60])
    _console.print(table)


@app.command("get")
def get_fact(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    fact_id: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Get a single fact."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/memory_stores/{name}/facts/{fact_id}")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"id:   {data['id']}")
    typer.echo(f"name: {data['name']}")
    typer.echo(f"path: {data['path']}")
    typer.echo("")
    typer.echo(data["text"])


@app.command("edit")
def edit_fact(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    fact_id: str = typer.Argument(...),
    text: str = typer.Argument(...),
) -> None:
    """Edit a fact's text."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(
            f"/memory_stores/{name}/facts/{fact_id}",
            json={"text": text},
            headers={"X-Coffer-Actor": "user"},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"updated {fact_id}")


@app.command("delete")
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    fact_id: str = typer.Argument(...),
) -> None:
    """Delete (forget) a single fact."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(
            f"/memory_stores/{name}/facts/{fact_id}",
            headers={"X-Coffer-Actor": "user"},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"deleted {fact_id}")


@app.command("clear")
def clear(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    """Clear every fact in a scope (the store is preserved)."""
    if not yes and not typer.confirm(f"Really clear all facts in {name}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.request(
            "DELETE",
            f"/memory_stores/{name}/facts",
            headers={"X-Coffer-Actor": "user"},
        )
        _cli_client.check(r, verbose=_verbose(ctx))
    out = r.json()
    typer.echo(f"cleared {out['cleared']} fact(s)")


@app.command("configure")
def configure(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    provider: str | None = typer.Option(None, "--provider"),
    model: str | None = typer.Option(None, "--model"),
    dimensions: int | None = typer.Option(None, "--dimensions"),
    base_url: str | None = typer.Option(None, "--base-url"),
    credential_ref: str | None = typer.Option(
        None, "--credential-ref", help="Stored credential ref (never a raw key)."
    ),
    enable_vector: bool = typer.Option(
        False, "--enable-vector", help="Add 'vector' to retrieval_modes."
    ),
    default_mode: str | None = typer.Option(None, "--default-mode"),
    max_fact_chars: int | None = typer.Option(None, "--max-fact-chars"),
) -> None:
    """Update a store's config (embedding / modes / limits). PATCHes the store;
    enabling vector re-embeds existing facts."""
    patch: dict[str, object] = {}
    if provider is not None:
        patch["embedding_provider"] = provider
    if model is not None:
        patch["embedding_model"] = model
    if dimensions is not None:
        patch["embedding_dimensions"] = dimensions
    if base_url is not None:
        patch["embedding_base_url"] = base_url
    if credential_ref is not None:
        patch["embedding_credential_ref"] = credential_ref
    if default_mode is not None:
        patch["default_mode"] = default_mode
    if max_fact_chars is not None:
        patch["max_fact_chars"] = max_fact_chars
    c, _info = _cli_client.client_or_exit()
    with c:
        if enable_vector:
            current = c.get(f"/memory_stores/{name}")
            _cli_client.check(current, verbose=_verbose(ctx))
            modes = list(current.json()["config"]["retrieval_modes"])
            if "vector" not in modes:
                modes.append("vector")
            patch["retrieval_modes"] = modes
        if not patch:
            typer.echo("nothing to configure (no options given)", err=True)
            raise typer.Exit(1)
        r = c.patch(f"/memory_stores/{name}", json=patch)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"configured {name}")


@app.command("recall")
def recall(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    query: str = typer.Argument(...),
    top_k: int = typer.Option(5, "--top-k"),
    mode: str | None = typer.Option(None, "--mode", help="grep / keyword / vector."),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Recall facts from a store."""
    payload: dict[str, object] = {"query": query, "top_k": top_k}
    if mode is not None:
        payload["mode"] = mode
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/memory_stores/{name}/recall", json=payload)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    if data.get("fallback"):
        typer.echo("(vector unavailable — fell back to keyword)", err=True)
    for i, h in enumerate(data["hits"], start=1):
        typer.echo(f"{i}. (score={h['score']:.3f}) {h['text']}")


# --- projection -------------------------------------------------------------


@app.command("bind")
def bind(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Memory store name."),
    agent_ref: str = typer.Argument(..., help="Agent resource name to project into."),
    project_root: str | None = typer.Option(
        None, "--project-root", help="Absolute project root (SYMLINK of a project store)."
    ),
) -> None:
    """Establish a native memory projection into an agent."""
    body: dict[str, object] = {"agent_ref": agent_ref}
    if project_root is not None:
        body["project_root"] = project_root
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/memory_stores/{name}/projections", json=body)
        _cli_client.check(r, verbose=_verbose(ctx))
    out = r.json()
    typer.echo(
        f"projected {name} → {agent_ref} (mode={out['projection_mode']}, "
        f"target={out['target_path']})"
    )


@app.command("unbind")
def unbind(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    agent_ref: str = typer.Argument(...),
) -> None:
    """Remove a native memory projection."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/memory_stores/{name}/projections/{agent_ref}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"removed projection {name} → {agent_ref}")


@app.command("projections")
def list_projections(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List an agent-store projections for a memory store."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/memory_stores/{name}/projections")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title=f"Projections of {name}")
    table.add_column("agent_ref")
    table.add_column("mode")
    table.add_column("target_path")
    for p in data["projections"]:
        table.add_row(p["agent_ref"], p["projection_mode"], p["target_path"])
    _console.print(table)
