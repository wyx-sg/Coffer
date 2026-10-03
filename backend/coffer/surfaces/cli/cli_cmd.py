"""``coffer cli …`` — the command-line tools Coffer knows: the ones skills and MCP
servers require, and the ones you add by hand (spec skill-manager "Serve
required commands on REST, the command line and the web", "Declare a
command-line tool without a skill").

``add``, ``edit`` and ``rm`` declare a tool by hand, with no skill. ``list`` and
``show`` read ``/clis``; ``check`` probes again; ``prompt``
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

app = typer.Typer(help="Add and check command-line tools")
_console = Console()


def _version_label(item: dict[str, Any]) -> str:
    found = item["version"] or ("—" if item["path"] is None else "unknown")
    return f"{found} (min {item['min_version']})" if item["min_version"] else found


def _login_label(item: dict[str, Any]) -> str:
    state = item["login"]["state"]
    return {"logged_in": "logged in", "logged_out": "not logged in", "not_needed": "—"}.get(
        state or "", "—"
    )


def _needed_by_label(item: dict[str, Any]) -> str:
    names = [n["skill_name"] for n in item["needed_by"]] + [
        f"{s['server_name']} (MCP)" for s in item["needed_by_servers"]
    ]
    if item["added"]:
        names.insert(0, "added by you")
    return ", ".join(names)


def _print_table(items: list[dict[str, Any]]) -> None:
    if not items:
        typer.echo("No command-line tool yet: add one with `coffer cli add <command>`.")
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
            _needed_by_label(it),
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
    """List every command-line tool — added by hand or required — problems first."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get("/clis")
        _cli_client.check(r, verbose=verbose_of(ctx))
    _print_listing(r.json(), output_json=output_json)


@app.command("add")
def add(
    ctx: typer.Context,
    command: str = typer.Argument(
        ..., metavar="COMMAND", help="A command name (jq) or the absolute path of an executable"
    ),
    title: str | None = typer.Option(None, "--title", help="A display name"),
    description: str | None = typer.Option(None, "--description", help="What it is for"),
    min_version: str | None = typer.Option(
        None, "--min-version", help='Oldest wanted, like "2.40"'
    ),
    login_check: str | None = typer.Option(
        None,
        "--login-check",
        help='A command line that exits 0 when logged in, like "gh auth status"',
    ),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Add a command-line tool by hand; no skill is needed."""
    body = {
        "command": command,
        "title": title,
        "description": description,
        "min_version": min_version,
        "login_check": login_check,
    }
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/clis", json=body)
        _cli_client.check(r, verbose=verbose_of(ctx))
    if output_json:
        typer.echo(_json.dumps(r.json(), indent=2))
    else:
        _print_table([r.json()])


@app.command("edit")
def edit(
    ctx: typer.Context,
    command: str = typer.Argument(..., metavar="COMMAND", help="A tool you added, e.g. jq"),
    title: str | None = typer.Option(None, "--title", help="A display name; '' clears it"),
    description: str | None = typer.Option(None, "--description", help="'' clears it"),
    min_version: str | None = typer.Option(None, "--min-version", help="'' clears it"),
    login_check: str | None = typer.Option(None, "--login-check", help="'' clears it"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Change a tool you added by hand (only the options you give change)."""
    given = {
        "title": title,
        "description": description,
        "min_version": min_version,
        "login_check": login_check,
    }
    body = {k: (v or None) for k, v in given.items() if v is not None}
    if not body:
        typer.echo("nothing to change: give --title, --description, --min-version or --login-check")
        raise typer.Exit(int(ExitCode.INVALID_USAGE))
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.patch(f"/clis/{command}", json=body)
        _cli_client.check(r, verbose=verbose_of(ctx))
    if output_json:
        typer.echo(_json.dumps(r.json(), indent=2))
    else:
        _print_table([r.json()])


@app.command("rm")
def rm(
    ctx: typer.Context,
    command: str = typer.Argument(..., metavar="COMMAND", help="A tool you added, e.g. jq"),
    yes: bool = typer.Option(False, "--yes", "-y", "--force", "-f", help="Do not ask"),
) -> None:
    """Remove a tool you added by hand. A skill that requires it keeps it listed."""
    if not yes and not typer.confirm(f"Really remove the command-line tool {command}?"):
        raise typer.Exit(1)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/clis/{command}")
        _cli_client.check(r, verbose=verbose_of(ctx))
    typer.echo(f"removed: {command}")


@app.command("show")
def show(
    ctx: typer.Context,
    command: str = typer.Argument(..., metavar="COMMAND", help="The command, e.g. gh"),
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Show one command-line tool: where it is, its version, login state and
    what needs it."""
    verbose = verbose_of(ctx)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/clis/{command}")
        _cli_client.check(r, verbose=verbose)
        data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"command:     {data['command']}" + (f" ({data['title']})" if data["title"] else ""))
    if data["description"]:
        typer.echo(f"about:       {data['description']}")
    typer.echo(f"status:      {data['status']}")
    typer.echo(f"path:        {data['path'] or '—'}")
    typer.echo(f"version:     {_version_label(data)}")
    typer.echo(f"login:       {_login_label(data)}")
    if data["handoff"]:
        typer.echo(f"hand off:    coffer cli prompt {command}  (a prompt for your agent)")
    typer.echo("needed by:")
    if data["added"]:
        typer.echo("  - added by you")
    for n in data["needed_by"]:
        extra = f" (min {n['min_version']})" if n["min_version"] else ""
        why = f" — {n['why']}" if n["why"] else ""
        typer.echo(f"  - {n['skill_name']}{extra}{why}")
    for s in data["needed_by_servers"]:
        typer.echo(f"  - {s['server_name']} (MCP server, starts with {s['launcher']})")


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
