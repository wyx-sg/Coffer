"""``coffer usage`` — metered API-key usage and official subscription quota.

Every reader goes through the route the Usage page reads (``/usage/summary``,
``/usage/requests``, ``/usage/export.csv``, ``/usage/quota``), so a terminal
sees what the page shows. Costs are estimates from the price version stored
with each request, and are labelled so.

``coffer usage statusline -- <command…>`` is the OPT-IN Claude Code statusLine
wrapper (ADR usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-
quota). Claude Code runs it with the statusLine JSON on stdin; it forwards that
JSON's documented ``rate_limits`` to the daemon — with a one-second timeout,
never spawning a daemon, every error ignored — and then runs the user's
original statusLine command with the same stdin, printing its output and
exiting with its code. The original runs even when the daemon is down; with no
original command the wrapper prints nothing. Coffer never installs it by
itself: the user points ``statusLine.command`` at it.
"""

from __future__ import annotations

import json as _json
import subprocess
import sys
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(
    help="Model usage through Coffer's proxy, and subscription quota",
    invoke_without_command=True,
)
_console = Console()

#: The statusline forward's whole budget: a statusline must never wait on Coffer.
STATUSLINE_FORWARD_TIMEOUT = 1.0


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
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
    output_csv: bool = typer.Option(False, "--csv", help="CSV output"),
) -> None:
    """Show token usage and estimated cost over a range."""
    if ctx.invoked_subcommand is not None:
        return
    verbose = _verbose(ctx)
    params = _range_params(range_name, start, end, group_by)
    c, _info = _cli_client.client_or_exit()
    with c:
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


@app.command("quota")
def quota(
    ctx: typer.Context,
    refresh: bool = typer.Option(False, "--refresh", help="Read Codex's windows now"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Show each subscription agent's official remaining quota."""
    verbose = _verbose(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/usage/quota/refresh") if refresh else c.get("/usage/quota")
        _cli_client.check(r, verbose=verbose)
    body = r.json()
    if output_json:
        typer.echo(_json.dumps(body, indent=2))
        return
    for agent in body["agents"]:
        if not agent["windows"]:
            typer.echo(f"{agent['agent_type']}: no official value seen yet")
            continue
        typer.echo(f"{agent['agent_type']}" + (f" ({agent['plan']})" if agent["plan"] else ""))
        for w in agent["windows"]:
            if w["used_percent"] is None:
                typer.echo(f"  {w['label']}: reset since last seen (as of {w['as_of']})")
                continue
            resets = f", resets {w['resets_at']}" if w["resets_at"] else ""
            typer.echo(
                f"  {w['label']}: {w['used_percent']:.0f}% used{resets} (as of {w['as_of']})"
            )


def forward_statusline(stdin: bytes) -> None:
    """Send the statusLine JSON's ``rate_limits`` to a RUNNING daemon.

    Never spawns one (``discover`` only reads daemon.json), gives up after
    :data:`STATUSLINE_FORWARD_TIMEOUT`, and swallows every error.
    """
    try:
        payload = _json.loads(stdin.decode("utf-8") or "{}")
        rate_limits = payload.get("rate_limits") if isinstance(payload, dict) else None
        if not isinstance(rate_limits, dict) or not rate_limits:
            return
        info = _cli_client.discover()
        if info is None:
            return
        httpx.post(
            f"http://127.0.0.1:{info.port}/api/v1/usage/quota/statusline",
            json={"rate_limits": rate_limits},
            headers={"X-Coffer-Token": info.token},
            timeout=STATUSLINE_FORWARD_TIMEOUT,
        )
    except Exception:
        return


def run_original(command: list[str], stdin: bytes) -> int:
    """Run the user's original statusLine command with the same stdin.

    One argument is a shell command line (what ``statusLine.command`` holds);
    several are an argv. Its stdout is printed as ours; its stderr passes through.
    """
    if not command:
        return 0
    try:
        if len(command) == 1:
            done = subprocess.run(
                command[0], input=stdin, shell=True, stdout=subprocess.PIPE, check=False
            )
        else:
            done = subprocess.run(command, input=stdin, stdout=subprocess.PIPE, check=False)
    except OSError as exc:
        print(f"coffer usage statusline: {exc}", file=sys.stderr)
        return 127
    typer.echo(done.stdout.decode("utf-8", "replace"), nl=False)
    return done.returncode


@app.command(
    "statusline",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def statusline(
    command: list[str] | None = typer.Argument(  # noqa: B008
        None, help="The original statusLine command to run after forwarding"
    ),
) -> None:
    """Opt-in Claude Code statusLine wrapper: forward rate limits, then chain."""
    stdin = sys.stdin.buffer.read() if not sys.stdin.isatty() else b""
    forward_statusline(stdin)
    code = run_original(list(command or []), stdin)
    raise typer.Exit(code)


__all__ = ["app", "forward_statusline", "run_original"]
