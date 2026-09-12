"""`coffer daemon port` — show, fix, or clear the port the daemon listens on.

Every command here works with NO daemon running, because that is a state this
very setting can cause: a fixed port something else has taken stops the daemon
from starting, so a surface that needed a live daemon to change the setting
would be unreachable exactly when it is needed.

When a daemon IS up, `set`/`clear` still go through it, so the change is
audited and lands the same way it would from the UI; writing the file directly
is the fallback, not the first choice. `show` never needs the daemon: it reads
the config file and the published daemon.json, both of which it can see
whatever state the daemon is in.
"""

from __future__ import annotations

import json as _json

import typer

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon import config as daemon_config
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._options import ExitCode

app = typer.Typer(help="The port the daemon listens on")

#: The daemon's own settings endpoint — the same one the UI writes through, so
#: a change made here is recorded exactly like a change made there.
_SETTINGS_PATH = "/settings/daemon"

_RESTART_HINT = "run: coffer daemon restart"


def _verbose(ctx: typer.Context) -> bool:
    return bool((ctx.obj or {}).get("verbose", False))


def _validated(port: int) -> int:
    """Reject an unbindable port before anything is written or sent.

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
        return "fixed port cleared — the daemon picks a port automatically"
    return f"fixed port set to {port}"


def _apply(ctx: typer.Context, port: int | None) -> None:
    """Persist the setting through the daemon when one answers, else directly."""
    info = bootstrap.live_daemon()
    if info is None:
        daemon_config.write_fixed_port(port)
        typer.echo(_outcome(port))
        typer.echo("daemon not running — wrote the setting directly; it applies at the next start")
        return

    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.put(_SETTINGS_PATH, json={"port": port})
        _cli_client.check(r, verbose=_verbose(ctx))
        payload = r.json()
    typer.echo(_outcome(port))

    restart_required = payload.get("restart_required")
    if restart_required is None:
        # Older daemon, or a response that omitted the flag: the question it
        # answers is simply whether the daemon is already on the new port.
        restart_required = port is not None and port != info.port
    if restart_required:
        running_on = payload.get("effective_port", info.port)
        typer.echo(
            f"the daemon is still on port {running_on}; "
            f"the change applies at the next start — {_RESTART_HINT}"
        )


@app.command("show")
def show(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Show the configured fixed port and the port the daemon is actually on."""
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
        typer.echo("configured: automatic (no fixed port)")
    else:
        typer.echo(f"configured: {configured}")
    if info is None:
        typer.echo("daemon:     not running")
    else:
        typer.echo(f"daemon:     running on {info.port}")

    if not readable:
        typer.echo(
            f"the config file at {daemon_config.config_path()} exists but could not be read; "
            "automatic selection is in effect"
        )
    elif configured is not None and effective is not None and configured != effective:
        typer.echo(f"the fixed port applies at the next start — {_RESTART_HINT}")


@app.command("set")
def set_port(
    ctx: typer.Context,
    port: int = typer.Argument(..., help="Port the daemon should always listen on"),
) -> None:
    """Fix the daemon's port so its web UI keeps one address."""
    _apply(ctx, _validated(port))


@app.command("clear")
def clear(ctx: typer.Context) -> None:
    """Go back to automatic port selection."""
    _apply(ctx, None)
