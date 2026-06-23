"""`coffer provider …` — provider-profile CLI commands (spec 011)."""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Manage provider profiles and switch the active provider")
_console = Console()


@app.command("add")
def add(
    name: str = typer.Argument(..., help="Profile name"),
    protocol: str = typer.Option(
        ..., "--protocol", help="Protocol: anthropic | openai | ollama | unknown"
    ),
    base_url: str = typer.Option(..., "--base-url", help="Upstream endpoint base URL"),
    secret: str | None = typer.Option(None, "--secret", help="API key (stored encrypted)"),
    credential_ref: str | None = typer.Option(
        None, "--credential-ref", help="Reuse an existing credential ref instead of --secret"
    ),
    compatible: list[str] | None = typer.Option(  # noqa: B008 (typer pattern; list annotation)
        None,
        "--compatible",
        help="Agent this connection projects into (claude_code | codex); repeatable. "
        "Omit to use the wire default.",
    ),
) -> None:
    """Create an LLM connection. For anthropic/openai/unknown supply exactly one
    of --secret / --credential-ref; an ollama connection needs neither. Pass
    --compatible to route the connection to specific agents (e.g. an openai
    gateway to claude_code). The model is chosen at the point of use, not on the
    connection (spec 011 E3)."""
    body: dict[str, object] = {
        "name": name,
        "protocol": protocol,
        "base_url": base_url,
    }
    if secret is not None:
        body["secret_value"] = secret
    if credential_ref is not None:
        body["credential_ref"] = credential_ref
    if compatible:
        body["compatible_agents"] = compatible

    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/providers", json=body)
        if r.status_code in (400, 422):
            typer.echo(f"invalid provider config: {r.text}", err=True)
            raise typer.Exit(6)
        if r.status_code == 409:
            typer.echo(f"provider {name!r} already exists", err=True)
            raise typer.Exit(5)
        r.raise_for_status()
    data = r.json()
    typer.echo(f"added provider {data['name']} ({data['protocol']})")


@app.command("list")
def list_providers(output_json: bool = typer.Option(False, "--json")) -> None:
    """List all provider profiles."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/providers")
        r.raise_for_status()
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Providers")
    for col in ("name", "protocol", "base_url", "active", "internal"):
        table.add_column(col)
    for p in data["providers"]:
        table.add_row(
            p["name"],
            p["protocol"],
            p["base_url"],
            "yes" if p["is_active"] else "",
            "yes" if p.get("internal_default") else "",
        )
    _console.print(table)


@app.command("show")
def show(name: str = typer.Argument(..., help="Profile name")) -> None:
    """Show one provider profile."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/providers/{name}")
        if r.status_code == 404:
            typer.echo(f"provider {name!r} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    typer.echo(_json.dumps(r.json(), indent=2))


@app.command("edit")
def edit(
    name: str = typer.Argument(..., help="Profile name"),
    base_url: str | None = typer.Option(None, "--base-url"),
    secret: str | None = typer.Option(None, "--secret", help="Rotate the stored API key"),
) -> None:
    """Edit a provider profile (protocol / credential_ref are immutable)."""
    patch: dict[str, object] = {}
    if base_url is not None:
        patch["base_url"] = base_url
    if secret is not None:
        patch["secret_value"] = secret
    if not patch:
        typer.echo("nothing to update — specify at least one option", err=True)
        raise typer.Exit(6)

    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/providers/{name}", json=patch)
        if r.status_code == 404:
            typer.echo(f"provider {name!r} not found", err=True)
            raise typer.Exit(4)
        if r.status_code in (400, 422):
            typer.echo(f"invalid update: {r.text}", err=True)
            raise typer.Exit(6)
        r.raise_for_status()
    typer.echo(f"updated provider {name}")


@app.command("rm")
def rm(name: str = typer.Argument(..., help="Profile name")) -> None:
    """Remove a provider profile."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/providers/{name}")
        if r.status_code == 404:
            typer.echo(f"provider {name!r} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    typer.echo(f"removed provider {name}")


@app.command("switch")
def switch(name: str = typer.Argument(..., help="Profile to activate")) -> None:
    """Switch: make this profile active for its wire and write native config."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/providers/{name}/activate")
        if r.status_code == 404:
            typer.echo(f"provider {name!r} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    data = r.json()
    projected = ", ".join(data["projected"]) or "(no matching agent)"
    typer.echo(f"switched to {data['activated']} [{data['protocol']}] → {projected}")


@app.command("internal-default")
def internal_default(name: str = typer.Argument(..., help="Connection to use internally")) -> None:
    """Make this connection Coffer's internal-engine default (≤1 globally)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/providers/{name}/internal-default")
        if r.status_code == 404:
            typer.echo(f"provider {name!r} not found", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    data = r.json()
    typer.echo(f"internal engine now uses {data['name']} [{data['protocol']}]")


@app.command("key")
def key(
    connection: str | None = typer.Option(
        None, "--connection", help="Print this specific connection's key (the projected helper)"
    ),
    wire: str | None = typer.Option(
        None, "--wire", help="Back-compat: print the key active for a wire (anthropic | openai)"
    ),
) -> None:
    """Print a provider's API key for Claude Code's apiKeyHelper. Prefer
    --connection <name> (what Coffer projects); --wire is the legacy form that
    resolves whichever connection is active for that wire's agent."""
    if connection:
        path, missing = f"/providers/{connection}/key", f"no key for connection {connection!r}"
    elif wire:
        path, missing = f"/providers/active-key/{wire}", f"no active provider for wire {wire!r}"
    else:
        typer.echo("specify --connection <name> or --wire <wire>", err=True)
        raise typer.Exit(6)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(path)
        if r.status_code == 404:
            typer.echo(missing, err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    # Raw value only — apiKeyHelper consumes stdout as the token.
    typer.echo(r.json()["value"])
