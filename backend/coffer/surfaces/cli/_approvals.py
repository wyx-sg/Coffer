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
REFUSED = "refused in the Coffer app, and nothing waits"
#: How long ``--wait`` waits before giving up, and how often it asks.
WAIT_SECONDS = 600.0
POLL_SECONDS = 2.0

WAIT_OPTION = typer.Option(
    False, "--wait", help="Wait for approval in the Coffer app instead of exiting"
)


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
    refused = [a for a in approvals if a.get("status") == "rejected"]
    approvals = [a for a in approvals if a.get("status") != "rejected"]
    for a in refused:
        typer.echo(
            f"{REFUSED}: {a.get('description', a['id'])} (approval {a['id']}); "
            "it stays refused until the destination changes",
            err=True,
        )
    if refused and not approvals:
        raise typer.Exit(int(ExitCode.CONFLICT))
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
