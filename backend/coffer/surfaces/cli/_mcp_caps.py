"""`coffer mcp tool|resource|prompt ...` — capability curation sub-commands.

Responsibility: enable/disable/list individual tool, resource, and prompt
capabilities exposed by a registered MCP server.  Split from ``mcp.py`` to
satisfy the project 400-line backend Python file-size limit.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

_console = Console()

tool_app = typer.Typer(help="Manage tool preferences")
resource_app = typer.Typer(help="Manage resource preferences")
prompt_app = typer.Typer(help="Manage prompt preferences")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _capabilities_for(name: str, *, verbose: bool = False) -> dict[str, list[dict[str, Any]]]:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/resources/mcp_server/{name}/capabilities")
        if r.status_code == 404:
            typer.echo(f"mcp_server:{name} not found", err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    return r.json()  # type: ignore[no-any-return]


def _render_capability_table(title: str, rows: list[dict[str, Any]], key_field: str) -> None:
    table = Table(title=title)
    table.add_column("Key")
    table.add_column("Prefixed")
    table.add_column("Enabled")
    table.add_column("Description")
    for r in rows:
        table.add_row(
            r[key_field],
            r.get("prefixed_name") or r.get("prefixed_uri") or "",
            str(r["enabled"]),
            (r.get("description") or "")[:60],
        )
    _console.print(table)


def _toggle(name: str, type_: str, key: str, *, enable: bool, verbose: bool = False) -> None:
    c, _info = _cli_client.client_or_exit()
    op = "enable" if enable else "disable"
    with c:
        # CODE-038: send the capability key in the request body, not the URL
        # path. Resource keys are URIs containing '/' (e.g. file:///etc/hosts);
        # embedding them in the path never matches the single-segment legacy
        # route and always 404s. The body route handles arbitrary keys.
        r = c.post(
            f"/resources/mcp_server/{name}/capabilities/{type_}/{op}",
            json={"capability_key": key},
        )
        if r.status_code == 404:
            typer.echo(f"capability not found: {type_}:{key} on {name}", err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"{op}d: {name} {type_}:{key}")


# ---------------------------------------------------------------------------
# tool sub-commands
# ---------------------------------------------------------------------------


@tool_app.command("list")
def tool_list(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List tools for an MCP server."""
    verbose = (ctx.obj or {}).get("verbose", False)
    caps = _capabilities_for(name, verbose=verbose)
    if output_json:
        typer.echo(_json.dumps({"tools": caps["tools"]}, indent=2))
    else:
        _render_capability_table(f"{name} tools", caps["tools"], "original_name")


@tool_app.command("enable")
def tool_enable(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    tool_key: str = typer.Argument(...),
) -> None:
    """Enable a tool capability."""
    verbose = (ctx.obj or {}).get("verbose", False)
    _toggle(name, "tool", tool_key, enable=True, verbose=verbose)


@tool_app.command("disable")
def tool_disable(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    tool_key: str = typer.Argument(...),
) -> None:
    """Disable a tool capability."""
    verbose = (ctx.obj or {}).get("verbose", False)
    _toggle(name, "tool", tool_key, enable=False, verbose=verbose)


# ---------------------------------------------------------------------------
# resource sub-commands
# ---------------------------------------------------------------------------


@resource_app.command("list")
def resource_list(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List resources for an MCP server."""
    verbose = (ctx.obj or {}).get("verbose", False)
    caps = _capabilities_for(name, verbose=verbose)
    if output_json:
        typer.echo(_json.dumps({"resources": caps["resources"]}, indent=2))
    else:
        _render_capability_table(f"{name} resources", caps["resources"], "original_uri")


@resource_app.command("enable")
def resource_enable(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    uri: str = typer.Argument(...),
) -> None:
    """Enable a resource capability."""
    verbose = (ctx.obj or {}).get("verbose", False)
    _toggle(name, "resource", uri, enable=True, verbose=verbose)


@resource_app.command("disable")
def resource_disable(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    uri: str = typer.Argument(...),
) -> None:
    """Disable a resource capability."""
    verbose = (ctx.obj or {}).get("verbose", False)
    _toggle(name, "resource", uri, enable=False, verbose=verbose)


# ---------------------------------------------------------------------------
# prompt sub-commands
# ---------------------------------------------------------------------------


@prompt_app.command("list")
def prompt_list(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """List prompts for an MCP server."""
    verbose = (ctx.obj or {}).get("verbose", False)
    caps = _capabilities_for(name, verbose=verbose)
    if output_json:
        typer.echo(_json.dumps({"prompts": caps["prompts"]}, indent=2))
    else:
        _render_capability_table(f"{name} prompts", caps["prompts"], "original_name")


@prompt_app.command("enable")
def prompt_enable(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    key: str = typer.Argument(...),
) -> None:
    """Enable a prompt capability."""
    verbose = (ctx.obj or {}).get("verbose", False)
    _toggle(name, "prompt", key, enable=True, verbose=verbose)


@prompt_app.command("disable")
def prompt_disable(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    key: str = typer.Argument(...),
) -> None:
    """Disable a prompt capability."""
    verbose = (ctx.obj or {}).get("verbose", False)
    _toggle(name, "prompt", key, enable=False, verbose=verbose)
