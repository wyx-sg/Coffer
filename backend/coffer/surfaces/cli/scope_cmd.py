"""coffer scope ... commands (per-agent activation scope; ADR: per-agent-resource-scope).

Thin CLI wrapper over ``GET/PUT /api/v1/resources/{kind}/{name}/scope``.
Same ``<kind>:<name>`` ref parsing (``kind, _, name = ref.partition(":")`` +
``typer.Exit(2)`` guard) and the same ``client_or_exit()`` + ``check()``
call shape as the other resource sub-groups.

Three states, mirroring ``coffer.domain.scope``:

- ``scope show``                        — read the current one
- ``scope set <ref> --agents a,b``      — active only for those agents
- ``scope set <ref> --no-agents``       — dormant (active for no agent)
- ``scope clear <ref>``                 — unscoped (active for every agent)
"""

from __future__ import annotations

import json as _json

import typer

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Per-agent activation scope for a resource")


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _parse_ref(ref: str) -> tuple[str, str]:
    kind, _, name = ref.partition(":")
    if not kind or not name:
        typer.echo("ref must be <kind>:<name>", err=True)
        raise typer.Exit(2)
    return kind, name


@app.command("show")
def show(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Resource as <kind>:<name>"),
) -> None:
    """Show a resource's current scope and whether its kind supports scope."""
    verbose = _verbose(ctx)
    kind, name = _parse_ref(ref)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/resources/{kind}/{name}/scope")
        _cli_client.check(r, verbose=verbose)
    body = r.json()
    typer.echo(
        _json.dumps(
            {"scope": body["scope"], "supports_scope": body["supports_scope"]},
            indent=2,
        )
    )


@app.command("set")
def set_(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Resource as <kind>:<name>"),
    agents: str | None = typer.Option(
        None, "--agents", help="Comma-separated agent names this resource is active for"
    ),
    no_agents: bool = typer.Option(
        False, "--no-agents", help="Make the resource dormant (active for no agent)"
    ),
) -> None:
    """Replace a resource's scope with an explicit agent list.

    Whole-value write (no read-modify-write): ``--agents`` names exactly the
    agents the resource is active for. ``--no-agents`` writes the empty list,
    which is DORMANT — use ``scope clear`` to go back to every agent.
    """
    verbose = _verbose(ctx)
    kind, name = _parse_ref(ref)
    if bool(agents) == no_agents:
        typer.echo("pick exactly one of --agents / --no-agents", err=True)
        raise typer.Exit(2)

    if no_agents:
        scope: list[str] = []
        typer.echo(f"{kind}:{name} is now DORMANT — active for no agent")
    else:
        scope = [a.strip() for a in agents.split(",") if a.strip()]  # type: ignore[union-attr]
        if not scope:
            typer.echo("--agents needs at least one agent name", err=True)
            raise typer.Exit(2)

    c, _info = _cli_client.client_or_exit()
    with c:
        put_r = c.put(f"/resources/{kind}/{name}/scope", json={"scope": scope})
        _cli_client.check(put_r, verbose=verbose)
    typer.echo(_json.dumps({"scope": put_r.json()["scope"]}, indent=2))


@app.command("clear")
def clear(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Resource as <kind>:<name>"),
) -> None:
    """Clear the scope back to unscoped — active for every agent."""
    verbose = _verbose(ctx)
    kind, name = _parse_ref(ref)
    c, _info = _cli_client.client_or_exit()
    with c:
        typer.echo(f"clearing scope for {kind}:{name} — it becomes active for every agent")
        put_r = c.put(f"/resources/{kind}/{name}/scope", json={"scope": None})
        _cli_client.check(put_r, verbose=verbose)
    typer.echo(_json.dumps({"scope": put_r.json()["scope"]}, indent=2))
