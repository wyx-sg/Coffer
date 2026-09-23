"""`coffer daemon service` — install, remove, or inspect the login service.

The daemon wants to be running whether or not anything has a window open, and
launchd is how macOS says that (see
:mod:`coffer.infrastructure.daemon.login_service` for the plist and why each
key in it is what it is). This is the surface for turning it on.

Like ``coffer daemon port``, everything here reads and writes the user's own
launchd agent directly, with no daemon involved and none required — which is
the point, since the state it is most often reached from is "there is no
daemon running and I would like that to stop happening".
"""

from __future__ import annotations

import typer

from coffer.infrastructure.daemon import login_service
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="Run the daemon as a login service")


def _require_support() -> None:
    if login_service.is_supported():
        return
    typer.echo("a login service is macOS-only; there is no launchd here", err=True)
    raise typer.Exit(int(ExitCode.INVALID_INPUT))


@app.command("install")
def install() -> None:
    """Start the daemon at login, and restart it if it crashes."""
    _require_support()
    try:
        path = login_service.install()
    except OSError as exc:
        typer.echo(f"could not install the login service: {exc}", err=True)
        raise typer.Exit(int(ExitCode.GENERIC)) from None
    typer.echo(f"login service installed: {path}")
    typer.echo("the daemon starts at login, and after a crash")


@app.command("uninstall")
def uninstall() -> None:
    """Stop starting the daemon at login. Leaves a running daemon running."""
    _require_support()
    try:
        removed = login_service.uninstall()
    except OSError as exc:
        typer.echo(f"could not remove the login service: {exc}", err=True)
        raise typer.Exit(int(ExitCode.GENERIC)) from None
    if removed:
        typer.echo("login service removed — the daemon is now started on demand only")
    else:
        typer.echo("no login service was installed")


@app.command("status")
def status() -> None:
    """Whether the login service is installed, and where."""
    if not login_service.is_supported():
        typer.echo("not supported: a login service is macOS-only")
        return
    if login_service.is_installed():
        typer.echo(f"installed: {login_service.plist_path()}")
    else:
        typer.echo("not installed — the daemon is started on demand")
