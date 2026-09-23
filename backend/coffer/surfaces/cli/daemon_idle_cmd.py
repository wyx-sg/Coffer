"""`coffer daemon idle` — how long the daemon serves nobody before standing down.

The daemon is resident (``coffer daemon service install``), which is what
makes an agent's call work at any hour with no window open. Resident is not
the same as immortal: this is the ceiling on it, and the setting for someone
who wants either extreme — a daemon that goes after lunch, or one that never
goes at all.

Read and written the same way as ``coffer daemon port``: straight into
``~/.coffer/daemon-config.json``, with no daemon involved. A running daemon
read the value when it booted and keeps it until it restarts, which is what
``show`` says when the two disagree.
"""

from __future__ import annotations

import typer

from coffer.infrastructure.daemon import config as daemon_config
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="How long the daemon stays up with nothing using it")


def _describe(hours: float | None) -> str:
    if hours is None:
        return "never stands down — the daemon stays up for the whole login session"
    return f"stands down after {hours:g}h with nothing using it"


@app.command("show")
def show() -> None:
    """The configured idle window."""
    typer.echo(_describe(daemon_config.read_idle_shutdown_hours()))


@app.command("set")
def set_hours(
    hours: float = typer.Argument(..., help="Hours of disuse before standing down"),
) -> None:
    """Stand down after HOURS with nothing using the daemon."""
    try:
        daemon_config.write_idle_shutdown_hours(hours)
    except daemon_config.InvalidIdleShutdown as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(int(ExitCode.INVALID_INPUT)) from None
    typer.echo(_describe(hours))
    typer.echo("takes effect at the next daemon start: run `coffer daemon restart` to apply now")


@app.command("never")
def never() -> None:
    """Never stand down. For a vault whose channels must answer at any hour."""
    daemon_config.write_idle_shutdown_hours(None)
    typer.echo(_describe(None))
    typer.echo("takes effect at the next daemon start: run `coffer daemon restart` to apply now")
