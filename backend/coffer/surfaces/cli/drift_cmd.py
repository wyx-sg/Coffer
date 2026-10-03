"""``coffer drift list|repair`` and ``coffer attention`` — the reconciler's
read models on the command line, over the same routes the web UI reads.

- ``drift list`` — ``GET /reconcile/plan``: every difference between what
  Coffer wants in the agents' files and what is there, and what a pass would
  do about it. Computed on request; nothing is written.
- ``drift repair <id>...`` / ``--all`` — ``POST /reconcile/apply``: apply
  differences now, as the person asking. ``--all`` applies every difference a
  person's request would repair. Exits 1 when any item failed.
- ``attention`` — ``GET /attention``: what needs a person across every kind,
  each item with the one route its page uses.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="See and repair drift between Coffer and the agents' own files")
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _plan(
    ctx: typer.Context, *, target: str | None, kind: str | None, uid: str | None, trigger: str
) -> dict[str, Any]:
    params: dict[str, Any] = {"trigger": trigger}
    for key, value in (("target", target), ("kind", kind), ("uid", uid)):
        if value is not None:
            params[key] = value
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/reconcile/plan", params=params)
        _cli_client.check(r, verbose=_verbose(ctx))
    body: dict[str, Any] = r.json()
    return body


def _items_table(title: str, items: list[dict[str, Any]], *, outcome: bool = False) -> Table:
    table = Table(title=title)
    for col in ("ID", "Op", "Policy", "Reason", "File", *(["Outcome"] if outcome else [])):
        table.add_column(col)
    for i in items:
        row = [i["id"], i["op"], i["disposition"], i["reason"], i.get("file") or ""]
        if outcome:
            row.append(i["outcome"] + (f": {i['error']}" if i.get("error") else ""))
        table.add_row(*row)
    return table


@app.command("list")
def list_drift(
    ctx: typer.Context,
    target: str | None = typer.Option(None, "--target", help="One target only"),
    kind: str | None = typer.Option(None, "--kind", help="Only items about this kind"),
    uid: str | None = typer.Option(None, "--uid", help="Only items about this resource"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List every difference a reconcile pass would find now. Writes nothing."""
    body = _plan(ctx, target=target, kind=kind, uid=uid, trigger="period")
    if output_json:
        typer.echo(_json.dumps(body, indent=2))
        return
    for t in body["targets"]:
        if t.get("error"):
            typer.echo(f"{t['name']}: could not be checked — {t['error']}", err=True)
    if not body["items"]:
        typer.echo("No drift: every target matches what Coffer wants.")
        return
    _console.print(_items_table("Drift", body["items"]))


@app.command("repair")
def repair(
    ctx: typer.Context,
    ids: list[str] = typer.Argument(None, help="Item ids from `coffer drift list`"),  # noqa: B008
    repair_all: bool = typer.Option(False, "--all", help="Every item a request would repair"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Apply drift items now. Each repair is audited with you as the actor."""
    wanted = list(ids or [])
    if repair_all:
        plan = _plan(ctx, target=None, kind=None, uid=None, trigger="manual")
        wanted = [i["id"] for i in plan["items"] if i["disposition"] == "repair"]
    if not wanted:
        if repair_all:
            typer.echo("Nothing to repair.")
            return
        typer.echo("name at least one id, or pass --all", err=True)
        raise typer.Exit(int(ExitCode.INVALID_USAGE))
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/reconcile/apply", json={"ids": wanted})
        _cli_client.check(r, verbose=_verbose(ctx))
    body = r.json()
    if output_json:
        typer.echo(_json.dumps(body, indent=2))
    else:
        _console.print(_items_table("Repair", body["items"], outcome=True))
        missing = set(wanted) - {i["id"] for i in body["items"]}
        for gone in sorted(missing):
            typer.echo(f"{gone}: no such difference now", err=True)
    if any(i["outcome"] == "failed" for i in body["items"]) or body["failures"]:
        raise typer.Exit(int(ExitCode.GENERIC))


def attention(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    prompt: str | None = typer.Option(
        None,
        "--prompt",
        metavar="KEY",
        help="Print the hand-off prompt of the item with this key, to give an agent",
    ),
) -> None:
    """What needs you now, across every kind, with the route that acts on each."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/attention")
        _cli_client.check(r, verbose=_verbose(ctx))
    body = r.json()
    if prompt is not None:
        _print_prompt(body, prompt)
        return
    if output_json:
        typer.echo(_json.dumps(body, indent=2))
        return
    for e in body["errors"]:
        typer.echo(f"{e['source']}: could not be read — {e['error']}", err=True)
    if not body["items"]:
        typer.echo("Nothing needs you.")
        return
    table = Table(title="Needs you")
    for col in ("Severity", "Kind", "Title", "Reason", "Action"):
        table.add_column(col)
    for i in body["items"]:
        a = i["action"]
        action = f"{a['verb']}: {a['method']} {a['path']}"
        table.add_row(i["severity"], i["kind"], i["title"], i["reason"], action)
    _console.print(table)
    typer.echo("A prompt to give an agent:")
    for i in body["items"]:
        typer.echo(f"  {i['title']}: coffer attention --prompt {i['key']}")


def _print_prompt(body: dict[str, Any], key: str) -> None:
    """The item's hand-off prompt, exactly as the Overview row offers it."""
    item = next((i for i in (*body["items"], *body["ignored"]) if i["key"] == key), None)
    if item is None:
        typer.echo(f"{key}: nothing needs you under this key now", err=True)
        raise typer.Exit(int(ExitCode.NOT_FOUND))
    typer.echo(item["handoff"]["prompt"])
