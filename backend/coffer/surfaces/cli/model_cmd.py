"""`coffer model …` — model config CLI commands."""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Manage LLM model configurations")
_console = Console()


@app.command("add")
def add(
    name: str = typer.Option(..., "--name", help="Human-readable display name"),
    provider: str = typer.Option(..., "--provider", help="Provider: anthropic, openai, ollama"),
    model: str = typer.Option(..., "--model", help="Model identifier (e.g. claude-sonnet-4-6)"),
    credential_ref: str | None = typer.Option(None, "--credential-ref"),
    base_url: str | None = typer.Option(None, "--base-url"),
    default: bool = typer.Option(False, "--default", help="Set as the default model"),
) -> None:
    """Register a new model configuration."""
    body: dict[str, object] = {
        "display_name": name,
        "provider": provider,
        "model": model,
        "is_default": default,
    }
    if credential_ref is not None:
        body["credential_ref"] = credential_ref
    if base_url is not None:
        body["base_url"] = base_url

    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/models", json=body)
        if r.status_code in (400, 422):
            typer.echo(f"invalid model config: {r.text}", err=True)
            raise typer.Exit(6)
        r.raise_for_status()
    data = r.json()
    typer.echo(f"added model id={data['id']} ({data['display_name']})")


@app.command("list")
def list_models(
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List all configured models."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/models")
        r.raise_for_status()
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Models")
    table.add_column("id")
    table.add_column("display_name")
    table.add_column("provider")
    table.add_column("model")
    table.add_column("default")
    for m in data["models"]:
        table.add_row(
            m["id"][:8],
            m["display_name"],
            m["provider"],
            m["model"],
            "yes" if m["is_default"] else "",
        )
    _console.print(table)


@app.command("edit")
def edit(
    model_id: str = typer.Argument(..., help="Model ID to update"),
    name: str | None = typer.Option(None, "--name", help="New display name"),
    model: str | None = typer.Option(None, "--model", help="New model identifier"),
    credential_ref: str | None = typer.Option(None, "--credential-ref"),
    base_url: str | None = typer.Option(None, "--base-url"),
    default: bool | None = typer.Option(None, "--default/--no-default"),
) -> None:
    """Edit an existing model configuration."""
    patch: dict[str, object] = {}
    if name is not None:
        patch["display_name"] = name
    if model is not None:
        patch["model"] = model
    if credential_ref is not None:
        patch["credential_ref"] = credential_ref
    if base_url is not None:
        patch["base_url"] = base_url
    if default is not None:
        patch["is_default"] = default

    if not patch:
        typer.echo("nothing to update — specify at least one option", err=True)
        raise typer.Exit(6)

    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/models/{model_id}", json=patch)
        if r.status_code == 404:
            typer.echo(f"model {model_id!r} not found", err=True)
            raise typer.Exit(4)
        if r.status_code in (400, 422):
            typer.echo(f"invalid update: {r.text}", err=True)
            raise typer.Exit(6)
        r.raise_for_status()
    data = r.json()
    typer.echo(f"updated model id={data['id']} ({data['display_name']})")


@app.command("rm")
def rm(
    model_id: str = typer.Argument(..., help="Model ID to remove"),
) -> None:
    """Remove a model configuration."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/models/{model_id}")
        if r.status_code == 404:
            typer.echo(f"model {model_id!r} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    typer.echo(f"removed model {model_id}")
