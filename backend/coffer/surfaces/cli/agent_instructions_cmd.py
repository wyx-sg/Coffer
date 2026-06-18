"""coffer agent instructions subcommands (spec 004 item 1).

The master-instructions hub + per-agent delivery verbs. Kept out of
``agent_cmd.py`` to respect the 400-line backend file cap; ``agent_cmd`` calls
:func:`attach` so the user-facing tree is ``coffer agent instructions ...``.
"""

from __future__ import annotations

import json as _json
import pathlib
import sys
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client

instructions_app = typer.Typer(help="Master instructions hub + per-agent delivery")


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _not_found_exit(r: Any) -> None:
    if r.status_code == 404:
        typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
        raise typer.Exit(4)


@instructions_app.command("master")
def master(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Print the hub master instructions (empty when never written)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/instructions")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(data["content"], nl=False)


@instructions_app.command("set-master")
def set_master(
    ctx: typer.Context,
    file: str | None = typer.Option(
        None, "--file", "-f", help="Read content from this file; omit or '-' for stdin."
    ),
    expected_fingerprint: str | None = typer.Option(
        None, "--expected-fingerprint", help="Reject (409) if the master changed since this."
    ),
) -> None:
    """Write the hub master instructions from a file or stdin."""
    content = (
        pathlib.Path(file).read_text(encoding="utf-8") if file and file != "-" else sys.stdin.read()
    )
    body: dict[str, Any] = {"content": content}
    if expected_fingerprint is not None:
        body["expected_fingerprint"] = expected_fingerprint
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put("/instructions", json=body)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"master instructions updated (fingerprint {r.json()['fingerprint'][:12]})")


@instructions_app.command("status")
def status(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Report whether the master is delivered to this agent and in sync."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}/instructions")
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"delivered: {data['delivered']}")
    typer.echo(f"in_sync: {data['in_sync']}")


@instructions_app.command("deliver")
def deliver(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Deliver the master instructions into this agent's instructions file."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/agents/{name}/instructions")
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"delivered master instructions to agent:{name}")


@instructions_app.command("remove")
def remove(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Strip the Coffer-managed instructions block from this agent."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/agents/{name}/instructions")
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"removed delivered instructions from agent:{name}")


@instructions_app.command("adopt")
def adopt(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    """Make this agent's instructions the new hub master."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/agents/{name}/instructions/adopt")
        _not_found_exit(r)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"adopted agent:{name} instructions into the master")


def attach(agent_app: typer.Typer) -> None:
    """Register ``coffer agent instructions ...`` on agent_cmd's typer."""
    agent_app.add_typer(instructions_app, name="instructions")
