"""`coffer transcript …` — transcript distillation CLI commands (Spec 007 extension).

Thin HTTP shells over the daemon. Two commands:
  - ``list <agent>``    List transcript sessions for a registered agent.
  - ``distill <agent>`` Distil insights from a session into Coffer memory facts.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Transcript distillation commands")
_console = Console()


def _verbose(ctx: typer.Context) -> bool:
    return bool(ctx.obj and ctx.obj.get("verbose"))


@app.command("list")
def list_sessions(
    ctx: typer.Context,
    agent: str = typer.Argument(..., help="Registered agent name."),
) -> None:
    """List transcript sessions for an agent."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{agent}/transcripts")
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()
    table = Table(title=f"Transcript sessions for {agent}")
    table.add_column("session_id")
    table.add_column("project_path")
    table.add_column("message_count")
    table.add_column("started_at")
    for s in data["sessions"]:
        table.add_row(
            s["session_id"],
            s.get("project_path") or "",
            str(s["message_count"]),
            s.get("started_at") or "",
        )
    _console.print(table)


@app.command("distill")
def distill(
    ctx: typer.Context,
    agent: str = typer.Argument(..., help="Registered agent name."),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID to distil."),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Filter by project path."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview insights without writing."),
) -> None:
    """Distil insights from an agent's transcript into Coffer memory."""
    body: dict[str, object] = {"dry_run": dry_run}
    if session_id is not None:
        body["session_id"] = session_id
    if project_path is not None:
        body["project_path"] = project_path

    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/agents/{agent}/transcripts/distill", json=body)
        _cli_client.check(r, verbose=_verbose(ctx))
    data = r.json()

    insights = data.get("insights", [])
    if not insights:
        typer.echo("No durable insights found in this session.")
        return

    typer.echo(f"Insights ({len(insights)}):")
    for ins in insights:
        typer.echo(f"  [{ins['type']}] {ins['name']}")
        typer.echo(f"    {ins['body']}")

    if dry_run:
        typer.echo("(dry-run: nothing was written to memory)")
    else:
        fact_ids: list[str] = data.get("fact_ids", [])
        if fact_ids:
            typer.echo(f"Created {len(fact_ids)} fact(s):")
            for fid in fact_ids:
                typer.echo(f"  {fid}")
