"""coffer scope ... commands (ADR-045 machine x agent activation scope).

Thin CLI wrapper over ``GET/PUT /api/v1/resources/{kind}/{name}/scope``
(Tasks 7/14). Modelled on ``sync_cmd.py``'s ``override`` sub-group: same
``<kind>:<name>`` ref parsing (``kind, _, name = ref.partition(":")`` +
``typer.Exit(2)`` guard) and the same ``client_or_exit()`` + ``check()``
call shape.
"""

from __future__ import annotations

import json as _json

import typer

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Machine x agent activation scope for a resource")


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
    """Show a resource's current scope and which axes its kind supports."""
    verbose = _verbose(ctx)
    kind, name = _parse_ref(ref)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/resources/{kind}/{name}/scope")
        _cli_client.check(r, verbose=verbose)
    body = r.json()
    typer.echo(_json.dumps({"scope": body["scope"], "axes": body["axes"]}, indent=2))


@app.command("set")
def set_(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Resource as <kind>:<name>"),
    machine: str = typer.Option(
        ..., "--machine", help="Machine id this entry applies to, or '*' for every machine"
    ),
    agents: str | None = typer.Option(
        None, "--agents", help="Comma-separated agent names active on this machine"
    ),
    all_agents: bool = typer.Option(
        False, "--all-agents", help="Active for every agent on this machine"
    ),
) -> None:
    """Set (merge) one machine's entry into a resource's scope.

    Read-modify-write: fetches the current scope (a null scope is treated as
    ``{}``), overwrites the single ``--machine`` entry, and PUTs the merged
    map back — every other machine's entry is left untouched.
    """
    verbose = _verbose(ctx)
    kind, name = _parse_ref(ref)
    if agents and all_agents:
        typer.echo("pick exactly one of --agents / --all-agents", err=True)
        raise typer.Exit(2)

    c, _info = _cli_client.client_or_exit()
    with c:
        get_r = c.get(f"/resources/{kind}/{name}/scope")
        _cli_client.check(get_r, verbose=verbose)
        current = get_r.json()
        axes = current["axes"]

        if "agent" in axes:
            if not agents and not all_agents:
                typer.echo("pick exactly one of --agents / --all-agents", err=True)
                raise typer.Exit(2)
            if all_agents:
                value: str | list[str] = "*"
            else:
                value = [a.strip() for a in agents.split(",") if a.strip()]  # type: ignore[union-attr]
                if not value:
                    typer.echo("--agents needs at least one agent name", err=True)
                    raise typer.Exit(2)
        else:
            if agents:
                typer.echo(
                    f"{kind} has no agent axis (machine-only scope) — remove --agents; "
                    "--all-agents is implied",
                    err=True,
                )
                raise typer.Exit(2)
            value = "*"

        scope = dict(current["scope"] or {})
        scope[machine] = value
        put_r = c.put(f"/resources/{kind}/{name}/scope", json={"scope": scope})
        _cli_client.check(put_r, verbose=verbose)
    typer.echo(_json.dumps({"scope": put_r.json()["scope"]}, indent=2))


@app.command("clear")
def clear(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Resource as <kind>:<name>"),
    machine: str | None = typer.Option(
        None,
        "--machine",
        help="Drop only this machine's entry (id or '*'); omit to clear the whole scope",
    ),
) -> None:
    """Drop one machine's entry, or clear the whole scope back to active-everywhere.

    With ``--machine``: removes that one entry and PUTs the remaining map —
    if that empties the map, it is PUT as ``{}`` (dormant on every machine),
    never silently restored to "everywhere". Without ``--machine``: PUTs
    ``scope: null``, which *does* restore active-everywhere.
    """
    verbose = _verbose(ctx)
    kind, name = _parse_ref(ref)
    c, _info = _cli_client.client_or_exit()
    with c:
        if machine is None:
            typer.echo(
                f"clearing scope for {kind}:{name} — it becomes active on every machine, "
                "for every agent"
            )
            put_r = c.put(f"/resources/{kind}/{name}/scope", json={"scope": None})
            _cli_client.check(put_r, verbose=verbose)
        else:
            get_r = c.get(f"/resources/{kind}/{name}/scope")
            _cli_client.check(get_r, verbose=verbose)
            current_scope = get_r.json()["scope"]
            if current_scope is None:
                typer.echo(
                    f"{kind}:{name} is already active everywhere; nothing to clear for machine "
                    f"'{machine}'"
                )
                return
            scope = dict(current_scope)
            scope.pop(machine, None)
            if not scope:
                typer.echo(
                    f"warning: {kind}:{name} now has no scope entries — it is DORMANT "
                    "(inactive) on every machine"
                )
            put_r = c.put(f"/resources/{kind}/{name}/scope", json={"scope": scope})
            _cli_client.check(put_r, verbose=verbose)
    typer.echo(_json.dumps({"scope": put_r.json()["scope"]}, indent=2))
