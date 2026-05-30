"""HTTP client wrapper that reads ~/.coffer/daemon.json and attaches the token.

Implements the ADR-006 detect-or-spawn pattern: when the daemon is absent,
``client_or_exit()`` spawns it automatically instead of asking the user to
run ``coffer daemon start``.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import httpx
import typer

from coffer.infrastructure.daemon.pid_lock import DaemonInfo, read
from coffer.infrastructure.daemon.spawn import daemon_spawn_command
from coffer.surfaces.cli._options import ExitCode

# How long (seconds) to wait for daemon.json to appear after spawning.
_DAEMON_BOOT_TIMEOUT: float = 10.0


class DaemonNotRunning(SystemExit):
    """Exit code 3 — daemon not reachable."""

    code = 3


def _daemon_json_path() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


def discover() -> DaemonInfo | None:
    path = _daemon_json_path()
    if not path.exists():
        return None
    try:
        return read(path)
    except (ValueError, KeyError, OSError):
        return None


def _wait_for_daemon_json(timeout: float = _DAEMON_BOOT_TIMEOUT) -> DaemonInfo | None:
    """Poll until daemon.json appears; return DaemonInfo or None on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = discover()
        if info is not None:
            return info
        time.sleep(0.1)
    return None


def _spawn_daemon() -> subprocess.Popen[bytes] | None:
    """Detached best-effort spawn of the daemon process.

    Stdout/stderr go to ~/.coffer/logs/daemon.log; stdin is DEVNULL.
    The caller is responsible for waiting for daemon.json to appear.

    Returns the ``Popen`` handle so the caller can ``kill()`` the
    half-started daemon if it never publishes daemon.json within the boot
    timeout; returns ``None`` if the spawn itself failed (OSError).
    """
    home = Path(os.environ.get("HOME", "~")).expanduser()
    log_dir = home / ".coffer" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "daemon.log"
    log = open(log_path, "ab")  # noqa: SIM115 — handle leaks intentionally into child

    cmd = daemon_spawn_command()

    try:
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            return subprocess.Popen(
                cmd,
                stdout=log,
                stderr=log,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        return subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        log.close()
        print(f"coffer: failed to spawn daemon: {e}", file=sys.stderr)
        return None


def client_or_exit() -> tuple[httpx.Client, DaemonInfo]:
    """Return an authenticated httpx.Client + DaemonInfo for the running daemon.

    Implements ADR-006 detect-or-spawn: if daemon.json is absent (or the
    daemon is not reachable), spawn it automatically and wait up to
    ``_DAEMON_BOOT_TIMEOUT`` seconds for it to write daemon.json.

    Raises DaemonNotRunning (exit 3) only if the spawn fails or times out.
    """
    info = discover()
    if info is None:
        # ADR-006: auto-spawn the daemon rather than asking the user.
        proc = _spawn_daemon()
        info = _wait_for_daemon_json(timeout=_DAEMON_BOOT_TIMEOUT)
        if info is None:
            # Kill the half-started daemon so it can't finish booting *after*
            # we gave up and leave a daemon.json the user was told failed.
            if proc is not None:
                with contextlib.suppress(OSError):
                    proc.kill()
            print(
                "daemon failed to start within "
                f"{_DAEMON_BOOT_TIMEOUT:.0f}s; check ~/.coffer/logs/daemon.log",
                file=sys.stderr,
            )
            raise DaemonNotRunning()

    base = f"http://127.0.0.1:{info.port}/api/v1"
    return (
        httpx.Client(
            base_url=base,
            headers={
                "X-Coffer-Token": info.token,
                # SPEC-005: tag every CLI-initiated mutation in audit_log.
                "X-Coffer-Actor": "cli",
            },
            timeout=15,
        ),
        info,
    )


def check(
    r: httpx.Response,
    *,
    verbose: bool,
) -> None:
    """Call ``r.raise_for_status()``; on error, render it and raise ``typer.Exit``.

    This is the single replacement for bare ``r.raise_for_status()`` calls in
    the command modules. It routes every HTTP error through ``render_http_error``
    so the user sees a human-readable message and the correct exit code.
    """
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise typer.Exit(int(render_http_error(e, verbose=verbose))) from None


def render_http_error(
    err: Exception,
    *,
    verbose: bool,
) -> ExitCode:
    """Print the error to stderr and return the appropriate ExitCode.

    Callers should ``raise typer.Exit(int(render_http_error(err, verbose=v)))``.
    Secrets must never be passed here — this function may print context to stderr.
    """
    if isinstance(err, httpx.HTTPStatusError):
        envelope = None
        with contextlib.suppress(Exception):
            envelope = err.response.json().get("error")
        message = envelope.get("message") if envelope else str(err)
        code_name = envelope.get("code") if envelope else None
        typer.echo(message, err=True)

        status = err.response.status_code
        exit_code: ExitCode = {
            404: ExitCode.NOT_FOUND,
            409: ExitCode.CONFLICT,
            400: ExitCode.INVALID_INPUT,
            422: ExitCode.INVALID_INPUT,
        }.get(status, ExitCode.GENERIC)

        if code_name in ("CREDENTIAL_MISSING", "CREDENTIAL_LOCKED"):
            exit_code = ExitCode.CREDENTIAL_ISSUE
    elif isinstance(err, httpx.ConnectError):
        typer.echo(
            "daemon not reachable — it may have crashed; check ~/.coffer/logs/daemon.log",
            err=True,
        )
        exit_code = ExitCode.DAEMON_UNREACHABLE
    else:
        typer.echo(f"unexpected error: {err}", err=True)
        exit_code = ExitCode.GENERIC

    if verbose:
        typer.echo("", err=True)
        typer.echo(traceback.format_exc(), err=True)

    return exit_code
