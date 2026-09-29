"""``coffer agent connect | disconnect | connection`` — an agent's Coffer connection.

The CLI half of ``/api/v1/agents/{uid}/coffer-connection`` (spec agent-registry
"Connect an agent to Coffer in one action", "Report an agent's Coffer connection
part by part", "Disconnect an agent from Coffer"). Kept out of ``agent_cmd`` for
the file-size budget; attached onto the same typer.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import verbose_of
from coffer.surfaces.cli._resolve import resolve_ref

#: How each part reads in a person's terminal.
_PART_LABELS = {
    "mcp": "gateway MCP entry",
    "memory_hook": "memory delivery hook",
}

_STATE_LABELS = {
    "connected": "connected",
    "partial": "needs repair (run `coffer agent connect` again)",
    "disconnected": "not connected",
}


def _call(ctx: typer.Context, name: str, method: str) -> dict[str, Any]:
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_ref(c, "agent", name, verbose=verbose)["uid"]
        r = c.request(method, f"/agents/{uid}/coffer-connection")
        _cli_client.check(r, verbose=verbose)
    data: dict[str, Any] = r.json()
    return data


def state_label(state: str) -> str:
    """How a connection state reads in a person's terminal."""
    return _STATE_LABELS.get(state, state)


def echo_parts(data: dict[str, Any]) -> None:
    """One indented line per part — shared with ``coffer agent show``."""
    for part in data["parts"]:
        label = _PART_LABELS.get(part["key"], part["key"])
        mark = "installed" if part["installed"] else "missing"
        detail = f" ({part['detail']})" if part.get("detail") else ""
        typer.echo(f"  {label}: {mark}{detail}")


def connection(
    ctx: typer.Context,
    name: str = typer.Argument(..., metavar="NAME", help="Agent name or uid"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Report whether this agent is connected to Coffer, part by part."""
    data = _call(ctx, name, "GET")
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"{name}: {state_label(data['state'])}")
    echo_parts(data)


def connect(
    ctx: typer.Context,
    name: str = typer.Argument(..., metavar="NAME", help="Agent name or uid"),
) -> None:
    """Connect this agent to Coffer: install every part that applies to it."""
    data = _call(ctx, name, "POST")
    typer.echo(f"connected agent {name} to Coffer")
    echo_parts(data)


def disconnect(
    ctx: typer.Context,
    name: str = typer.Argument(..., metavar="NAME", help="Agent name or uid"),
) -> None:
    """Disconnect this agent from Coffer: remove every part Coffer wrote into it."""
    _call(ctx, name, "DELETE")
    typer.echo(f"disconnected agent {name} from Coffer")


def attach(app: typer.Typer) -> None:
    """Register the three commands on ``agent_cmd``'s typer."""
    app.command("connection")(connection)
    app.command("connect")(connect)
    app.command("disconnect")(disconnect)
