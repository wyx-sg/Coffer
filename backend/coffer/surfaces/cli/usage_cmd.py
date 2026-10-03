"""``coffer usage`` — metered API-key usage.

Every reader goes through the route the Usage page reads (``/usage/summary``,
``/usage/requests``, ``/usage/export.csv``), so a terminal
sees what the page shows. Costs are estimates from the price version stored
with each request, and are labelled so.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

app = typer.Typer(
    help="Model usage through Coffer's proxy",
    invoke_without_command=True,
)
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _range_params(
    range_name: str, start: str | None, end: str | None, group_by: str
) -> dict[str, Any]:
    params: dict[str, Any] = {"range": range_name, "group_by": group_by}
    if start is not None:
        params["from"] = start
    if end is not None:
        params["to"] = end
    return params


def _label(row: dict[str, Any], group_by: str) -> str:
    if group_by == "model":
        model = row.get("model") or "(unknown model)"
        via = row.get("connection_name") or row.get("connection_uid")
        return f"{model} via {via}" if via else model
    if group_by == "agent":
        return row.get("agent_uid") or row.get("agent_type") or "(unknown agent)"
    return str(row.get("day") or row.get("key"))


#: What a cost reads as when nothing in it has a price: a dash, never $0.
NO_PRICE = "—"


def _cost(totals: dict[str, Any]) -> str:
    unpriced = totals.get("unpriced_requests") or 0
    if unpriced and unpriced >= (totals.get("requests") or 0):
        # Nothing here was priced (Coffer bundles Anthropic's rates only; a
        # price for another vendor's model is set on its connection).
        return f"{NO_PRICE} ({unpriced} unpriced)"
    cost = f"~${totals['estimated_cost_usd']:.4f}"
    if unpriced:
        cost += f" (+{unpriced} unpriced)"
    return cost


@app.callback()
def summary(
    ctx: typer.Context,
    range_name: str = typer.Option("today", "--range", help="today | 7d | 30d | month | custom"),
    start: str | None = typer.Option(None, "--from", help="First day of a custom range"),
    end: str | None = typer.Option(None, "--to", help="Last day of a custom range, inclusive"),
    group_by: str = typer.Option("model", "--by", help="model | agent | day"),
    agent_type: str | None = typer.Option(
        None, "--agent", help="Only requests this agent type sent (claude_code | codex)"
    ),
    provider: str | None = typer.Option(
        None, "--provider", help="Only requests this provider (by name) served"
    ),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    output_csv: bool = typer.Option(False, "--csv", help="CSV output"),
) -> None:
    """Show token usage and estimated cost over a range."""
    if ctx.invoked_subcommand is not None:
        return
    verbose = _verbose(ctx)
    params = _range_params(range_name, start, end, group_by)
    if agent_type is not None:
        params["agent_type"] = agent_type
    c, _info = _cli_client.client_or_exit()
    with c:
        if provider is not None:
            params["connection_uid"] = resolve_uid(c, "provider", provider, verbose=verbose)
        r = c.get("/usage/export.csv" if output_csv else "/usage/summary", params=params)
        _cli_client.check(r, verbose=verbose)
    if output_csv:
        typer.echo(r.text, nl=False)
        return
    body = r.json()
    if output_json:
        typer.echo(_json.dumps(body, indent=2))
        return
    table = Table(title=f"Usage {body['start']} … {body['end']} (costs are estimates)")
    for col in ("Group", "Requests", "Input", "Cache write", "Cache read", "Output", "Cost"):
        table.add_column(col)
    for row in [*body["rows"], {"key": "Total", "totals": body["totals"], "day": "Total"}]:
        t = row["totals"]
        name = "Total" if row["key"] == "Total" else _label(row, group_by)
        requests = str(t["requests"])
        if t["unknown_usage_requests"]:
            requests += f" ({t['unknown_usage_requests']} unknown)"
        table.add_row(
            name,
            requests,
            str(t["input_tokens"]),
            str(t["cache_write_5m_tokens"] + t["cache_write_1h_tokens"]),
            str(t["cache_read_tokens"]),
            str(t["output_tokens"]),
            _cost(t),
        )
    _console.print(table)


@app.command("requests")
def requests(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", min=1, max=500, help="Most requests to print"),
    cursor: str | None = typer.Option(None, "--cursor", help="The next_cursor a read printed"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List recent metered requests, newest first."""
    verbose = _verbose(ctx)
    params: dict[str, Any] = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/usage/requests", params=params)
        _cli_client.check(r, verbose=verbose)
    body = r.json()
    if output_json:
        typer.echo(_json.dumps(body, indent=2))
        return
    table = Table(title="Metered requests")
    for col in ("Time", "Agent", "Model", "Outcome", "In", "Out", "Cost"):
        table.add_column(col)
    for e in body["requests"]:
        cost = e["estimated_cost_usd"]
        table.add_row(
            str(e["started_at"]),
            e.get("agent_type") or "",
            e.get("model") or "",
            e["outcome"],
            "?" if not e["usage_known"] else str(e.get("input_tokens") or 0),
            "?" if not e["usage_known"] else str(e.get("output_tokens") or 0),
            NO_PRICE if e["unpriced"] else ("" if cost is None else f"~${cost:.4f}"),
        )
    _console.print(table)
    if body.get("next_cursor"):
        typer.echo(f"more: coffer usage requests --cursor {body['next_cursor']}")


__all__ = ["app"]
