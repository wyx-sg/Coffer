"""``coffer agent models <agent_key>`` — the models an agent can be put on.

CLI parity for the web model picker: both read
``GET /agent-providers/{agent_key}/models``, the one list every surface is
served (spec provider-switching "Serve one model list to every surface"). The
argument is the agent key the provider registry answers for (``claude_code``,
``codex``), not an agent resource's name — the route is keyed that way, and an
unknown key is the route's 404.

Its own module (rather than more lines in ``agent_cmd.py``) so both stay under
the backend file-size cap; ``agent_cmd`` calls :func:`attach`.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client


def _line(model: dict[str, Any]) -> str:
    """``id  [label]  [efforts: a, b*, c]`` — ``*`` marks the agent's default effort."""
    parts = [str(model["id"])]
    label = model.get("label") or ""
    if label and label != model["id"]:
        parts.append(str(label))
    efforts = model.get("efforts") or []
    if efforts:
        default = model.get("default_effort")
        levels = ", ".join(f"{e}*" if e == default else str(e) for e in efforts)
        parts.append(f"efforts: {levels}")
    return "  ".join(parts)


def models(
    ctx: typer.Context,
    agent_key: str = typer.Argument(..., help="Agent type, e.g. claude_code or codex"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List the models a picker offers for this agent, with their effort levels."""
    verbose = bool((ctx.obj or {}).get("verbose", False))
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agent-providers/{agent_key}/models")
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    for model in data["models"]:
        typer.echo(_line(model))


def attach(agent_app: typer.Typer) -> None:
    """Register the models command on agent_cmd's existing typer."""
    agent_app.command("models")(models)
