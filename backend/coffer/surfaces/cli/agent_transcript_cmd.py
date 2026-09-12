"""``coffer agent transcripts <name>`` — browse an agent's local conversations.

CLI parity for the web Conversations tab: a thin HTTP shell over
``GET /agents/{name}/transcripts``. Read-only. Its own module (rather than more
lines in ``agent_cmd.py``) so both stay under the backend file-size cap;
``agent_cmd`` calls :func:`attach` so the user-facing tree stays
``coffer agent transcripts``.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _short_time(value: str | None) -> str:
    """ISO instant → ``YYYY-MM-DD HH:MM`` for the table; blank when absent."""
    if not value:
        return ""
    return value.replace("T", " ")[:16]


def transcripts(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    limit: int = typer.Option(20, "--limit", help="Max sessions to show (1-500)."),
    offset: int = typer.Option(0, "--offset", help="Skip this many sessions."),
    query: str | None = typer.Option(None, "--query", "-q", help="Search title or project path."),
    sort: str = typer.Option(
        "last_activity_at", "--sort", help="started_at | last_activity_at | message_count"
    ),
    order: str = typer.Option("desc", "--order", help="asc | desc"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List the conversations this agent has recorded on this machine."""
    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "sort": sort,
        "order": order,
    }
    if query:
        params["q"] = query
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}/transcripts", params=params)
        if r.status_code == 404:
            typer.echo(r.json().get("error", {}).get("message", "not found"), err=True)
            raise typer.Exit(4)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    sessions = data["sessions"]
    table = Table(title=f"Conversations — {name} ({len(sessions)} of {data['total']})")
    for col in ("Title", "Project", "Messages", "Started", "Last activity"):
        table.add_column(col)
    for s in sessions:
        table.add_row(
            s.get("title") or s["session_id"],
            s.get("project_path") or "",
            str(s["message_count"]),
            _short_time(s.get("started_at")),
            _short_time(s.get("last_activity_at")),
        )
    _console.print(table)


def attach(agent_app: typer.Typer) -> None:
    """Register the transcript commands on agent_cmd's existing typer."""
    agent_app.command("transcripts")(transcripts)
