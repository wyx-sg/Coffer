"""coffer agent workspace subcommands (spec 004/005 amendment).

MCP entries, plugins, directory config-file children, and the follow-policy
verb. Kept out of ``agent_cmd.py`` to respect the 400-line backend file cap;
``agent_cmd`` calls :func:`attach` to register everything on its existing
typers, so the user-facing tree stays ``coffer agent mcp/config/plugin/...``.
"""

from __future__ import annotations

import json as _json
import sys
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

plugin_app = typer.Typer(help="View and manage an agent's installed plugins")
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _not_found_exit(r: Any) -> None:
    if r.status_code == 404:
        typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
        raise typer.Exit(4)


def _warn_parse_errors(parse_errors: list[dict[str, Any]]) -> None:
    for p in parse_errors:
        typer.echo(f"warning: cannot parse {p['source']} ({p['path']}): {p['error']}", err=True)


def _tristate(value: bool | None) -> str:
    if value is None:
        return "—"
    return "✓" if value else "✗"


# --- coffer agent mcp entries / remove-entry / toggle-entry / adopt ----------


def mcp_entries(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List the MCP server entries in the agent's own config files."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}/mcp-entries")
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    _warn_parse_errors(data["parse_errors"])
    table = Table(title=f"MCP entries — {name}")
    for col in ("Name", "Source", "Transport", "Enabled", "Coffer", "Matches"):
        table.add_column(col)
    for it in data["items"]:
        table.add_row(
            it["name"],
            it["source"],
            it["transport"],
            _tristate(it["enabled"]),
            "✓" if it["is_coffer"] else "",
            it["matches_resource"] or "",
        )
    _console.print(table)


def mcp_remove_entry(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    entry: str = typer.Argument(..., help="MCP entry name"),
    source: str | None = typer.Option(
        None, "--source", help="Config-file key when the entry exists in several files."
    ),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Remove one MCP entry from the agent's config file (a .bak is kept)."""
    if not force and not typer.confirm(f"Really remove MCP entry {entry!r} from agent:{name}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        params = {"source": source} if source is not None else None
        r = c.delete(f"/agents/{name}/mcp-entries/{entry}", params=params)
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"removed: mcp entry {entry} from agent:{name}")


def mcp_toggle_entry(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    entry: str = typer.Argument(..., help="MCP entry name"),
    enabled: bool = typer.Option(..., "--enabled/--disabled", help="Target state."),
) -> None:
    """Enable or disable one MCP entry (Codex only)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/agents/{name}/mcp-entries/{entry}", json={"enabled": enabled})
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"{'enabled' if enabled else 'disabled'}: mcp entry {entry} (agent:{name})")


def mcp_adopt(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    entry: str = typer.Argument(..., help="MCP entry name"),
    source: str | None = typer.Option(
        None, "--source", help="Config-file key when the entry exists in several files."
    ),
    new_name: str | None = typer.Option(
        None, "--name", help="Register the resource under this name instead."
    ),
    secret: list[str] = typer.Option(  # noqa: B008 — typer option declaration
        [],
        "--secret",
        help="KEY=CREDENTIAL_REF mapping for a secret-like env/header key (repeatable).",
    ),
) -> None:
    """Adopt an MCP entry into Coffer as a managed mcp_server resource."""
    secrets: dict[str, str] = {}
    for item in secret:
        key, sep, ref = item.partition("=")
        if not sep or not key or not ref:
            typer.echo(f"--secret must be KEY=CREDENTIAL_REF, got {item!r}", err=True)
            raise typer.Exit(2)
        secrets[key] = ref
    body: dict[str, Any] = {}
    if source is not None:
        body["source"] = source
    if new_name is not None:
        body["new_name"] = new_name
    if secrets:
        body["secrets"] = secrets
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/agents/{name}/mcp-entries/{entry}/adopt", json=body)
        _not_found_exit(r)
        envelope = r.json().get("error", {}) if r.status_code >= 400 else {}
        if r.status_code == 422 and envelope.get("code") == "ADOPT_SECRET_UNRESOLVED":
            typer.echo(envelope.get("message", "secret keys unresolved"), err=True)
            typer.echo("hint: pass --secret KEY=CREDENTIAL_REF for each key listed above", err=True)
            raise typer.Exit(6)
        if r.status_code == 409:
            typer.echo(envelope.get("message", "name conflict"), err=True)
            suggested = (envelope.get("details") or {}).get("suggested_name")
            if suggested:
                typer.echo(f"hint: retry with --name {suggested}", err=True)
            raise typer.Exit(5)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    typer.echo(f"adopted: {data['kind']}:{data['name']}")


# --- coffer agent plugin ... --------------------------------------------------


@plugin_app.command("list")
def plugin_list(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List the agent's installed plugins and known marketplaces."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}/plugins")
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    _warn_parse_errors(data["parse_errors"])
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


def _plugin_set_enabled(ctx: typer.Context, name: str, plugin_id: str, enabled: bool) -> None:
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/agents/{name}/plugins/{plugin_id}", json={"enabled": enabled})
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"{'enabled' if enabled else 'disabled'}: plugin {plugin_id} (agent:{name})")


@plugin_app.command("enable")
def plugin_enable(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    plugin_id: str = typer.Argument(..., help="Plugin id (name@marketplace)"),
) -> None:
    """Enable a plugin in the agent's config."""
    _plugin_set_enabled(ctx, name, plugin_id, True)


@plugin_app.command("disable")
def plugin_disable(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    plugin_id: str = typer.Argument(..., help="Plugin id (name@marketplace)"),
) -> None:
    """Disable a plugin in the agent's config."""
    _plugin_set_enabled(ctx, name, plugin_id, False)


@plugin_app.command("uninstall")
def plugin_uninstall(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    plugin_id: str = typer.Argument(..., help="Plugin id (name@marketplace)"),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Uninstall a plugin (Codex only — removes the entry and its cache dir)."""
    if not force and not typer.confirm(f"Really uninstall plugin {plugin_id!r} from agent:{name}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/agents/{name}/plugins/{plugin_id}")
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"uninstalled: plugin {plugin_id} from agent:{name}")


# --- coffer agent config files / write / rm -----------------------------------


def config_files(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    key: str = typer.Argument(..., help="Directory-type config key (e.g. subagents)"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List the child files of a directory-type config entry."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}/config-files")
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    entry = next((i for i in r.json()["items"] if i["key"] == key), None)
    if entry is None:
        typer.echo(f"unknown config key: {key}", err=True)
        raise typer.Exit(4)
    if entry["kind"] != "directory":
        typer.echo(f"config key {key!r} is not a directory entry", err=True)
        raise typer.Exit(6)
    files = entry["files"] or []
    if output_json:
        typer.echo(_json.dumps(files, indent=2))
        return
    table = Table(title=f"{key} files — {name}")
    for col in ("Relpath", "Size", "Modified"):
        table.add_column(col)
    for f in files:
        table.add_row(f["relpath"], str(f["size"]), f["modified_at"])
    _console.print(table)


def config_write(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    key: str = typer.Argument(..., help="Directory-type config key (e.g. subagents)"),
    relpath: str = typer.Argument(..., help="Child file path (e.g. reviewer.md)"),
    from_file: str | None = typer.Option(
        None, "--from-file", help="Read the content from PATH instead of stdin."
    ),
) -> None:
    """Write a child file of a directory-type config entry (content from --from-file or stdin)."""
    if from_file is not None:
        import pathlib

        try:
            content = pathlib.Path(from_file).read_text(encoding="utf-8")
        except OSError as e:
            typer.echo(f"cannot read {from_file}: {e}", err=True)
            raise typer.Exit(1) from e
    else:
        content = sys.stdin.read()
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put(f"/agents/{name}/config-files/{key}/files/{relpath}", json={"content": content})
        _not_found_exit(r)
        if r.status_code == 422:
            typer.echo(r.json().get("error", {}).get("message", "invalid content"), err=True)
            raise typer.Exit(2)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"saved: {key}/{relpath}")


def config_rm(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    key: str = typer.Argument(..., help="Directory-type config key (e.g. subagents)"),
    relpath: str = typer.Argument(..., help="Child file path (e.g. reviewer.md)"),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Delete a child file of a directory-type config entry."""
    if not force and not typer.confirm(f"Really delete {key}/{relpath} of agent:{name}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/agents/{name}/config-files/{key}/files/{relpath}")
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"removed: {key}/{relpath}")


# --- coffer agent follow -------------------------------------------------------


def follow(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    on: bool = typer.Option(
        ..., "--on/--off", help="Follow (or stop following) the master skill library."
    ),
    exclude: list[str] = typer.Option(  # noqa: B008 — typer option declaration
        [],
        "--exclude",
        help="Skill name to exclude (repeatable; replaces the exclusion list).",
    ),
) -> None:
    """Set the agent's follow-master-library policy (FR-025)."""
    body: dict[str, Any] = {"follow_all_skills": on}
    if exclude:
        body["skill_exclusions"] = list(exclude)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/agents/{name}", json=body)
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"updated: agent:{name} follow_all_skills={'on' if on else 'off'}")


def attach(agent_app: typer.Typer, *, config_app: typer.Typer, mcp_app: typer.Typer) -> None:
    """Register the workspace commands on agent_cmd's existing typers."""
    mcp_app.command("entries")(mcp_entries)
    mcp_app.command("remove-entry")(mcp_remove_entry)
    mcp_app.command("toggle-entry")(mcp_toggle_entry)
    mcp_app.command("adopt")(mcp_adopt)
    config_app.command("files")(config_files)
    config_app.command("write")(config_write)
    config_app.command("rm")(config_rm)
    agent_app.add_typer(plugin_app, name="plugin")
    agent_app.command("follow")(follow)
