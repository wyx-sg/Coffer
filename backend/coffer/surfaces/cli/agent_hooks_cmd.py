"""``coffer agent hooks <name>`` — every hook in the agent's native config.

CLI parity for ``GET /agents/{uid}/hooks`` (spec agent-registry "List every
hook in the agent's native config"): one line per hook with its event,
matcher, source and command, Coffer's own marked, then Coffer's hook health,
whether the agent will run it (its trust), and when it last fired. Read only.

Its own module so ``agent_cmd`` stays under the backend file-size cap;
``agent_cmd`` calls :func:`attach`.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

#: What to tell the user when the agent will not run Coffer's hook. Coffer
#: never approves its own hook: that is the user's act in the agent.
_NEEDS_APPROVAL = {
    "untrusted": "Coffer's hook needs approval in Codex: run /hooks there and trust it.",
    "modified": "Coffer's hook changed since you approved it: run /hooks in Codex and trust it.",
    "disabled": "Coffer's hook is switched off in Codex: turn it back on with /hooks.",
    "unknown": "Could not read Codex's hook trust record (config.toml).",
}


def _line(hook: dict[str, Any]) -> str:
    source = f"plugin {hook['plugin']}" if hook.get("plugin") else str(hook["source"])
    matcher = f" [{hook['matcher']}]" if hook.get("matcher") else ""
    mark = "* " if hook.get("coffer") else "  "
    return f"{mark}{hook['event']}{matcher}  ({source})  {hook['command']}"


def hooks(
    ctx: typer.Context,
    name: str = typer.Argument(..., metavar="NAME", help="Agent name or uid"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List every hook the agent will run; Coffer's own is marked with *."""
    verbose = bool((ctx.obj or {}).get("verbose", False))
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{resolve_uid(c, 'agent', name, verbose=verbose)}/hooks")
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    for hook in data["items"]:
        typer.echo(_line(hook))
    if not data["items"]:
        typer.echo("(no hooks)")
    own = data.get("coffer_hook")
    if own is not None:
        fired = own.get("last_fired_at") or "never"
        trust = own.get("trust") or "not_required"
        trusted = "" if trust == "not_required" else f", trust {trust}"
        typer.echo(f"coffer hook: {own['health']} on {own['event']}{trusted}, last fired {fired}")
        if own["health"] != "missing" and trust in _NEEDS_APPROVAL:
            typer.echo(_NEEDS_APPROVAL[trust])
    for err in data.get("parse_errors") or []:
        typer.echo(f"could not parse {err['path']}: {err['error']}", err=True)


def attach(agent_app: typer.Typer) -> None:
    """Register the hooks command on agent_cmd's existing typer."""
    agent_app.command("hooks")(hooks)
