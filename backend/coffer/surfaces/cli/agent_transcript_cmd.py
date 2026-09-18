"""``coffer agent transcripts`` / ``transcript`` — an agent's local conversations.

CLI parity for the web Conversations tab, which has two surfaces and so does
this: ``transcripts`` lists the sessions (``GET /agents/{uid}/transcripts``) and
``transcript`` renders one of them (``.../transcripts/session``), taking the
absolute ``source_path`` the listing printed. Read-only, both of them.

Its own module (rather than more lines in ``agent_cmd.py``) so both stay under
the backend file-size cap; ``agent_cmd`` calls :func:`attach` so the user-facing
tree stays ``coffer agent transcripts`` / ``coffer agent transcript``.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._resolve import resolve_uid

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
        uid = resolve_uid(c, "agent", name, verbose=_verbose(ctx))
        r = c.get(f"/agents/{uid}/transcripts", params=params)
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


def transcript(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Agent name"),
    path: str = typer.Option(..., "--path", help="Absolute source_path from `transcripts`."),
    limit: int = typer.Option(200, "--limit", help="Max turns to show (1-500)."),
    offset: int = typer.Option(0, "--offset", help="Skip this many turns."),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Print one conversation: its turns, secret-scrubbed and bounded.

    A transcript can be tens of megabytes, so what comes back is a window —
    ``limit`` turns from ``offset``, each cut at the server's per-turn cap. The
    header says how many turns the file holds in total, so a short output is
    never mistaken for a short conversation.
    """
    params: dict[str, Any] = {"path": path, "limit": limit, "offset": offset}
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_uid(c, "agent", name, verbose=_verbose(ctx))
        r = c.get(f"/agents/{uid}/transcripts/session", params=params)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    shown = len(data["messages"])
    header = data.get("title") or data["session_id"]
    _console.print(f"[bold]{header}[/bold]")
    _console.print(
        f"{data['project_path'] or ''}  —  turns {data['offset'] + 1}"
        f"-{data['offset'] + shown} of {data['message_count']}"
    )
    for message in data["messages"]:
        _console.print(f"\n[bold]{message['role']}[/bold] {_short_time(message.get('timestamp'))}")
        _console.print(message["text"])
        if message.get("truncated"):
            _console.print("[dim](turn truncated)[/dim]")


def attach(agent_app: typer.Typer) -> None:
    """Register the transcript commands on agent_cmd's existing typer."""
    agent_app.command("transcripts")(transcripts)
    agent_app.command("transcript")(transcript)
