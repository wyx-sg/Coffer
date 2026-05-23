"""`coffer memory …` — memory CLI commands."""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.domain.memory.config import DEFAULT_EMBEDDING_MODEL
from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Manage memory stores")
_console = Console()


@app.command("create")
def create(
    name: str = typer.Argument(...),
    description: str | None = typer.Option(None, "--description"),
    embedding_model: str = typer.Option(DEFAULT_EMBEDDING_MODEL, "--embedding-model"),
    llm_provider: str = typer.Option("none", "--llm-provider", help="One of: none, ollama, openai"),
    llm_model: str | None = typer.Option(None, "--llm-model"),
    llm_endpoint: str | None = typer.Option(None, "--llm-endpoint"),
    llm_credential_ref: str | None = typer.Option(None, "--llm-credential-ref"),
    max_memory_chars: int = typer.Option(8192, "--max-memory-chars"),
) -> None:
    """Create a memory store."""
    body = {
        "name": name,
        "description": description,
        "config": {
            "embedding_model": embedding_model,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_endpoint": llm_endpoint,
            "llm_credential_ref": llm_credential_ref,
            "max_memory_chars": max_memory_chars,
        },
    }
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/memory_stores", json=body)
        if r.status_code == 409:
            typer.echo(f"memory store {name!r} already exists", err=True)
            raise typer.Exit(5)
        if r.status_code in (400, 422):
            typer.echo(f"invalid config: {r.text}", err=True)
            raise typer.Exit(6)
        r.raise_for_status()
    typer.echo(f"created: memory:{name}")


@app.command("list")
def list_stores(
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/memory_stores")
        r.raise_for_status()
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Memory stores")
    table.add_column("name")
    table.add_column("description")
    table.add_column("llm_provider")
    for s in data["memory_stores"]:
        table.add_row(
            s["name"],
            s.get("description") or "",
            s["config"]["llm_provider"],
        )
    _console.print(table)


@app.command("describe")
def describe(
    name: str,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/memory_stores/{name}")
        if r.status_code == 404:
            typer.echo(f"memory:{name} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
        s = r.json()
        m = c.get(f"/memory_stores/{name}/metrics")
        m.raise_for_status()
        metrics = m.json()
    if output_json:
        typer.echo(_json.dumps({"memory_store": s, "metrics": metrics}, indent=2))
        return
    typer.echo(f"name:       {s['name']}")
    typer.echo(f"ref:        {s['ref']}")
    typer.echo(f"config:     {_json.dumps(s['config'], indent=2)}")
    typer.echo(f"memories:   {metrics['memory_count']}")
    typer.echo(f"disk_bytes: {metrics['disk_bytes']}")


@app.command("add")
def add(
    name: str = typer.Argument(...),
    text: str = typer.Argument(...),
) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            f"/memory_stores/{name}/memories",
            json={"text": text},
            headers={"X-Coffer-Actor": "user"},
        )
        if r.status_code == 404:
            typer.echo(f"memory:{name} not found", err=True)
            raise typer.Exit(4)
        if r.status_code == 503:
            typer.echo("LLM provider not configured; set --llm-provider on create", err=True)
            raise typer.Exit(7)
        if r.status_code == 400:
            typer.echo(f"rejected: {r.text}", err=True)
            raise typer.Exit(6)
        r.raise_for_status()
    out = r.json()
    typer.echo(f"added memory id={out['id']}")


@app.command("list-memories")
def list_memories(
    name: str = typer.Argument(...),
    limit: int = typer.Option(50, "--limit"),
    offset: int = typer.Option(0, "--offset"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(
            f"/memory_stores/{name}/memories",
            params={"limit": limit, "offset": offset},
        )
        if r.status_code == 404:
            typer.echo(f"memory:{name} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title=f"Memories in {name} (total: {data['total']})")
    table.add_column("id")
    table.add_column("actor")
    table.add_column("text")
    for m in data["memories"]:
        table.add_row(m["id"][:8], m["actor"], m["text"][:80])
    _console.print(table)


@app.command("edit")
def edit_memory(
    name: str = typer.Argument(...),
    memory_id: str = typer.Argument(...),
    text: str = typer.Argument(...),
) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(
            f"/memory_stores/{name}/memories/{memory_id}",
            json={"text": text},
        )
        if r.status_code == 404:
            typer.echo("memory not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    typer.echo(f"updated {memory_id}")


@app.command("delete")
def delete(
    name: str = typer.Argument(...),
    memory_id: str = typer.Argument(...),
) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/memory_stores/{name}/memories/{memory_id}")
        if r.status_code == 404:
            typer.echo("memory not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    typer.echo(f"deleted {memory_id}")


@app.command("clear")
def clear(
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    if not yes and not typer.confirm(f"Really clear all memories in {name}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/memory_stores/{name}/memories/clear")
        if r.status_code == 404:
            typer.echo(f"memory:{name} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    typer.echo("cleared")


@app.command("search")
def search(
    name: str = typer.Argument(...),
    query: str = typer.Argument(...),
    top_k: int = typer.Option(5, "--top-k"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(
            f"/memory_stores/{name}/search",
            json={"query": query, "top_k": top_k},
        )
        if r.status_code == 404:
            typer.echo(f"memory:{name} not found", err=True)
            raise typer.Exit(4)
        if r.status_code == 503:
            typer.echo("memory engine unavailable", err=True)
            raise typer.Exit(7)
        r.raise_for_status()
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    for i, h in enumerate(data["hits"], start=1):
        typer.echo(f"{i}. (score={h['score']:.3f}) {h['text']}")


@app.command("delete-store")
def delete_store(
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes"),
) -> None:
    if not yes and not typer.confirm(f"Really delete memory:{name} and all its memories?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/resources/memory/{name}")
        if r.status_code == 404:
            typer.echo(f"memory:{name} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    typer.echo(f"deleted: memory:{name}")
