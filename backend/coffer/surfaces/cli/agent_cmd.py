"""coffer agent ... commands."""

from __future__ import annotations

import json as _json
from typing import Any

import click
import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import agent_native_memory_cmd as _native_memory
from coffer.surfaces.cli import agent_workspace_cmd as _workspace

app = typer.Typer(help="Manage registered AI agents")
config_app = typer.Typer(help="View and edit an agent's config files")
mcp_app = typer.Typer(help="Install/uninstall Coffer's MCP server into an agent")
hook_app = typer.Typer(help="Install/uninstall Coffer's lifecycle hooks into an agent")
_console = Console()


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List registered agents."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/agents")
        _cli_client.check(r, verbose=verbose)
    items = r.json()["items"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    table = Table(title="Agents")
    for col in ("Name", "Type", "Config Dir"):
        table.add_column(col)
    for it in items:
        table.add_row(
            it["name"],
            it["type"],
            it["config_dir"],
        )
    _console.print(table)


@app.command("add")
def add(
    ctx: typer.Context,
    agent_type: str = typer.Argument(..., help="claude_code | codex"),
    name: str | None = typer.Option(
        None, "--name", "-n", help="Resource name (defaults to a per-type name, e.g. claude-code)."
    ),
    config_dir: str | None = typer.Option(
        None, "--config-dir", help="Override config directory (default: ~/.claude etc.)."
    ),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Register an agent.

    FR-006: ``--name`` is optional — when omitted the daemon derives a stable
    per-type default (``claude_code`` → ``claude-code``).
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    # Only send `name` when provided so the server applies its per-type default.
    body: dict[str, Any] = {
        "type": agent_type,
        "config_dir": config_dir,
        "description": description,
    }
    if name is not None:
        body["name"] = name
    with c:
        r = c.post("/agents", json=body)
        _cli_client.check(r, verbose=verbose)
        registered = r.json().get("name", name) if r.content else name
    typer.echo(f"registered: agent:{registered}")


@app.command("show")
def show(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}")
        if r.status_code == 404:
            typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
    else:
        for k in ("name", "type", "config_dir"):
            typer.echo(f"{k}: {data[k]}")


@app.command("edit")
def edit(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    config_dir: str | None = typer.Option(None, "--config-dir"),
    description: str | None = typer.Option(None, "--description"),
    disable_native_memory: bool | None = typer.Option(
        None,
        "--disable-native-memory/--enable-native-memory",
        help="Disable (or restore) the agent's native write-side memory (Coffer becomes the store)",
    ),
) -> None:
    """Update an agent's fields."""
    if config_dir is None and description is None and disable_native_memory is None:
        typer.echo("nothing to update", err=True)
        raise typer.Exit(1)
    verbose = (ctx.obj or {}).get("verbose", False)
    body: dict[str, object] = {}
    if config_dir is not None:
        body["config_dir"] = config_dir
    if description is not None:
        body["description"] = description
    if disable_native_memory is not None:
        body["disable_native_memory"] = disable_native_memory
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/agents/{name}", json=body)
        if r.status_code == 404:
            typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"updated: agent:{name}")


@app.command("rm")
def rm(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Remove an agent (re-discoverable on the next scan — removal isn't permanent)."""
    if not force and not typer.confirm(f"Really remove agent:{name}?"):
        raise typer.Exit(1)
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/agents/{name}")
        if r.status_code == 404:
            typer.echo("not found", err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed: agent:{name}")


@app.command("detect")
def detect(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Discover installed agents that aren't registered yet (read-only).

    Detection never adds anything on its own — it lists candidates and shows
    the `coffer agent add` command to register each (discovery + confirm).
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/agents/candidates")
        _cli_client.check(r, verbose=verbose)
    cands = r.json()["candidates"]
    if output_json:
        typer.echo(_json.dumps(cands, indent=2))
        return
    if not cands:
        typer.echo("no new agents detected")
        return
    for a in cands:
        typer.echo(
            f"detected: {a['type']} -> add with "
            f"`coffer agent add {a['type']} --name {a['suggested_name']}`"
        )


# --- coffer agent config ... -------------------------------------------------

app.add_typer(config_app, name="config")


def _not_found_exit(r: Any) -> None:
    if r.status_code == 404:
        typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
        raise typer.Exit(4)


@config_app.command("ls")
def config_ls(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List an agent's curated config files."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}/config-files")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    items = r.json()["items"]
    if output_json:
        typer.echo(_json.dumps(items, indent=2))
        return
    table = Table(title=f"Config files — {name}")
    for col in ("Key", "Format", "Path", "Exists"):
        table.add_column(col)
    for it in items:
        table.add_row(it["key"], it["format"], it["path"], "✓" if it["exists"] else "")
    _console.print(table)


@config_app.command("cat")
def config_cat(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    key: str = typer.Argument(..., help="Config-file key (e.g. settings, config, memory)"),
) -> None:
    """Print one config file's content."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}/config-files/{key}")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    typer.echo(r.json()["content"], nl=False)


@config_app.command("edit")
def config_edit(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    key: str = typer.Argument(..., help="Config-file key (e.g. settings, config, memory)"),
    from_file: str | None = typer.Option(
        None,
        "--from-file",
        help="Read the new content from PATH instead of opening $EDITOR (non-interactive).",
    ),
) -> None:
    """Edit one config file. Opens $EDITOR on its current content, or use --from-file.

    On save, Coffer validates the content against the file's format (malformed
    JSON/TOML is rejected and the on-disk file is left unchanged), writes it
    atomically, and keeps a `<path>.bak` of the prior version.
    """
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        # Fetch current content (also resolves unknown agent/key -> exit 4).
        r = c.get(f"/agents/{name}/config-files/{key}")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
        current = r.json()["content"]

        if from_file is not None:
            import pathlib

            try:
                content = pathlib.Path(from_file).read_text(encoding="utf-8")
            except OSError as e:
                typer.echo(f"cannot read {from_file}: {e}", err=True)
                raise typer.Exit(1) from e
        else:
            # click.edit (typer has no `edit`): opens $EDITOR with the current
            # content; returns None if the user made no changes / aborted.
            edited = click.edit(current, extension=f".{key}")
            if edited is None:
                typer.echo("no changes", err=True)
                raise typer.Exit(0)
            content = edited

        w = c.put(f"/agents/{name}/config-files/{key}", json={"content": content})
        _not_found_exit(w)
        if w.status_code == 422:
            typer.echo(w.json().get("error", {}).get("message", "invalid content"), err=True)
            raise typer.Exit(2)
        _cli_client.check(w, verbose=verbose)
    typer.echo(f"saved: {key} (a .bak was kept)")


# --- coffer agent mcp ... ----------------------------------------------------

app.add_typer(mcp_app, name="mcp")


@mcp_app.command("status")
def mcp_status(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Report whether Coffer's MCP is installed in this agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}/mcp-install")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"installed: {data['installed']}")
    if data.get("command"):
        typer.echo(f"command: {data['command']}")


@mcp_app.command("install")
def mcp_install(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Install Coffer's MCP server entry into this agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/agents/{name}/mcp-install")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"installed Coffer MCP into agent:{name} ({r.json().get('command')})")


@mcp_app.command("uninstall")
def mcp_uninstall(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Remove Coffer's MCP server entry from this agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/agents/{name}/mcp-install")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed Coffer MCP from agent:{name}")


# --- coffer agent hook ... ---------------------------------------------------

app.add_typer(hook_app, name="hook")


@hook_app.command("status")
def hook_status(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Report whether Coffer's lifecycle hooks are installed in this agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}/hook-install")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"installed: {data['installed']}")
    if data.get("command"):
        typer.echo(f"command: {data['command']}")


@hook_app.command("install")
def hook_install(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Install Coffer's SessionStart/SessionEnd hooks into this agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/agents/{name}/hook-install")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"installed Coffer hooks into agent:{name} ({r.json().get('command')})")


@hook_app.command("uninstall")
def hook_uninstall(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Remove Coffer's lifecycle hooks from this agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/agents/{name}/hook-install")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed Coffer hooks from agent:{name}")


# --- workspace subcommands (mcp entries/plugins/dir configs/follow) -----------
# Implemented in agent_workspace_cmd.py to keep this file under the size cap.

_workspace.attach(app, config_app=config_app, mcp_app=mcp_app)

# --- native-memory subcommands (spec 004 FR-040/FR-041: list + import) --------
# Implemented in agent_native_memory_cmd.py to keep this file under the size cap.

_native_memory.attach(app)
