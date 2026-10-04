"""`coffer proxy …` — the local model proxy (spec provider-switching
"Authenticate each agent to the proxy with its own local token").

``token`` is what Coffer writes into both agents' config — Claude Code's
``apiKeyHelper`` and Codex's provider ``auth`` command — so it takes the
agent's uid, the identity that line keeps citing across a rename, and prints
nothing but the token on stdout.
"""

from __future__ import annotations

import typer

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="The local model proxy's per-agent tokens", hidden=True)


@app.command("token", hidden=True)
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


__all__ = ["app"]
