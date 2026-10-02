"""The machine a channel is bound to, as ``coffer channel`` reports and sets it.

Split out of ``channel_cmd`` for its size budget and because both halves answer
one question — which machine is this — from the same two daemon surfaces.
"""

from __future__ import annotations

from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client

__all__ = ["binding_label", "handover_warning", "known_machines", "this_machine_id"]


def this_machine_id(client: Any, *, verbose: bool) -> str:
    """This daemon's machine id, from the surface that already publishes it.

    The CLI cannot derive it: the id is read from the host by the daemon and
    cached beside the database, and a CLI deriving its own would be a second
    answer to an identity question that must have exactly one. Read off the
    daemon's status rather than the sync surface: a channel is bound to a
    machine whether or not the vault syncs with anything.
    """
    r = client.get("/daemon/status")
    _cli_client.check(r, verbose=verbose)
    machine_id = _cli_client.status_machine_id(r.json())
    if not machine_id:
        typer.echo("the daemon has not derived this machine's id yet — try again", err=True)
        raise typer.Exit(1)
    return str(machine_id)


def known_machines(client: Any, *, verbose: bool) -> list[str]:
    """Every machine id the registry holds, or ``[]`` when there is no registry
    to judge a binding against (a vault that has never converged lists only this
    machine, and an id absent from a registry of one is not a fault)."""
    r = client.get("/sync/machines")
    if r.status_code != 200:
        return []  # no registry to read — a binding cannot be judged against one
    ids = [str(m["machine_id"]) for m in (r.json().get("machines") or [])]
    return ids if len(ids) > 1 else []


def handover_warning(current: str | None, target: str, *, here: str) -> str | None:
    """What rebinding costs when the channel is moved TO this machine while another
    still holds it (spec channels "Bind each channel to the one machine that runs
    it"): both adapters can be live until the old machine sees the change, which is
    bounded by its sync interval. ``None`` when there is no such window."""
    if not current or current == target or target != here:
        return None
    return (
        f"warning: machine {current} still holds this channel; until it syncs this "
        "change both machines may answer the bot. Rebinding from the machine that "
        "holds it has no overlap."
    )


def binding_label(binding: str, *, runs_here: bool, known: list[str]) -> str:
    """``<id> (this machine)``, ``(another machine)``, or — spec channels "Bind
    each channel to the one machine that runs it" — a fault when the registry
    does not hold the machine the channel names, which is somebody's mistake and
    not the normal state of a channel bound elsewhere."""
    if runs_here:
        where = "this machine"
    elif known and binding not in known:
        where = "UNKNOWN MACHINE — no machine in this vault has that id, so it runs nowhere"
    else:
        where = "another machine"
    return f"{binding} ({where})"
