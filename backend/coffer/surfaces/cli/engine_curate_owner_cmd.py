"""``coffer engine curate-owner …`` — the one machine that may curate.

Split out of ``engine_cmd.py`` for the file-size tier, the way ``coffer sync
machine`` is split out of ``sync_cmd.py``. It is the one setting on the
engine's singleton that cannot be read off that singleton alone: the four
states an owner can be in are only visible against the machine REGISTRY, which
is a derived view of the sync working tree rather than DB state, so this
command is the only one in the group that talks to two surfaces.

Curation rewrites a collection's documents unattended. Once a vault spans
machines exactly one may run it — two machines fold the same material into
two DIFFERENT documents, git merges that cleanly because they are
additions at different paths, and the vault silently holds the same knowledge
twice (spec vault-sync ``## Unattended rewriters``). Hence an owner, and hence
these three commands: a binding nobody can see, diagnose or change is a
single-machine outage with no way out short of editing SQLite.
"""

from __future__ import annotations

import json as _json
from datetime import datetime
from typing import Any

import typer

from coffer.domain.internal_engine_config import CurationOwner, GlobalInternalEngineConfig
from coffer.surfaces.cli import _client as _cli_client

curate_owner_app = typer.Typer(help="The one machine allowed to run the curation pass")

#: The engine's settings singleton, and the route the owner is written on.
#: Spelled here rather than imported from ``engine_cmd`` because that module
#: imports this one — the same direction ``sync_cmd`` imports ``sync_machine_cmd``.
_CONFIG = "/internal-engine-config"
_OWNER_ROUTE = f"{_CONFIG}/curation-owner"


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _machine_facts(client: Any, *, verbose: bool) -> tuple[str, list[str]]:
    """This machine's id, and every machine id the registry holds.

    Both come from the sync surface that already publishes them — the same
    reads ``coffer channel bind`` and ``coffer sync machine list`` make — so an
    owner is resolved against exactly what the machines table shows. Neither is
    on the engine's own payload, and deliberately: a settings read must not go
    near git.
    """
    r = client.get("/sync/status")
    _cli_client.check(r, verbose=verbose)
    this_machine = str(r.json()["machine_id"])
    r = client.get("/sync/machines")
    _cli_client.check(r, verbose=verbose)
    known = [str(m["machine_id"]) for m in (r.json().get("machines") or [])]
    return this_machine, known


def _owner_state(owner: str | None, this_machine: str, known: list[str]) -> CurationOwner:
    """The four-state answer, taken from the domain rule and nowhere else.

    The aggregate is rebuilt around the one field its rule reads rather than
    the rule being re-derived here: the carve-out that an EMPTY registry can
    never mean "that machine is gone" is exactly the kind of thing that drifts
    the moment a second surface owns a copy of it, and the install it protects
    — a vault that has never converged — is the commonest one there is. The
    remaining fields are placeholders to satisfy the constructor;
    ``curation_owner`` reads none of them.
    """
    probe = GlobalInternalEngineConfig(
        model=None, updated_at=datetime.min, curate_owner_machine_id=owner
    )
    return probe.curation_owner(this_machine, known)


#: What each state MEANS for the reader in front of this terminal. ``UNKNOWN``
#: gets a sentence rather than an id because it is the only one that is a
#: fault: printing the id alone would read like ``OTHER``, and the difference
#: between "another machine is doing it" and "nobody is doing it" is the whole
#: reason the state exists.
_OWNER_LINE = {
    CurationOwner.UNOWNED: "curation owner: none — the pass runs wherever this vault is read",
    CurationOwner.SELF: "curation owner: {owner} (this machine)",
    CurationOwner.OTHER: "curation owner: {owner} (another machine)",
    CurationOwner.UNKNOWN: (
        "curation owner: {owner} — NO machine in this vault claims that id, "
        "so the pass runs nowhere at all"
    ),
}

#: Printed under the fault, because a state nothing can act on is only half a
#: report. Naming no machine takes the pass back here.
_OWNER_REPAIR = "take it back with 'coffer engine curate-owner set' (no id names this machine)"


def _report(state: CurationOwner, owner: str | None) -> None:
    """One rendering for every command, so ``show`` and ``set`` cannot disagree
    about a fact the user is about to act on."""
    typer.echo(_OWNER_LINE[state].format(owner=owner))
    if state is CurationOwner.UNKNOWN:
        typer.echo(_OWNER_REPAIR)


@curate_owner_app.command("show")
def curate_owner_show(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print which machine may run the curation pass, and what that means here.

    The state, not just the id: an owner naming a machine that has since been
    retired stops curation on EVERY machine, and printing its id the way an
    ordinary remote owner is printed would hide exactly that.
    """
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(_CONFIG)
        _cli_client.check(r, verbose=verbose)
        owner = r.json()["curate_owner_machine_id"]
        this_machine, known = _machine_facts(c, verbose=verbose)
    state = _owner_state(owner, this_machine, known)
    if output_json:
        typer.echo(
            _json.dumps(
                {
                    "curate_owner_machine_id": owner,
                    "state": state.value,
                    "this_machine_id": this_machine,
                },
                indent=2,
            )
        )
        return
    _report(state, owner)


@curate_owner_app.command("set")
def curate_owner_set(
    ctx: typer.Context,
    machine_id: str | None = typer.Argument(
        None, help="machine_id that should own curation (default: this machine)"
    ),
) -> None:
    """Name the one machine allowed to run the curation pass.

    Argued like ``coffer channel bind``, and for the same reason: the answer is
    almost always "the machine I am typing on", so naming none means this one.
    An id nobody claims is still written — a vault that has never converged has
    no registry to check it against, and that is the one install where checking
    would refuse the only correct answer — but the result is read back as the
    fault it is rather than reported as a success.
    """
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        this_machine, known = _machine_facts(c, verbose=verbose)
        r = c.put(_OWNER_ROUTE, json={"machine_id": machine_id or this_machine})
        _cli_client.check(r, verbose=verbose)
        owner = r.json()["curate_owner_machine_id"]
    _report(_owner_state(owner, this_machine, known), owner)


@curate_owner_app.command("clear")
def curate_owner_clear(ctx: typer.Context) -> None:
    """Stop naming an owner, so curation runs wherever this setting is read.

    Right for a vault down to one machine, wrong for one that still spans
    several — which is why it is something the operator asks for and never a
    repair anything performs on its own.
    """
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put(_OWNER_ROUTE, json={"machine_id": None})
        _cli_client.check(r, verbose=_verbose(ctx))
    _report(CurationOwner.UNOWNED, None)
