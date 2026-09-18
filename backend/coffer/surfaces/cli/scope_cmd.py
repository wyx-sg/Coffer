"""coffer scope ... commands (activation scope; ADR: per-agent-resource-scope).

Thin CLI wrapper over ``GET/PUT /api/v1/resources/{uid}/scope``. Takes a KIND
and a NAME, like every other resource command, and resolves both the resource
and the agents it names through ``_resolve``.

One allow-list of agents, mirroring ``coffer.domain.scope``:

- ``scope show <kind> <name>``                    — read the current one
- ``scope set <kind> <name> --agents a,b``        — active only for those agents
- ``scope set <kind> <name> --no-agents``         — dormant (matches no agent)
- ``scope clear <kind> <name>``                   — unscoped (every agent)

**The stored list holds agent UIDs; this surface speaks agent NAMES.** The
translation happens here, in both directions: ``set`` resolves each name to a
uid before writing, and ``show`` renders the stored uids back as names. Doing it
at the surface is what keeps the daemon on one vocabulary — while the stored
list held names, an agent had two of them and a whole module existed to
reconcile the two.

``set`` is a whole-value write, not a read-modify-write.

A scope applies to THIS machine and is never synced: every machine holding the
vault sets its own, so the answer is always the one you can verify from the
machine you are sitting at.
"""

from __future__ import annotations

import json as _json
from typing import Any

import httpx
import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

app = typer.Typer(help="Activation scope for a resource")

_KIND = typer.Argument(..., help="Resource kind, e.g. mcp_server")
_NAME = typer.Argument(..., help="Resource name")


def _agent_uids(c: httpx.Client, names: list[str], *, verbose: bool) -> list[str]:
    """Each agent NAME the user typed, as the uid the scope stores.

    An unknown name is refused rather than passed through. A uid that matches
    no agent is legal in the stored value — a machine may be scoped to an agent
    it does not have yet — but a name the user typed that resolves to nothing
    is almost always a typo, and silently writing it would produce a scope that
    quietly matches one agent fewer than they think.
    """
    return [resolve_uid(c, "agent", name, verbose=verbose) for name in names]


def _agent_names(
    c: httpx.Client, scope: dict[str, Any] | None, *, verbose: bool
) -> dict[str, Any] | None:
    """The stored scope with its agent uids rendered back as names.

    A uid with no agent behind it is shown verbatim: it is a real entry of the
    stored value and hiding it would make the displayed scope narrower than the
    one in the database.
    """
    if scope is None or scope.get("agents") is None:
        return scope
    r = c.get("/resources", params={"kind": "agent"})
    _cli_client.check(r, verbose=verbose)
    names_by_uid = {a["uid"]: a["name"] for a in r.json()["resources"]}
    return {**scope, "agents": [names_by_uid.get(uid, uid) for uid in scope["agents"]]}


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _axis(names: str | None, empty: bool, flag: str) -> list[str] | None:
    """The written allow-list: a list, the empty list, or unrestricted."""
    if names and empty:
        typer.echo(f"pick at most one of --{flag} / --no-{flag}", err=True)
        raise typer.Exit(2)
    if empty:
        return []
    if names is None:
        return None
    parsed = [n.strip() for n in names.split(",") if n.strip()]
    if not parsed:
        typer.echo(f"--{flag} needs at least one name", err=True)
        raise typer.Exit(2)
    return parsed


@app.command("show")
def show(
    ctx: typer.Context,
    kind: str = _KIND,
    name: str = _NAME,
) -> None:
    """Show a resource's current scope and whether its kind supports scope."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, kind, name, verbose=verbose)
        r = c.get(f"/resources/{uid}/scope")
        _cli_client.check(r, verbose=verbose)
        body = r.json()
        shown = _agent_names(c, body["scope"], verbose=verbose)
    typer.echo(
        _json.dumps(
            {"scope": shown, "supports_scope": body["supports_scope"]},
            indent=2,
        )
    )


@app.command("set")
def set_(
    ctx: typer.Context,
    kind: str = _KIND,
    name: str = _NAME,
    agents: str | None = typer.Option(
        None, "--agents", help="Comma-separated agent names this resource is active for"
    ),
    no_agents: bool = typer.Option(
        False, "--no-agents", help="Make the resource dormant (active for no agent)"
    ),
) -> None:
    """Replace a resource's scope with an explicit allow-list of agents.

    Whole-value write (no read-modify-write): ``--agents`` restricts to exactly
    those names. ``--no-agents`` writes the empty list, which is DORMANT — use
    ``scope clear`` to go back to every agent.

    The scope written here applies to THIS machine only and is not synced.
    """
    verbose = _verbose(ctx)
    if not (agents or no_agents):
        typer.echo("name the agents (--agents, or --no-agents)", err=True)
        raise typer.Exit(2)

    named = _axis(agents, no_agents, "agents")
    if no_agents:
        typer.echo(f"{kind} {name} is now DORMANT — an empty allow-list matches nothing")

    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, kind, name, verbose=verbose)
        scope = {"agents": None if named is None else _agent_uids(c, named, verbose=verbose)}
        put_r = c.put(f"/resources/{uid}/scope", json={"scope": scope})
        _cli_client.check(put_r, verbose=verbose)
        shown = _agent_names(c, put_r.json()["scope"], verbose=verbose)
    typer.echo(_json.dumps({"scope": shown}, indent=2))


@app.command("clear")
def clear(
    ctx: typer.Context,
    kind: str = _KIND,
    name: str = _NAME,
) -> None:
    """Clear the scope back to unscoped — active for every agent on this machine."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, kind, name, verbose=verbose)
        typer.echo(f"clearing scope for {kind} {name} — it becomes active for every agent")
        put_r = c.put(f"/resources/{uid}/scope", json={"scope": None})
        _cli_client.check(put_r, verbose=verbose)
    typer.echo(_json.dumps({"scope": put_r.json()["scope"]}, indent=2))
