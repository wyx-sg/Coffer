"""``coffer agent hook ...`` subcommands.

Split out of :mod:`coffer.surfaces.cli.agent_cmd` to keep that file under the
size cap. ``attach`` registers the ``hook`` sub-typer onto the agent app.
"""

from __future__ import annotations

import json as _json

import typer

from coffer.surfaces.cli import _client as _cli_client

hook_app = typer.Typer(help="Install/uninstall Coffer's lifecycle hooks into an agent")


def _not_found_exit(r: object) -> None:
    if r.status_code == 404:  # type: ignore[attr-defined]
        typer.echo(
            r.json().get("error", {}).get("message", "not found"),  # type: ignore[attr-defined]
            err=True,
        )
        raise typer.Exit(4)


@hook_app.command("status")
def hook_status(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Report whether Coffer's lifecycle hooks are installed in this agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.get(f"/agents/{name}/hook-install")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    if output_json:
        typer.echo(_json.dumps(data, indent=2))
        return
    typer.echo(f"installed: {data['installed']}")
    if data.get("command"):
        typer.echo(f"command: {data['command']}")


@hook_app.command("install")
def hook_install(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Install Coffer's SessionStart/SessionEnd hooks into this agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post(f"/agents/{name}/hook-install")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    # A shell-command install reports the installed command; a block-mode
    # install (INSTRUCTIONS_BLOCK) has none — the block itself is the payload.
    command = r.json().get("command")
    suffix = f" ({command})" if command else " (session-context block)"
    typer.echo(f"installed Coffer hooks into agent:{name}{suffix}")


@hook_app.command("uninstall")
def hook_uninstall(
    ctx: typer.Context,
    name: str = typer.Argument(...),
) -> None:
    """Remove Coffer's lifecycle hooks from this agent."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.delete(f"/agents/{name}/hook-install")
        _not_found_exit(r)
        _cli_client.check(r, verbose=verbose)
    typer.echo(f"removed Coffer hooks from agent:{name}")


def attach(app: typer.Typer) -> None:
    """Register the ``hook`` sub-typer onto the agent app."""
    app.add_typer(hook_app, name="hook")
