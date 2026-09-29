"""``coffer log audit|mcp|daemon|prune`` — the records the Activity page shows.

Each reader goes through the same route the page reads (spec web-ui "Keep the
command-line record readers"): the audit log (``GET /audit``), the MCP
invocation log (``GET /mcp/invocations``, or one server's), and the daemon log
tail (``GET /daemon/logs``), so a terminal sees what the page shows. ``prune``
is the on-demand retention pass (spec resource-framework "Prune each registered
log table on its own retention period").

The audit and MCP readers page by the route's cursor: a page with more after
it ends with the ``--cursor`` value that reads the next one, and ``--json``
prints the route's answer, ``next_cursor`` included.

``--since`` takes an ISO 8601 instant or an age such as ``90s``, ``30m``,
``1h`` or ``2d``, turned into an instant here so every route receives the one
form it accepts.
"""

from __future__ import annotations

import json as _json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

app = typer.Typer(help="Read Coffer's records: the audit log, MCP calls and the daemon log")
_console = Console()

_AGE = re.compile(r"^(\d+)([smhd])$")
_UNIT = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}

_SINCE_HELP = "ISO 8601 instant, or an age such as 30m, 1h, 2d"
_CURSOR_HELP = "Read the page after this one: the next_cursor a previous read printed"


def since_instant(raw: str | None, *, now: datetime | None = None) -> str | None:
    """``raw`` as an ISO 8601 instant; an age counts back from now."""
    if raw is None:
        return None
    age = _AGE.match(raw.strip())
    if age:
        delta = timedelta(**{_UNIT[age.group(2)]: int(age.group(1))})
        return ((now or datetime.now(tz=UTC)) - delta).isoformat()
    try:
        datetime.fromisoformat(raw)
    except ValueError:
        typer.echo(f"--since takes an ISO 8601 instant or an age like 1h, got {raw!r}", err=True)
        raise typer.Exit(2) from None
    return raw


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


@app.command("audit")
def audit(
    ctx: typer.Context,
    kind: str | None = typer.Option(None, "--kind", help="Only this resource kind"),
    name: str | None = typer.Option(None, "--name", help="Only this resource (needs --kind)"),
    event_type: str | None = typer.Option(None, "--event-type", help="Only this event type"),
    since: str | None = typer.Option(None, "--since", help=_SINCE_HELP),
    limit: int = typer.Option(50, "--limit", min=1, max=500, help="Most entries to print"),
    cursor: str | None = typer.Option(None, "--cursor", help=_CURSOR_HELP),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Read the audit log, newest first, one page at a time."""
    verbose = _verbose(ctx)
    if name is not None and kind is None:
        typer.echo("--name needs --kind: a name is only unique within a kind", err=True)
        raise typer.Exit(2)
    params: dict[str, Any] = {"limit": limit}
    if kind is not None:
        params["kind"] = kind
    if event_type is not None:
        params["event_type"] = event_type
    if since is not None:
        params["since"] = since_instant(since)
    if cursor is not None:
        params["cursor"] = cursor
    c, _info = _cli_client.client_or_exit()
    with c:
        if name is not None and kind is not None:
            # The route filters on identity, so a renamed resource's whole
            # trail comes back, rows written under its old name included.
            params["resource_uid"] = resolve_uid(c, kind, name, verbose=verbose)
        r = c.get("/audit", params=params)
        _cli_client.check(r, verbose=verbose)
    body = r.json()
    if output_json:
        # The route's answer as it is: its entries and its next_cursor.
        typer.echo(_json.dumps(body, indent=2))
        return
    entries = body["entries"]
    table = Table(title="Audit log")
    for col in ("Time", "Actor", "Event", "Resource"):
        table.add_column(col)
    for e in entries:
        resource = (
            f"{e['resource_kind']}:{e.get('resource_name') or ''}" if e.get("resource_kind") else ""
        )
        table.add_row(str(e["timestamp"]), e["actor"], e["event_type"], resource)
    _console.print(table)
    _next_page_hint(body.get("next_cursor"))


@app.command("mcp")
def mcp(
    ctx: typer.Context,
    server: str | None = typer.Option(None, "--server", help="One server; omit for every server"),
    status_filter: str | None = typer.Option(None, "--status", help="ok | error"),
    since: str | None = typer.Option(None, "--since", help=_SINCE_HELP),
    limit: int = typer.Option(20, "--limit", min=1, max=500, help="Most calls to print"),
    cursor: str | None = typer.Option(None, "--cursor", help=_CURSOR_HELP),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Read the MCP invocation log, newest first.

    Without --server this is the log the Activity page shows, Coffer's own
    calls (server ``coffer``) and deleted servers' rows (``deleted:<name>``)
    included.
    """
    verbose = _verbose(ctx)
    params: dict[str, Any] = {"limit": limit}
    if status_filter is not None:
        params["status"] = status_filter
    if since is not None:
        params["since"] = since_instant(since)
    if cursor is not None:
        params["cursor"] = cursor
    c, _info = _cli_client.client_or_exit()
    with c:
        if server is None:
            r = c.get("/mcp/invocations", params=params)
        else:
            uid = resolve_uid(c, "mcp_server", server, verbose=verbose)
            r = c.get(f"/resources/mcp_server/{uid}/invocations", params=params)
        _cli_client.check(r, verbose=verbose)
    body = r.json()
    if output_json:
        # The route's answer as it is: its invocations and its next_cursor.
        typer.echo(_json.dumps(body, indent=2))
        return
    rows = body["invocations"]
    table = Table(title=f"{server or 'all servers'} invocations (last {limit})")
    table.add_column("Time")
    if server is None:
        table.add_column("Server")
    for col in ("Type", "Key", "Duration (ms)", "Status"):
        table.add_column(col)
    for inv in rows:
        named = [inv.get("resource_name") or inv["resource_uid"]] if server is None else []
        table.add_row(
            str(inv["timestamp"]),
            *named,
            inv["capability_type"],
            inv["capability_key"],
            str(inv["duration_ms"]),
            inv["status"],
        )
    _console.print(table)
    _next_page_hint(body.get("next_cursor"))


def _next_page_hint(next_cursor: str | None) -> None:
    """End a page that has more after it with the flag that reads the next one."""
    if next_cursor:
        typer.echo(f"More entries follow: add --cursor {next_cursor}")


@app.command("daemon")
def daemon(
    ctx: typer.Context,
    since: str | None = typer.Option(None, "--since", help=_SINCE_HELP),
    errors: bool = typer.Option(False, "--errors", help="Only errors"),
    limit: int = typer.Option(100, "--limit", min=1, max=500, help="Most records to print"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Read the tail of the daemon log, newest first, normalised as the Activity page shows it."""
    params: dict[str, Any] = {"limit": limit, "errors_only": errors}
    if since is not None:
        params["since"] = since_instant(since)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/daemon/logs", params=params)
        _cli_client.check(r, verbose=_verbose(ctx))
    body = r.json()
    if output_json:
        typer.echo(_json.dumps(body, indent=2))
        return
    for rec in body["records"]:
        raw = rec.get("record") or {}
        if "raw" in raw and rec.get("level") is None:
            typer.echo(raw["raw"])
            continue
        head = " ".join(
            str(part)
            for part in (
                rec.get("timestamp"),
                rec.get("level"),
                raw.get("logger"),
                rec.get("event"),
            )
            if part
        )
        typer.echo(head)
        for line in _continuation(raw):
            typer.echo(f"    {line}")


def _continuation(record: dict[str, Any]) -> list[str]:
    """The lines riding with a record — a traceback, a wrapped message."""
    extra = record.get("continuation") or record.get("exception") or []
    if isinstance(extra, str):
        return extra.splitlines()
    return [str(line) for line in extra]


@app.command("prune")
def prune(
    ctx: typer.Context,
    table: str | None = typer.Option(None, "--table", help="Prune only this table"),
) -> None:
    """Prune every registered log table now (or only --table), by its retention period."""
    payload: dict[str, object] = {} if table is None else {"table_name": table}
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/retention/prune", json=payload)
        _cli_client.check(r, verbose=_verbose(ctx))
    result = r.json()["tables"]
    for name, rows in result.items():
        typer.echo(f"pruned {name}: {rows} rows deleted")
    if not result:
        typer.echo("nothing to prune")
