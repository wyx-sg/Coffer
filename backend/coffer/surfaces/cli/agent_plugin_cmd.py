"""``coffer agent plugin list|show|enable|disable|rm`` — an agent's installed plugins.

Part of spec agent-registry "Expose every agent operation through REST, CLI and
the Agents page"; ``rm`` is the uninstall of "Uninstall a plugin by the type's
own strategy". Kept out of ``agent_cmd.py`` for the 400-line backend file cap;
``agent_cmd`` calls :func:`attach`.

The agent is taken by NAME and resolved to a uid through ``_resolve`` (ADR
identity-is-the-uid-inside-the-file). The ``plugin_id`` beside it stays as it
is: it names something inside the agent's own config, which Coffer did not mint.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import verbose_of
from coffer.surfaces.cli._resolve import resolve_ref

plugin_app = typer.Typer(help="View and manage an agent's installed plugins")
_console = Console()

_AGENT = typer.Argument(..., metavar="NAME", help="Agent name or uid")
_PLUGIN = typer.Argument(..., help="Plugin id (name@marketplace)")


def _not_found_exit(r: Any) -> None:
    if r.status_code == 404:
        typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
        raise typer.Exit(4)


@plugin_app.command("list")
def plugin_list(
    ctx: typer.Context,
    name: str = _AGENT,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List the agent's installed plugins and known marketplaces."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_ref(c, "agent", name, verbose=verbose)["uid"]
        r = c.get(f"/agents/{uid}/plugins")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    for p in data["parse_errors"]:
        typer.echo(f"warning: cannot parse {p['source']} ({p['path']}): {p['error']}", err=True)
    table = Table(title=f"Plugins — {name}")
    for col in ("ID", "Name", "Marketplace", "Enabled", "Cache"):
        table.add_column(col)
    for it in data["items"]:
        table.add_row(
            it["id"],
            it["name"],
            it["marketplace"],
            "✓" if it["enabled"] else "✗",
            "✓" if it["cache_present"] else "",
        )
    _console.print(table)
    for m in data["marketplaces"]:
        src = " ".join(s for s in (m["source_type"], m["source"]) if s)
        typer.echo(f"marketplace: {m['name']}" + (f" ({src})" if src else ""))


@plugin_app.command("show")
def plugin_show(
    ctx: typer.Context,
    name: str = _AGENT,
    plugin_id: str = _PLUGIN,
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Show one plugin: its metadata, install dir and everything it contributes."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_ref(c, "agent", name, verbose=verbose)["uid"]
        r = c.get(f"/agents/{uid}/plugins/{plugin_id}")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    p = data["plugin"]
    src = data["marketplace_source"]
    typer.echo(f"{p['id']}  {'enabled' if p['enabled'] else 'disabled'}")
    for label, value in (
        ("version", p["version"]),
        ("author", p["author"]),
        ("description", p["description"]),
        ("homepage", p["homepage"]),
        ("marketplace", p["marketplace"] + (f" ({src})" if src else "")),
        ("installed at", data["install_path"]),
    ):
        if value:
            typer.echo(f"{label}: {value}")
    for key in ("skills", "commands", "agents"):
        for comp in data[key]:
            desc = f" — {comp['description']}" if comp["description"] else ""
            typer.echo(f"{key[:-1]}: {comp['name']}{desc}")
    for event in data["hooks"]:
        typer.echo(f"hook: {event}")
    for server in data["mcp_servers"]:
        typer.echo(f"mcp server: {server}")


def _plugin_set_enabled(ctx: typer.Context, name: str, plugin_id: str, enabled: bool) -> None:
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_ref(c, "agent", name, verbose=verbose)["uid"]
        r = c.patch(f"/agents/{uid}/plugins/{plugin_id}", json={"enabled": enabled})
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"{'enabled' if enabled else 'disabled'}: plugin {plugin_id} (agent {name})")


@plugin_app.command("enable")
def plugin_enable(ctx: typer.Context, name: str = _AGENT, plugin_id: str = _PLUGIN) -> None:
    """Enable a plugin in the agent's config."""
    _plugin_set_enabled(ctx, name, plugin_id, True)


@plugin_app.command("disable")
def plugin_disable(ctx: typer.Context, name: str = _AGENT, plugin_id: str = _PLUGIN) -> None:
    """Disable a plugin in the agent's config."""
    _plugin_set_enabled(ctx, name, plugin_id, False)


@plugin_app.command("rm")
def plugin_rm(
    ctx: typer.Context,
    name: str = _AGENT,
    plugin_id: str = _PLUGIN,
    yes: bool = typer.Option(False, "--yes", "-y", "--force", "-f", help="Do not ask"),
) -> None:
    """Uninstall a plugin (Codex edits its config; Claude Code shells out to its own CLI)."""
    if not yes and not typer.confirm(f"Really uninstall plugin {plugin_id!r} from agent {name}?"):
        raise typer.Exit(1)
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_ref(c, "agent", name, verbose=verbose)["uid"]
        r = c.delete(f"/agents/{uid}/plugins/{plugin_id}")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed: plugin {plugin_id} from agent {name}")


def attach(agent_app: typer.Typer) -> None:
    """Register ``coffer agent plugin`` on agent_cmd's typer."""
    agent_app.add_typer(plugin_app, name="plugin")
