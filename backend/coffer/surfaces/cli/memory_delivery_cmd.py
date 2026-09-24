"""``coffer memory delivery …`` — the install half of the memory layer's push.

Three commands: what is installed, install it, remove it (spec memory "Install
delivery hooks explicitly and removably").
Split out of ``memory_cmd.py`` to respect the 400-line backend file cap, along
the seam that was already there — every other command in that group reads or
rewrites the memory tree, and these three write into an **agent's own settings
file** instead. The same ``attach``-on-the-existing-typer pattern as
``agent_workspace_cmd.py`` and ``agent_native_memory_cmd.py`` keeps the
user-facing tree exactly where it was: ``coffer memory delivery``,
``delivery-install``, ``delivery-remove``.

Each takes the agent's **name**, because that is what a person knows, and
resolves it once to the uid the routes take. The uid is also what ends up
written into the settings file, so relabelling the agent afterwards costs no
reinstall (ADR resource-identity-is-an-immutable-uid).
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

#: These commands name an *agent*, not a partition — the one subject the rest
#: of ``coffer memory`` never mentions, and the reason this module exists.
_KIND_AGENT = "agent"

_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def delivery_status(
    ctx: typer.Context,
    agent: str = typer.Option("", "--agent", help="Restrict to one agent, by name"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show per-agent delivery installation state.

    Installed or not, and nothing else. Whether the hook has ever *fired* is an
    event, not a property of an agent, so it is read on the audit surface:
    ``coffer audit list --event-type memory_delivery_fired``.
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        params = None
        if agent:
            params = {"agent_uid": resolve_uid(c, _KIND_AGENT, agent, verbose=_verbose(ctx))}
        r = c.get("/memory/delivery", params=params)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    table = Table(title="Memory delivery")
    table.add_column("agent")
    table.add_column("installed")
    table.add_column("event")
    table.add_column("command")
    for d in data["delivery"]:
        # The name, because this is a table a person reads. The row carries the
        # uid too, and ``--json`` hands it to a script that wants to act on one.
        table.add_row(d["agent_name"], str(d["installed"]), d["event"], d["command"])
    _console.print(table)


def delivery_install(
    ctx: typer.Context,
    agent: str = typer.Argument(..., help="Agent name"),
) -> None:
    """Install Coffer's session-start hook for an agent.

    Renaming the agent later does not need a reinstall.

    \f
    The name is resolved here; the uid is what the route takes and what ends up
    written into the agent's settings file, so relabelling the agent afterwards
    costs no reinstall.
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, _KIND_AGENT, agent, verbose=_verbose(ctx))
        r = c.post(f"/memory/delivery/{uid}/install")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))


def delivery_remove(
    ctx: typer.Context,
    agent: str = typer.Argument(..., help="Agent name"),
) -> None:
    """Remove Coffer's session-start hook for an agent."""
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, _KIND_AGENT, agent, verbose=_verbose(ctx))
        r = c.delete(f"/memory/delivery/{uid}")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(_json.dumps(r.json(), indent=2))


def attach(memory_app: typer.Typer) -> None:
    """Register the delivery commands on ``memory_cmd``'s existing typer."""
    memory_app.command("delivery")(delivery_status)
    memory_app.command("delivery-install")(delivery_install)
    memory_app.command("delivery-remove")(delivery_remove)
