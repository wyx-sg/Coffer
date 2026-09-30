"""``coffer cli …`` — the command-line tools managed skills require (spec
skill-manager "Serve required commands on REST, the command line and the
web").

``list`` and ``show`` read ``/clis``; ``check`` probes again; ``prompt``
prints the hand-off prompt for a command that needs you — the text to give
your agent, which installs or updates it (or helps you log in) the way that
suits this machine. Coffer runs no install and no login itself.
"""

from __future__ import annotations

import json as _json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._kind_verbs import verbose_of
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="Check the command-line tools skills require")
_console = Console()


def _version_label(item: dict[str, Any]) -> str:
    found = item["version"] or ("—" if item["path"] is None else "unknown")
    return f"{found} (min {item['min_version']})" if item["min_version"] else found


def _login_label(item: dict[str, Any]) -> str:
    state = item["login"]["state"]
    return {"logged_in": "logged in", "logged_out": "not logged in", "not_needed": "—"}.get(
        state or "", "—"
    )


def _print_table(items: list[dict[str, Any]]) -> None:
    if not items:
        typer.echo("No skill requires a command-line tool.")
        return
    table = Table(title="CLIs")
    for col in ("Command", "Status", "Version", "Login", "Needed by"):
        table.add_column(col)
    for it in items:
        table.add_row(
            it["command"],
            it["status"],
            _version_label(it),
            _login_label(it),
            ", ".join(n["skill_name"] for n in it["needed_by"]),
        )
    _console.print(table)


def _print_listing(body: dict[str, Any], *, output_json: bool) -> None:
    if output_json:
        typer.echo(_json.dumps(body, indent=2))
        return
    _print_table(body["items"])
    for w in body["warnings"]:
        typer.echo(f"warning: {w['skill_name']}: {w['message']}", err=True)


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """List every command a skill requires, problems first."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/clis")
        _cli_client.check(r, verbose=verbose_of(ctx))
    _print_listing(r.json(), output_json=output_json)


@app.command("show")
def show(
    ctx: typer.Context,
    command: str = typer.Argument(..., metavar="COMMAND", help="The command, e.g. gh"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Show one required command: where it is, its version and login state."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/clis/{command}")
        _cli_client.check(r, verbose=verbose_of(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"command:     {data['command']}" + (f" ({data['title']})" if data["title"] else ""))
    typer.echo(f"status:      {data['status']}")
    typer.echo(f"path:        {data['path'] or '—'}")
    typer.echo(f"version:     {_version_label(data)}")
    typer.echo(f"login:       {_login_label(data)}")
    if data["login"]["command"]:
        typer.echo(f"log in with: {data['login']['command']}")
    if data["handoff"]:
        typer.echo(f"hand off:    coffer cli prompt {command}  (a prompt for your agent)")
    typer.echo("needed by:")
    for n in data["needed_by"]:
        extra = f" (min {n['min_version']})" if n["min_version"] else ""
        why = f" — {n['why']}" if n["why"] else ""
        typer.echo(f"  - {n['skill_name']}{extra}{why}")


@app.command("check")
def check(
    ctx: typer.Context,
    command: str | None = typer.Argument(None, metavar="[COMMAND]", help="One command only"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Probe the required commands again (or one of them)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/clis/{command}/check" if command else "/clis/check")
        _cli_client.check(r, verbose=verbose_of(ctx))
    body = r.json()
    if command is None:
        _print_listing(body, output_json=output_json)
    elif output_json:
        typer.echo(_json.dumps(body, indent=2))
    else:
        _print_table([body])


@app.command("prompt")
def prompt(
    ctx: typer.Context,
    command: str = typer.Argument(..., metavar="COMMAND", help="The command, e.g. jq"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Print the prompt to give your agent for a command that needs you."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/clis/{command}")
        _cli_client.check(r, verbose=verbose_of(ctx))
    data = r.json()
    if output_json:
        typer.echo(_json.dumps({"command": data["command"], "handoff": data["handoff"]}, indent=2))
        return
    if data["handoff"] is None:
        typer.echo(f"{command} is ready; there is nothing to hand off.", err=True)
        raise typer.Exit(int(ExitCode.CONFLICT))
    typer.echo(data["handoff"]["prompt"])
