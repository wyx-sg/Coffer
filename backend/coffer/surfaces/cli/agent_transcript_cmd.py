"""``coffer agent transcript <name> [<id>]`` — an agent's local conversations.

CLI parity for the web Conversations tab, which has two surfaces and so does
this one command: without an id it lists the sessions
(``GET /agents/{uid}/transcripts``), with one it renders that session
(``.../transcripts/session``) in a bounded window of turns. Read-only.

The id is the ``session_id`` the listing printed; the session route is keyed by
the file's ``source_path``, so the command finds the session in the listing
first. An id the listing does not know is handed to the route as it is (an
absolute ``source_path`` works that way too), and the route's own not-found
answer is what the user sees.

Its own module (rather than more lines in ``agent_cmd.py``) so both stay under
the backend file-size cap; ``agent_cmd`` calls :func:`attach`.
"""

from __future__ import annotations

import json as _json
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import verbose_of
from coffer.surfaces.cli._resolve import resolve_ref

_console = Console()
#: The listing route's page ceiling, used when looking an id up.
_PAGE = 500


def _short_time(value: str | None) -> str:
    """ISO instant → ``YYYY-MM-DD HH:MM`` for the table; blank when absent."""
    if not value:
        return ""
    return value.replace("T", " ")[:16]


def transcript(
    ctx: typer.Context,
    name: str = typer.Argument(..., metavar="NAME", help="Agent name or uid"),
    session_id: str | None = typer.Argument(
        None, metavar="[ID]", help="A session id from the listing; omit to list sessions"
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Sessions to list (default 20) or turns to show (default 200)"
    ),
    offset: int = typer.Option(0, "--offset", help="With an ID: skip this many turns."),
    cursor: str | None = typer.Option(
        None, "--cursor", help="Listing: read the page after the one that printed this cursor."
    ),
    query: str | None = typer.Option(None, "--query", "-q", help="Search title or project path."),
    project: str | None = typer.Option(None, "--project", help="Only this exact project path."),
    sort: str | None = typer.Option(
        None, "--sort", help="started_at | last_activity_at (default) | message_count"
    ),
    order: str | None = typer.Option(None, "--order", help="asc | desc (default)"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List this agent's conversations on this machine, or print one of them.

    The listing pages by cursor: a page with more after it ends with the
    --cursor value that reads the next one. With an ID, what comes back is a
    window — --limit turns from --offset, each cut at the server's per-turn cap
    and secret-scrubbed — and the header says how many turns the whole session
    holds.
    """
    verbose = verbose_of(ctx)
    listing_only = {
        "--query": query,
        "--project": project,
        "--sort": sort,
        "--order": order,
        "--cursor": cursor,
    }
    if session_id is not None and any(v is not None for v in listing_only.values()):
        used = ", ".join(k for k, v in listing_only.items() if v is not None)
        typer.echo(f"{used} only apply to the listing (no ID)", err=True)
        raise typer.Exit(2)
    if session_id is None and offset:
        typer.echo(
            "--offset only applies to one session (with an ID); the listing takes --cursor",
            err=True,
        )
        raise typer.Exit(2)
    c, _info = _cli_client.client_or_exit()
    with c:
        uid = resolve_ref(c, "agent", name, verbose=verbose)["uid"]
        if session_id is None:
            params: dict[str, Any] = {
                "limit": limit or 20,
                "sort": sort or "last_activity_at",
                "order": order or "desc",
            }
            if query:
                params["q"] = query
            if project:
                params["project"] = project
            if cursor:
                params["cursor"] = cursor
            r = c.get(f"/agents/{uid}/transcripts", params=params)
            _cli_client.check(r, verbose=verbose)
            _print_listing(name, r.json(), output_json)
            return
        path = _source_path(c, uid, session_id, verbose=verbose)
        r = c.get(
            f"/agents/{uid}/transcripts/session",
            params={"path": path, "limit": limit or 200, "offset": offset},
        )
        _cli_client.check(r, verbose=verbose)
    _print_session(r.json(), output_json)


def _source_path(c: httpx.Client, uid: str, session_id: str, *, verbose: bool) -> str:
    """The ``source_path`` of the listed session called ``session_id``, or the id
    itself when no listed session carries it (the route then answers)."""
    params: dict[str, Any] = {"limit": _PAGE}
    while True:
        r = c.get(f"/agents/{uid}/transcripts", params=params)
        _cli_client.check(r, verbose=verbose)
        page = r.json()
        for s in page["sessions"]:
            if s["session_id"] == session_id:
                return str(s["source_path"])
        if not page.get("next_cursor"):
            return session_id
        params["cursor"] = page["next_cursor"]


def _print_listing(name: str, data: dict[str, Any], output_json: bool) -> None:
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    sessions = data["sessions"]
    table = Table(title=f"Conversations — {name} ({len(sessions)} of {data['total']})")
    for col in ("ID", "Title", "Project", "Messages", "Last activity"):
        table.add_column(col)
    for s in sessions:
        table.add_row(
            s["session_id"],
            s.get("title") or "",
            s.get("project_path") or "",
            str(s["message_count"]),
            _short_time(s.get("last_activity_at")),
        )
    _console.print(table)
    if data.get("next_cursor"):
        typer.echo(f"More sessions follow: add --cursor {data['next_cursor']}")


def _print_session(data: dict[str, Any], output_json: bool) -> None:
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    shown = len(data["messages"])
    header = data.get("title") or data["session_id"]
    _console.print(f"[bold]{header}[/bold]", markup=True)
    _console.print(
        f"{data['project_path'] or ''}  —  turns {data['offset'] + 1}"
        f"-{data['offset'] + shown} of {data['message_count']}",
        markup=False,
    )
    for message in data["messages"]:
        _console.print(f"\n[bold]{message['role']}[/bold] {_short_time(message.get('timestamp'))}")
        _console.print(message["text"], markup=False)
        if message.get("truncated"):
            _console.print("[dim](turn truncated)[/dim]")


def attach(agent_app: typer.Typer) -> None:
    """Register the transcript command on agent_cmd's existing typer."""
    agent_app.command("transcript")(transcript)
