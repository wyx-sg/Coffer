"""``coffer workflow approvals|approve|reject`` — deciding what a run may write.

Split out of ``workflow_cmd`` for the file-size cap, but the seam is a real one:
these three commands are the only place a person decides whether something
reaches a system outside this machine, and they are the terminal half of the
gate in ``docs/decisions/workflow-gates-tool-calls.md``.

They attach to the ``workflow`` group itself rather than to a sub-group, because
``coffer workflow approve <id>`` is what someone reaches for when a notification
says something is waiting — not ``coffer workflow approval approve <id>``. That
is why this module exposes ``register(app)`` instead of a Typer app of its own.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer

from coffer.surfaces.cli import _client as _cli_client


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


def list_approvals(
    ctx: typer.Context,
    run_id: str | None = typer.Option(None, "--run"),
    status: str = typer.Option("pending", "--status"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """What is waiting on you."""
    params: dict[str, str] = {"status": status}
    if run_id:
        params["run_id"] = run_id
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/workflow/approvals", params=params)
        _cli_client.check(r, verbose=_verbose(ctx))
        payload: dict[str, Any] = r.json()
    if output_json:
        typer.echo(_json.dumps(payload, indent=2))
        return
    items = payload.get("items", [])
    if not items:
        typer.echo("nothing waiting")
        return
    for item in items:
        typer.echo(f"{item['id']}  {item.get('tool_name') or item['kind']}  {item['status']}")
        # The arguments verbatim: a decision on a summary is not a decision.
        typer.echo(_json.dumps(item["payload"], indent=2))
        typer.echo(f"  expires {item['expires_at']}")


def _decide(ctx: typer.Context, approval_id: str, decision: str, comment: str | None) -> None:
    body: dict[str, Any] = {"decision": decision}
    if comment:
        body["comment"] = comment
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/workflow/approvals/{approval_id}/decision", json=body)
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"{approval_id}: {decision}")


def approve(
    ctx: typer.Context,
    approval_id: str = typer.Argument(...),
    comment: str | None = typer.Option(None, "--comment", "-m"),
) -> None:
    """Let the held call through. Read the arguments first."""
    _decide(ctx, approval_id, "approved", comment)


def reject(
    ctx: typer.Context,
    approval_id: str = typer.Argument(...),
    comment: str | None = typer.Option(None, "--comment", "-m", help="Why — the node acts on it"),
) -> None:
    """Refuse the held call. The node is told, with your reason."""
    _decide(ctx, approval_id, "rejected", comment)


def register(app: typer.Typer) -> None:
    """Attach the three commands to the ``workflow`` group."""
    app.command("approvals")(list_approvals)
    app.command("approve")(approve)
    app.command("reject")(reject)
