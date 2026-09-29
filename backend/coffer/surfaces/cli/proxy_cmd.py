"""`coffer proxy …` — the local model proxy (spec provider-switching
"Authenticate each agent to the proxy with its own local token").

``token`` is what Coffer writes into both agents' config — Claude Code's
``apiKeyHelper`` and Codex's provider ``auth`` command — so it takes the
agent's uid, the identity that line keeps citing across a rename, and prints
nothing but the token on stdout.
"""

from __future__ import annotations

import json as _json

import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_ref

app = typer.Typer(help="Inspect the local model proxy and its per-agent tokens")


@app.command("token")
def token(
    agent_uid: str = typer.Option(..., "--agent-uid", help="The agent whose token to print"),
) -> None:
    """Print an agent's local proxy token (what its key helper runs).

    The token unlocks only this machine's loopback model proxy; it is never a
    provider key. Exits 4 with nothing on stdout for an agent this machine
    does not have, so a stale helper fails instead of printing a token.
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/proxy/tokens/{agent_uid}")
        if r.status_code == 404:
            typer.echo(f"no agent {agent_uid!r} on this machine", err=True)
            raise typer.Exit(4)
        r.raise_for_status()
    typer.echo(r.json()["token"])


@app.command("rotate")
def rotate(ref: str = typer.Argument(..., help="Agent name or uid")) -> None:
    """Replace an agent's local proxy token; the old one stops working at once."""
    c, _info = _cli_client.client_or_exit()
    with c:
        agent = resolve_ref(c, "agent", ref, verbose=False)
        r = c.post(f"/proxy/tokens/{agent['uid']}/rotate")
        _cli_client.check(r, verbose=False)
    typer.echo(f"rotated the proxy token of {agent['name']}")


@app.command("status")
def status_(json: bool = typer.Option(False, "--json", help="Machine-readable output")) -> None:
    """Show whether the model proxy is running, where, and how often it restarted."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/proxy/status")
        _cli_client.check(r, verbose=False)
    data = r.json()
    if json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"running: {'yes' if data['running'] else 'no'}")
    typer.echo(f"port: {data['port']}")
    for key in ("pid", "version", "restarts", "revision", "last_error"):
        if data.get(key) is not None:
            typer.echo(f"{key}: {data[key]}")


__all__ = ["app"]
