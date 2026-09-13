"""coffer scope ... commands (activation scope; ADR: per-agent-resource-scope).

Thin CLI wrapper over ``GET/PUT /api/v1/resources/{kind}/{name}/scope``.
Same ``<kind>:<name>`` ref parsing (``kind, _, name = ref.partition(":")`` +
``typer.Exit(2)`` guard) and the same ``client_or_exit()`` + ``check()``
call shape as the other resource sub-groups.

Two independent axes, ``AND``-ed, mirroring ``coffer.domain.scope``:

- ``scope show``                         — read the current one
- ``scope set <ref> --agents a,b``       — active only for those agents
- ``scope set <ref> --machines x,y``     — active only on those machines
- ``scope set <ref> --no-agents``        — dormant (matches no agent)
- ``scope clear <ref>``                  — unscoped (every agent, every machine)

``set`` is a whole-value write: an axis you do not name is written ``null``,
which is unrestricted.
"""

from __future__ import annotations

import json as _json

import typer

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Activation scope for a resource")


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _parse_ref(ref: str) -> tuple[str, str]:
    kind, _, name = ref.partition(":")
    if not kind or not name:
        typer.echo("ref must be <kind>:<name>", err=True)
        raise typer.Exit(2)
    return kind, name


def _axis(names: str | None, empty: bool, flag: str) -> list[str] | None:
    """One axis of the written scope: a list, the empty list, or unrestricted."""
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
    machines: str | None = typer.Option(
        None, "--machines", help="Comma-separated machine ids this resource is active on"
    ),
    no_machines: bool = typer.Option(
        False, "--no-machines", help="Make the resource dormant (active on no machine)"
    ),
) -> None:
    """Replace a resource's scope with an explicit pair of allow-lists.

    Whole-value write (no read-modify-write): an axis you name restricts to
    exactly those names, and an axis you leave out becomes ``null``, which is
    unrestricted. ``--no-agents``/``--no-machines`` write the empty list, which
    is DORMANT — use ``scope clear`` to go back to everywhere.
    """
    verbose = _verbose(ctx)
    kind, name = _parse_ref(ref)
    if not (agents or no_agents or machines or no_machines):
        typer.echo("name at least one axis (--agents/--machines, or their --no- forms)", err=True)
        raise typer.Exit(2)

    scope = {
        "agents": _axis(agents, no_agents, "agents"),
        "machines": _axis(machines, no_machines, "machines"),
    }
    if no_agents or no_machines:
        typer.echo(f"{kind}:{name} is now DORMANT — an empty axis matches nothing")

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
    """Clear the scope back to unscoped — every agent, every machine."""
    verbose = _verbose(ctx)
    kind, name = _parse_ref(ref)
    c, _info = _cli_client.client_or_exit()
    with c:
        typer.echo(
            f"clearing scope for {kind}:{name} — "
            "it becomes active for every agent, on every machine"
        )
        put_r = c.put(f"/resources/{kind}/{name}/scope", json={"scope": None})
        _cli_client.check(put_r, verbose=verbose)
    typer.echo(_json.dumps({"scope": put_r.json()["scope"]}, indent=2))
