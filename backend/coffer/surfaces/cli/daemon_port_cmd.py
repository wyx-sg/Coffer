"""`coffer daemon port` — show, change, or clear the port the daemon listens on.

This is the ONLY surface for the setting, and that is deliberate. The daemon
binds 8000 by default and refuses to start when it cannot have it, so the state
this setting most needs to be changed from is "no daemon is running" — which
rules out a page or a route the daemon itself would have to serve. Everything
here therefore reads and writes `~/.coffer/daemon-config.json` directly, with
no daemon involved and none required.

A running daemon is still consulted for one thing: it owns its bound socket and
cannot move without restarting, so when the new port is not the one it is on,
`set`/`clear` say a restart is still owed.
"""

from __future__ import annotations

import json as _json

import typer

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon import config as daemon_config
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="The port the daemon listens on")

_RESTART_HINT = "run: coffer daemon restart"


def _validated(port: int) -> int:
    """Reject an unbindable port before anything is written.

    Shares :mod:`coffer.infrastructure.daemon.config`'s bounds rather than
    restating them, so the CLI can never drift from what the daemon accepts.
    """
    try:
        return daemon_config.validate_port(port)
    except daemon_config.InvalidPort as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT)) from None


def _outcome(port: int | None) -> str:
    if port is None:
        return f"fixed port cleared — the daemon goes back to {daemon_config.DEFAULT_PORT}"
    return f"fixed port set to {port}"


def _apply(port: int | None) -> None:
    """Write the setting, then say whether a restart is owed.

    The file is written whatever the daemon is doing — it is read at the next
    start, and a daemon that is up has no say in the matter. What a live daemon
    does decide is the second line: if it is already serving the port that was
    just chosen there is nothing left to do, and saying "restart" anyway would
    train the user to ignore the line.
    """
    daemon_config.write_fixed_port(port)
    typer.echo(_outcome(port))

    info = bootstrap.live_daemon()
    if info is None:
        typer.echo("daemon not running — the setting applies at the next start")
        return
    if daemon_config.effective_port() != info.port:
        typer.echo(
            f"the daemon is still on port {info.port}; "
            f"the change applies at the next start — {_RESTART_HINT}"
        )


@app.command("show")
def show(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Show the port the daemon will bind, and the port it is actually on."""
    del ctx  # read locally; no daemon call to make verbose
    configured = daemon_config.read_fixed_port()
    readable = daemon_config.config_is_readable()
    info = bootstrap.live_daemon()
    effective = info.port if info is not None else None

    if output_json:
        typer.echo(
            _json.dumps(
                {
                    "configured_port": configured,
                    "effective_port": effective,
                    "daemon_running": info is not None,
                    "config_readable": readable,
                }
            )
        )
        return

    if configured is None:
        typer.echo(f"configured: default ({daemon_config.DEFAULT_PORT})")
    else:
        typer.echo(f"configured: {configured}")
    if info is None:
        typer.echo("daemon:     not running")
    else:
        typer.echo(f"daemon:     running on {info.port}")

    if not readable:
        typer.echo(
            f"the config file at {daemon_config.config_path()} exists but could not be read; "
            f"the default port {daemon_config.DEFAULT_PORT} is in effect"
        )
    elif effective is not None and daemon_config.effective_port() != effective:
        typer.echo(f"the configured port applies at the next start — {_RESTART_HINT}")


@app.command("set")
def set_port(
    port: int = typer.Argument(..., help="Port the daemon should always listen on"),
) -> None:
    """Change the port the daemon binds, away from the default."""
    _apply(_validated(port))


@app.command("clear")
def clear() -> None:
    """Go back to the default port."""
    _apply(None)
