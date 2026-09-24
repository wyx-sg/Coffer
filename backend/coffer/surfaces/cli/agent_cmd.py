"""coffer agent ... commands.

Every command takes the agent's NAME and resolves it once, through ``_resolve``,
to the uid the routes address (ADR resource-identity-is-an-immutable-uid): the
round trip is paid at the surface a human stands at, not by teaching the daemon
a second way to be addressed.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import agent_config_cmd as _config
from coffer.surfaces.cli import agent_models_cmd as _models
from coffer.surfaces.cli import agent_native_memory_cmd as _native_memory
from coffer.surfaces.cli import agent_transcript_cmd as _transcripts
from coffer.surfaces.cli import agent_workspace_cmd as _workspace
from coffer.surfaces.cli._resolve import resolve_uid

app = typer.Typer(help="Manage registered AI agents")
config_app = typer.Typer(help="View and edit an agent's config files")
mcp_app = typer.Typer(help="Install/uninstall Coffer's MCP server into an agent")
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

    ``--name`` is optional — when omitted the daemon derives a stable
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
    typer.echo(f"registered: agent {registered}")


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
        uid = resolve_uid(c, "agent", name, verbose=verbose)
        r = c.get(f"/agents/{uid}")
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
    else:
        # The uid is shown here and nowhere else — a detail view is where a
        # reader looks for the value the agent's own config file cites.
        for k in ("name", "uid", "type", "config_dir"):
            typer.echo(f"{k}: {data[k]}")
        # The model binding is what the projector actually writes into the
        # agent's native config, so `show` is where a terminal-only user reads
        # back what `edit --model` did. "(unbound)" is a real state, not a
        # missing value: an unbound agent runs on its own default.
        for k in ("model", "fast_model", "wire_api"):
            typer.echo(f"{k}: {data.get(k) or '(unbound)'}")


@app.command("edit")
def edit(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    config_dir: str | None = typer.Option(None, "--config-dir"),
    description: str | None = typer.Option(None, "--description"),
    model: str | None = typer.Option(None, "--model", help="Model this agent answers with"),
    fast_model: str | None = typer.Option(
        None, "--fast-model", help="Small/fast model slot (anthropic wire only)"
    ),
    clear_fast_model: bool = typer.Option(False, "--clear-fast-model", help="Unbind the fast slot"),
    wire_api: str | None = typer.Option(
        None, "--wire-api", help="Codex wire api; `responses` is the only value it still loads"
    ),
) -> None:
    """Update an agent's fields, including the model it answers with.

    The model binding lives on the agent, not on the connection: an unbound
    agent projects no model and runs on its own default. A change here takes
    effect on disk the next time that agent's connection is activated
    (`coffer provider switch <name>`), which is what re-projects the config.

    --clear-fast-model unbinds the fast slot.

    \f
    ``--clear-fast-model`` is how the fast slot is *removed* — the route
    distinguishes an absent field from an explicit null, and only the second
    one unbinds.
    """
    given = [config_dir, description, model, fast_model, wire_api]
    if all(v is None for v in given) and not clear_fast_model:
        typer.echo("nothing to update", err=True)
        raise typer.Exit(1)
    if fast_model is not None and clear_fast_model:
        typer.echo("give either --fast-model or --clear-fast-model, not both", err=True)
        raise typer.Exit(2)
    verbose = (ctx.obj or {}).get("verbose", False)
    body: dict[str, object] = {}
    if config_dir is not None:
        body["config_dir"] = config_dir
    if description is not None:
        body["description"] = description
    if model is not None:
        body["model"] = model
    # An explicit null is the clear; omitting the key entirely leaves the slot
    # alone. Both are sent through `model_fields_set` on the route side.
    if clear_fast_model:
        body["fast_model"] = None
    elif fast_model is not None:
        body["fast_model"] = fast_model
    if wire_api is not None:
        body["wire_api"] = wire_api
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "agent", name, verbose=verbose)
        r = c.patch(f"/agents/{uid}", json=body)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"updated: agent {name}")


@app.command("rm")
def rm(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Remove an agent (re-discoverable on the next scan — removal isn't permanent)."""
    if not force and not typer.confirm(f"Really remove agent {name}?"):
        raise typer.Exit(1)
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "agent", name, verbose=verbose)
        r = c.delete(f"/agents/{uid}")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed: agent {name}")


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
# The commands themselves live in two siblings (backend file-size cap): whole
# files in ``agent_config_cmd``, directory-entry children in
# ``agent_workspace_cmd``. Both attach onto this typer, below.

app.add_typer(config_app, name="config")


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
        uid = resolve_uid(c, "agent", name, verbose=verbose)
        r = c.get(f"/agents/{uid}/mcp-install")
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
        uid = resolve_uid(c, "agent", name, verbose=verbose)
        r = c.post(f"/agents/{uid}/mcp-install")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"installed Coffer MCP into agent {name} ({r.json().get('command')})")


@mcp_app.command("uninstall")
def mcp_uninstall(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Remove Coffer's MCP server entry from this agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "agent", name, verbose=verbose)
        r = c.delete(f"/agents/{uid}/mcp-install")
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed Coffer MCP from agent {name}")


# --- workspace subcommands (mcp entries/plugins/dir configs) -----------------
# Implemented in agent_workspace_cmd.py to keep this file under the size cap.

_config.attach(config_app)
_workspace.attach(app, config_app=config_app, mcp_app=mcp_app)

# --- native-memory read command (agent_native_memory_cmd.py, same reason) ---

_native_memory.attach(app)

# --- transcript browse command (agent_transcript_cmd.py, same reason) ------

_transcripts.attach(app)

# --- model list command (agent_models_cmd.py, same reason) ----------------

_models.attach(app)
