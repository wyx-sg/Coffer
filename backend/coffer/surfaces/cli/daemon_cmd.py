"""`coffer daemon` subcommand group: start (detached) / stop / restart / status."""

from __future__ import annotations

import json as _json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import typer

from coffer.infrastructure.daemon import bootstrap, port_alloc
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.pid_lock import pid_is_coffer_daemon
from coffer.infrastructure.daemon.spawn import daemon_spawn_command
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli import daemon_port_cmd

app = typer.Typer(help="Daemon lifecycle")
app.add_typer(daemon_port_cmd.app, name="port")


def _wait_for_daemon_json(path: Path, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.1)
    return False


def _wait_for_daemon_json_gone(path: Path, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not path.exists():
            return True
        time.sleep(0.1)
    return False


def _refuse_if_fixed_port_is_taken() -> None:
    """Diagnose a squatted fixed port here, instead of after a boot timeout.

    Without this the user meets "daemon failed to start within 10s; check
    daemon.log" — true, but it hides the one cause a fixed port makes likely,
    behind a file they then have to open. Only the caller's ordering makes this
    correct: ``live_daemon()`` is probed first, so *our own* daemon holding the
    port stays the clean "already running" path rather than a conflict.
    """
    port = daemon_config.read_fixed_port()
    if port is None:
        return
    holder = port_alloc.find_port_holder(port)
    if holder is None:
        # Either the port is free, or the holder is another user's process we
        # cannot see. Let the daemon try: it fails with the same message.
        return
    typer.echo(port_alloc.fixed_port_conflict_message(port, holder), err=True)
    raise typer.Exit(1)


def _start_daemon() -> None:
    """Body of ``start``, shared with ``restart``."""
    home = Path(os.environ.get("HOME", "~")).expanduser()
    daemon_json = home / ".coffer" / "daemon.json"

    # P1-1: key off live_daemon() (a real status probe), NOT mere file
    # presence. A stale daemon.json left by a crashed daemon must trigger a
    # respawn, not a false "already running".
    if bootstrap.live_daemon() is not None:
        typer.echo("daemon already running")
        raise typer.Exit(0)

    _refuse_if_fixed_port_is_taken()

    cmd = daemon_spawn_command()

    log_dir = home / ".coffer" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "daemon.log"
    log = open(log_path, "ab")  # noqa: SIM115 — handle leaks intentionally into child

    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    if not _wait_for_daemon_json(daemon_json, timeout=10.0):
        proc.kill()
        typer.echo("daemon failed to start within 10s; check daemon.log", err=True)
        raise typer.Exit(1)

    typer.echo(f"daemon started (pid={proc.pid})")


@app.command("start")
def start() -> None:
    """Spawn the daemon as a detached background process."""
    _start_daemon()


def _stop_daemon() -> bool:
    """Body of ``stop``, shared with ``restart``.

    Returns False when there was nothing to stop. The two callers differ only
    in what that means — an error for ``stop``, the normal case for
    ``restart`` — so the decision is theirs, not this helper's.
    """
    info = _cli_client.discover()
    if info is None:
        return False

    home = Path(os.environ.get("HOME", "~")).expanduser()

    # P1-1: verify the recorded pid IS a coffer daemon before signalling it.
    # A crashed daemon's pid can be recycled onto an unrelated process; we must
    # not SIGTERM a stranger. If it isn't ours, the daemon.json is stale —
    # clean it up instead of killing whoever now holds that pid.
    if not pid_is_coffer_daemon(info.pid):
        (home / ".coffer" / "daemon.json").unlink(missing_ok=True)
        typer.echo("daemon pid is not a coffer daemon; cleaned up stale daemon.json")
        return True

    try:
        os.kill(info.pid, signal.SIGTERM)
    except ProcessLookupError:
        # already gone; just clean up daemon.json
        (home / ".coffer" / "daemon.json").unlink(missing_ok=True)
        typer.echo("daemon already exited; cleaned up stale daemon.json")
        return True

    if _wait_for_daemon_json_gone(home / ".coffer" / "daemon.json", timeout=5.0):
        typer.echo("daemon stopped")
        return True
    typer.echo("daemon did not clean up daemon.json in 5s", err=True)
    raise typer.Exit(1)


@app.command("stop")
def stop() -> None:
    """Send SIGTERM to the running daemon and wait for it to exit."""
    if not _stop_daemon():
        typer.echo("daemon not running", err=True)
        raise typer.Exit(0)


@app.command("restart")
def restart() -> None:
    """Stop the running daemon (if any) and start a fresh one.

    The way a changed setting — a fixed port above all — actually takes effect,
    since a running daemon owns its bound socket and cannot move without one.
    """
    _stop_daemon()
    _start_daemon()


@app.command("status")
def status(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", help="JSON output for scripts"),
) -> None:
    """Show daemon status."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, info = _cli_client.client_or_exit()
    with c:
        r = c.get("/daemon/status")
        _cli_client.check(r, verbose=verbose)
        data = r.json()
    if output_json:
        typer.echo(_json.dumps({**data, "port": info.port, "pid": info.pid}))
        return
    typer.echo(f"status:  {data['status']}")
    typer.echo(f"version: {data['version']}")
    typer.echo(f"port:    {info.port}")
    typer.echo(f"pid:     {info.pid}")


@app.command("rotate-token")
def rotate_token(ctx: typer.Context) -> None:
    """Rotate the daemon API token and update daemon.json."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/daemon/rotate-token")
        _cli_client.check(r, verbose=verbose)
    typer.echo("token rotated; re-read ~/.coffer/daemon.json for the new value")
