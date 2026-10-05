"""``coffer approval`` — secret approvals: list, show, approve with Touch ID, reject.

Spec secret "Approve from the command line with the person's own presence
check". ``approve`` asks the desktop app to run the operating system's presence
check (Touch ID or the login password) for exactly the approvals named, each
pinned to the target it names now; the person confirms in the system prompt,
and the command reports each approval's state as the daemon then holds it.
There is no flag that skips the check: a cancelled, failed, timed-out or
unavailable check leaves every approval pending. Refusing needs nobody.
"""

from __future__ import annotations

from typing import Any

import typer

from coffer.surfaces.cli import _desktop, _io
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli.groups import group
from coffer.surfaces.cli.registry import maps

approvals = group("approval")
_BASE = "/secrets/approvals"
_UI = "Secrets · approvals · "


def _rows(value: Any) -> None:
    _io.table(
        [
            {
                "id": a["id"],
                "status": a["status"],
                "secret": a.get("ref"),
                "to": a.get("destination_label"),
                "what": a["description"],
            }
            for a in (value.get("approvals") if isinstance(value, dict) else value) or []
        ],
        ["id", "status", "secret", "to", "what"],
    )


@approvals.command("list")
@maps("approval list", ("GET", _BASE), ui=_UI + "list (Secrets page, Overview)")
def list_approvals(
    status: str | None = typer.Option(
        "pending", "--status", help="pending, approved, rejected, superseded, or all"
    ),
    destination: str | None = typer.Option(None, "--destination", help="A destination's uid"),
    as_json: bool = _io.json_option(),
) -> None:
    """Approvals, newest first (pending ones by default)."""
    params = {"status": None if status == "all" else status, "destination_uid": destination}
    _io.emit(_io.call("GET", _BASE, as_json=as_json, params=params), as_json=as_json, human=_rows)


@approvals.command("show")
@maps("approval show", ("GET", _BASE + "/{approval_id}"), ui=_UI + "open one")
def show(approval_id: str = typer.Argument(...), as_json: bool = _io.json_option()) -> None:
    """One approval: what it sends, to which destination and target, and its state."""
    _io.emit(_io.call("GET", f"{_BASE}/{approval_id}", as_json=as_json), as_json=as_json)


@approvals.command("approve")
@maps(
    "approval approve",
    ("POST", "/desktop/requests"),
    ("GET", "/desktop/requests/{request_id}"),
    ("POST", _BASE + "/{approval_id}/approve"),
    ("POST", _BASE + "/approve"),
    ui=_UI + "Approve (desktop app, after Touch ID or the login password)",
)
def approve(
    approval_ids: list[str] = typer.Argument(..., help="The approvals to approve — exactly these"),
    timeout: float = typer.Option(120.0, "--timeout", help="Seconds to wait for the person"),
    no_launch: bool = typer.Option(False, "--no-launch", help="Do not start the desktop app"),
    as_json: bool = _io.json_option(),
) -> None:
    """Approve with the person's own presence check, in the desktop app.

    The system prompt names each action, secret, destination and environment;
    the approvals are applied only after it passes, and only while each still
    names the target it named when asked. Exit 0 when every one is approved,
    11 when the person did not confirm (cancelled, failed or timed out — they
    stay pending), 12 when the desktop app is not available.
    """
    ids = list(dict.fromkeys(approval_ids))
    request = _desktop.run(
        {"op": "approve", "approval_ids": ids},
        as_json=as_json,
        timeout=timeout,
        launch=not no_launch,
    )
    after = [_io.call("GET", f"{_BASE}/{i}", as_json=as_json) for i in ids]
    result = {
        "request": {"status": request["status"], "message": request.get("message")},
        "approvals": [
            {"id": a["id"], "status": a["status"], "description": a["description"]} for a in after
        ],
    }

    def human(r: dict[str, Any]) -> None:
        for a in r["approvals"]:
            typer.echo(f"{a['id']}: {a['status']} — {a['description']}")
        if r["request"]["status"] != "done":
            typer.echo(
                f"not confirmed: {r['request']['message'] or r['request']['status']}", err=True
            )

    _io.emit(result, as_json=as_json, human=human)
    if any(a["status"] != "approved" for a in after):
        raise typer.Exit(int(ExitCode.PRESENCE_NOT_CONFIRMED))


@approvals.command("reject")
@maps(
    "approval reject",
    ("POST", _BASE + "/{approval_id}/reject"),
    ("POST", _BASE + "/reject"),
    ui=_UI + "Reject",
)
def reject(
    approval_ids: list[str] = typer.Argument(..., help="The approvals to refuse"),
    as_json: bool = _io.json_option(),
) -> None:
    """Refuse approvals. Needs no presence check: refusing only narrows."""
    ids = list(dict.fromkeys(approval_ids))
    if len(ids) == 1:
        answer = _io.call("POST", f"{_BASE}/{ids[0]}/reject", as_json=as_json)
        _io.emit(answer, as_json=as_json, human=lambda a: typer.echo(f"{a['id']}: {a['status']}"))
        return
    answer = _io.call("POST", _BASE + "/reject", as_json=as_json, body={"ids": ids})

    def human(r: dict[str, Any]) -> None:
        for item in r["results"]:
            typer.echo(
                f"{item['id']}: {item['outcome']}"
                + (f" ({item['reason']})" if item.get("reason") else "")
            )

    _io.emit(answer, as_json=as_json, human=human)


__all__ = ["approvals"]
