"""What the CLI says, and does, when a change waits for the Coffer app.

Spec secret "Hold a secret for a new destination until a person approves
it": a secret bound to a new destination, a replaced value that is in use, or
switching the protection off is saved as a pending approval. Approving takes a
present human in the desktop app — Touch ID or the login password — which no
terminal can supply. So the CLI names what waits, prints "waiting for approval
in the Coffer app", and exits ``APPROVAL_PENDING`` (9); with ``--wait`` it
polls until the person answers.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import typer

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode

WAITING = "waiting for approval in the Coffer app"
#: How long ``--wait`` waits before giving up, and how often it asks.
WAIT_SECONDS = 600.0
POLL_SECONDS = 2.0

WAIT_OPTION = typer.Option(
    False, "--wait", help="Wait for approval in the Coffer app instead of exiting"
)


def pending_for(
    c: httpx.Client, uid: str, *, verbose: bool, refs: list[str] | tuple[str, ...] = ()
) -> list[dict[str, Any]]:
    """The approvals a destination waits on right now.

    That is every pending binding of a secret to ``uid``, and — for each of
    ``refs``, the secrets the destination cites — a pending replacement of the
    value: a new key for a secret in use is held against the secret, not
    against any one destination, so it is found by its ref.
    """
    if not refs:
        r = c.get("/secrets/approvals", params={"status": "pending", "destination_uid": uid})
    else:
        r = c.get("/secrets/approvals", params={"status": "pending"})
    _cli_client.check(r, verbose=verbose)
    rows = list(r.json().get("approvals", []))
    if not refs:
        return rows
    wanted = set(refs)
    return [
        a
        for a in rows
        if a.get("destination_uid") == uid
        or (a.get("op") == "replace_value" and a.get("ref") in wanted)
    ]


def pending_ids(r: httpx.Response) -> list[str]:
    """The approval ids a ``SECRET_BINDING_PENDING`` refusal names, else []."""
    try:
        error = r.json().get("error") or {}
    except ValueError:
        return []
    if error.get("code") != "SECRET_BINDING_PENDING":
        return []
    return list((error.get("details") or {}).get("approval_ids") or [])


def settle(
    c: httpx.Client,
    approvals: list[dict[str, Any]],
    *,
    wait: bool,
    verbose: bool,
) -> None:
    """Report what waits; exit 9, or wait for the person when ``wait``."""
    if not approvals:
        return
    for a in approvals:
        typer.echo(f"{WAITING}: {a.get('description', a['id'])} (approval {a['id']})", err=True)
    if not wait:
        raise typer.Exit(int(ExitCode.APPROVAL_PENDING))
    deadline = time.monotonic() + WAIT_SECONDS
    remaining = {a["id"] for a in approvals}
    while remaining:
        if time.monotonic() > deadline:
            typer.echo("gave up waiting; the approval is still in the Coffer app", err=True)
            raise typer.Exit(int(ExitCode.APPROVAL_PENDING))
        time.sleep(POLL_SECONDS)
        for approval_id in sorted(remaining):
            r = c.get(f"/secrets/approvals/{approval_id}")
            _cli_client.check(r, verbose=verbose)
            status = r.json()["status"]
            if status == "approved":
                remaining.discard(approval_id)
            elif status != "pending":
                typer.echo(f"approval {approval_id} was {status}", err=True)
                raise typer.Exit(int(ExitCode.CONFLICT))
    typer.echo("approved in the Coffer app", err=True)


def settle_ids(c: httpx.Client, ids: list[str], *, wait: bool, verbose: bool) -> None:
    approvals = []
    for approval_id in ids:
        r = c.get(f"/secrets/approvals/{approval_id}")
        _cli_client.check(r, verbose=verbose)
        approvals.append(r.json())
    settle(c, approvals, wait=wait, verbose=verbose)
