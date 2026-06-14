"""`coffer history …` — cross-agent transcript history CLI (ADR-022).

Thin HTTP shells over the daemon's ``/api/v1/history`` routes:
  - ``search <q>``        BM25 search across all indexed transcripts.
  - ``sessions <agent>``  List one agent's transcript sessions.
  - ``browse <agent> <session_id>``  Print a session's scrubbed turns (read-only).
  - ``reindex``           (Re)build the local index from on-disk transcripts.
  - ``reset``             Drop the local index (rebuildable; nothing durable lost).
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Cross-agent transcript history commands")
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


@app.command("search")
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query."),
    agent_type: str | None = typer.Option(None, "--agent-type", help="Filter by agent type."),
    project: str | None = typer.Option(None, "--project", "-p", help="Filter by project path."),
    limit: int = typer.Option(20, "--limit", "-n", help="Max hits."),
) -> None:
    """Search the cross-agent transcript history."""
    params: dict[str, str | int] = {"q": query, "limit": limit}
    if agent_type is not None:
        params["agent_type"] = agent_type
    if project is not None:
        params["project"] = project
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/history/search", params=params)
        _cli_client.check(r, verbose=_verbose(ctx))
    hits = r.json()["hits"]
    if not hits:
        typer.echo("No matching transcripts.")
        return
    table = Table(title=f"History matches for {query!r}")
    table.add_column("agent")
    table.add_column("project")
    table.add_column("session")
    table.add_column("snippet")
    for h in hits:
        table.add_row(
            h["agent_type"],
            h.get("project_path") or "",
            h["session_id"],
            h["snippet"].replace("\n", " ")[:80],
        )
    _console.print(table)


@app.command("sessions")
def sessions(
    ctx: typer.Context,
    agent: str = typer.Argument(..., help="Registered agent name."),
) -> None:
    """List one agent's transcript sessions."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/history/sessions", params={"agent": agent})
        _cli_client.check(r, verbose=_verbose(ctx))
    table = Table(title=f"Sessions for {agent}")
    table.add_column("session_id")
    table.add_column("project_path")
    table.add_column("messages")
    table.add_column("started_at")
    for s in r.json()["sessions"]:
        table.add_row(
            s["session_id"],
            s.get("project_path") or "",
            str(s["message_count"]),
            s.get("started_at") or "",
        )
    _console.print(table)


@app.command("browse")
def browse(
    ctx: typer.Context,
    agent: str = typer.Argument(..., help="Registered agent name."),
    session_id: str = typer.Argument(..., help="Session ID to browse."),
) -> None:
    """Print a session's scrubbed natural-language turns (read-only)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/history/session", params={"agent": agent, "session_id": session_id})
        _cli_client.check(r, verbose=_verbose(ctx))
    for t in r.json()["turns"]:
        typer.echo(f"[{t['role']}] {t['text']}")


@app.command("reindex")
def reindex(
    ctx: typer.Context,
    agent: str | None = typer.Option(None, "--agent", "-a", help="Limit to one agent."),
) -> None:
    """(Re)build the local transcript index from on-disk transcripts."""
    params = {"agent": agent} if agent is not None else None
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/history/reindex", params=params)
        _cli_client.check(r, verbose=_verbose(ctx))
    d = r.json()
    typer.echo(f"indexed={d['indexed']} unchanged={d['unchanged']} removed={d['removed']}")


@app.command("reset")
def reset(ctx: typer.Context) -> None:
    """Drop the local transcript index (rebuildable; nothing durable lost)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/history/reset")
        _cli_client.check(r, verbose=_verbose(ctx))
    typer.echo(f"removed {r.json()['removed']} indexed session(s)")
