"""`coffer mcp ...` — MCP-kind-specific CLI commands.

Each command is a thin HTTP client of the daemon API. The split between
this file and `resource_cmd.py` (kind-agnostic) is that `mcp.py`
operations use MCP-specific routes (capabilities, refresh, test,
invocations) plus the convenience `add` flag for transport parsing.

Capability curation sub-commands (tool/resource/prompt) live in
`_mcp_caps.py` and are wired in here to keep this file under the
project's 400-line limit.
"""

from __future__ import annotations

import json as _json
import shlex
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._mcp_caps import prompt_app, resource_app, tool_app

app = typer.Typer(help="Manage MCP servers and their capabilities")
_console = Console()

app.add_typer(tool_app, name="tool")
app.add_typer(resource_app, name="resource")
app.add_typer(prompt_app, name="prompt")


def _parse_credentials(creds: list[str]) -> dict[str, str]:
    """Parse `--credential KEY=VALUE` repeatable into a dict."""
    out: dict[str, str] = {}
    for c in creds:
        if "=" not in c:
            raise typer.BadParameter(f"--credential must be KEY=CREDENTIAL_REF, got {c!r}")
        k, v = c.split("=", 1)
        out[k] = v
    return out


@app.command("add")
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Server name (kind-internally unique)"),
    stdio: str | None = typer.Option(None, "--stdio", help="`command [args...]`"),
    http: str | None = typer.Option(None, "--http", help="HTTP MCP server URL"),
    credential: list[str] = typer.Option(  # noqa: B008
        [], "--credential", help="ENV_OR_HEADER=CREDENTIAL_REF (repeatable)"
    ),
    no_auto_enable: bool = typer.Option(
        False, "--no-auto-enable", help="Default new capabilities to disabled"
    ),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Register a new MCP server (stdio OR http; pick one)."""
    verbose = (ctx.obj or {}).get("verbose", False)
    if (stdio is None) == (http is None):
        typer.echo("specify exactly one of --stdio or --http", err=True)
        raise typer.Exit(2)

    if stdio is not None:
        parts = shlex.split(stdio)
        if not parts:
            typer.echo("--stdio command cannot be empty", err=True)
            raise typer.Exit(2)
        transport: dict[str, Any] = {
            "type": "stdio",
            "command": parts[0],
            "args": parts[1:],
            "credential_refs": _parse_credentials(credential),
        }
    else:
        transport = {
            "type": "http",
            "url": http,
            "credential_refs": _parse_credentials(credential),
        }

    config = {
        "transport": transport,
        "auto_enable_new_capabilities": not no_auto_enable,
    }
    payload = {
        "kind": "mcp_server",
        "name": name,
        "description": description,
        "config": config,
    }

    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/resources", json=payload)
        if r.status_code == 409:
            typer.echo(f"server {name!r} already exists", err=True)
            raise typer.Exit(5)
        if r.status_code == 400:
            typer.echo(r.json()["error"]["message"], err=True)
            raise typer.Exit(6)
        if r.status_code == 422:
            typer.echo(f"config invalid: {r.json()['error']}", err=True)
            raise typer.Exit(6)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"registered: mcp_server:{name}")


@app.command("remove")
def remove(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Delete an MCP server registration."""
    verbose = (ctx.obj or {}).get("verbose", False)
    if not force and not typer.confirm(f"Really delete mcp_server:{name}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/resources/mcp_server/{name}")
        if r.status_code == 404:
            typer.echo(f"mcp_server:{name} not found", err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed: mcp_server:{name}")


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List all registered MCP servers."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/resources", params={"kind": "mcp_server"})
        _cli_client.check(r, verbose=verbose)
    data = r.json()["resources"]
    if output_json:
        typer.echo(_json.dumps({"resources": data}, indent=2))
        return
    table = Table(title="MCP Servers")
    table.add_column("Name")
    table.add_column("Transport")
    table.add_column("Enabled")
    table.add_column("Description")
    for item in data:
        transport_type = (item.get("config") or {}).get("transport", {}).get("type", "?")
        table.add_row(
            item["name"],
            transport_type,
            str(item["enabled"]),
            item.get("description") or "",
        )
    _console.print(table)


@app.command("show")
def show(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show details of a single MCP server."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/resources/mcp_server/{name}")
        if r.status_code == 404:
            typer.echo(f"mcp_server:{name} not found", err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"ref:      {data['ref']}")
    typer.echo(f"enabled:  {data['enabled']}")
    typer.echo(f"config:   {_json.dumps(data['config'], indent=2)}")


@app.command("refresh")
def refresh(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Invalidate + re-query capabilities for an MCP server."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/resources/mcp_server/{name}/refresh")
        if r.status_code == 404:
            typer.echo(f"mcp_server:{name} not found", err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"refreshed: mcp_server:{name}")


@app.command("test")
def test_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Health-test the upstream MCP server."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/resources/mcp_server/{name}/test")
        if r.status_code == 404:
            typer.echo(f"mcp_server:{name} not found", err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if data["ok"]:
        typer.echo(f"OK  ({data['latency_ms']} ms)")
    else:
        typer.echo(f"FAIL ({data['latency_ms']} ms): {data.get('error_message')}", err=True)
        raise typer.Exit(7)


@app.command("invocations")
def invocations(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    limit: int = typer.Option(20, "--limit", min=1, max=500),
    status_filter: str | None = typer.Option(None, "--status"),
    since: str | None = typer.Option(None, "--since", help="ISO 8601 timestamp"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Query the invocation log for an MCP server."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    params: dict[str, Any] = {"limit": limit}
    if status_filter is not None:
        params["status"] = status_filter
    if since is not None:
        params["since"] = since
    with c:
        r = c.get(f"/resources/mcp_server/{name}/invocations", params=params)
        if r.status_code == 404:
            typer.echo(f"mcp_server:{name} not found", err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    data = r.json()["invocations"]
    if output_json:
        typer.echo(_json.dumps({"invocations": data}, indent=2))
        return
    table = Table(title=f"{name} invocations (last {limit})")
    table.add_column("Time")
    table.add_column("Type")
    table.add_column("Key")
    table.add_column("Duration (ms)")
    table.add_column("Status")
    for inv in data:
        table.add_row(
            inv["timestamp"],
            inv["capability_type"],
            inv["capability_key"],
            str(inv["duration_ms"]),
            inv["status"],
        )
    _console.print(table)
