"""`coffer daemon` subcommand group: start (detached) / stop / status."""

from __future__ import annotations

import json as _json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import typer

from coffer.surfaces.cli import _client as _cli_client

app = typer.Typer(help="Daemon lifecycle")


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


@app.command("start")
def start() -> None:
    """Spawn the daemon as a detached background process."""
    home = Path(os.environ.get("HOME", "~")).expanduser()
    daemon_json = home / ".coffer" / "daemon.json"

    if daemon_json.exists():
        typer.echo("daemon already running (daemon.json exists)")
        raise typer.Exit(0)

    cmd = [
        sys.executable,
        "-m",
        "coffer.infrastructure.daemon.entry",
    ]

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


@app.command("stop")
def stop() -> None:
    """Send SIGTERM to the running daemon and wait for it to exit."""
    info = _cli_client.discover()
    if info is None:
        typer.echo("daemon not running", err=True)
        raise typer.Exit(0)

    try:
        os.kill(info.pid, signal.SIGTERM)
    except ProcessLookupError:
        # already gone; just clean up daemon.json
        home = Path(os.environ.get("HOME", "~")).expanduser()
        (home / ".coffer" / "daemon.json").unlink(missing_ok=True)
        typer.echo("daemon already exited; cleaned up stale daemon.json")
        return

    home = Path(os.environ.get("HOME", "~")).expanduser()
    if _wait_for_daemon_json_gone(home / ".coffer" / "daemon.json", timeout=5.0):
        typer.echo("daemon stopped")
    else:
        typer.echo("daemon did not clean up daemon.json in 5s", err=True)
        raise typer.Exit(1)


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


@app.command("backup")
def backup(
    ctx: typer.Context,
    to: str | None = typer.Option(None, "--to", help="Destination path for the backup file"),
) -> None:
    """Back up the Coffer database."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    payload: dict[str, object] = {}
    if to is not None:
        payload["path"] = to
    with c:
        r = c.post("/daemon/backup", json=payload)
        _cli_client.check(r, verbose=verbose)
    data = r.json()
    typer.echo(f"backup:  {data['path']} ({data['size_bytes']} bytes)")


@app.command("rotate-token")
def rotate_token(ctx: typer.Context) -> None:
    """Rotate the daemon API token and update daemon.json."""
    verbose = (ctx.obj or {}).get("verbose", False)
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/daemon/rotate-token")
        _cli_client.check(r, verbose=verbose)
    typer.echo("token rotated; re-read ~/.coffer/daemon.json for the new value")
