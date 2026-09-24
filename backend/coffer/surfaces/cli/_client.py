"""HTTP client wrapper that reads ~/.coffer/daemon.json and attaches the token.

Implements the detect-or-spawn ADR: when the daemon is absent,
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

from coffer.infrastructure.daemon.bootstrap import live_daemon, probe_status
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, read
from coffer.infrastructure.daemon.spawn import spawn_detached_daemon
from coffer.infrastructure.daemon.version_skew import skew_warning
from coffer.surfaces.cli._options import ExitCode

# How long (seconds) to wait for daemon.json to appear after spawning.
_DAEMON_BOOT_TIMEOUT: float = 10.0


class DaemonNotRunning(SystemExit):
    """Exit code 3 — daemon not reachable."""

    code = 3


def _daemon_json_path() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


def discover() -> DaemonInfo | None:
    """Read daemon.json without probing liveness (file presence only).

    Used by ``coffer daemon status`` and the shim, which do their own liveness
    handling. ``client_or_exit`` instead uses ``live_daemon`` so a stale file
    from a crashed daemon triggers a respawn rather than a dead connection.
    """
    path = _daemon_json_path()
    if not path.exists():
        return None
    try:
        return read(path)
    except (ValueError, KeyError, OSError):
        return None


def _wait_for_daemon(timeout: float = _DAEMON_BOOT_TIMEOUT) -> DaemonInfo | None:
    """Poll until a *live* daemon answers on its published port (or timeout).

    Probes ``live_daemon`` rather than mere daemon.json presence: the spawned
    daemon writes daemon.json a moment before uvicorn starts serving, so we
    wait for the status endpoint to actually answer before handing back a client.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = live_daemon()
        if info is not None:
            return info
        time.sleep(0.1)
    return None


def _spawn_daemon() -> subprocess.Popen[bytes] | None:
    """Detached best-effort spawn of the daemon process.

    Stdout/stderr go to ~/.coffer/logs/daemon.log; stdin is DEVNULL — the
    shared :func:`spawn_detached_daemon`, so the daemon's own refusal (a
    squatted port) lands in the log this surface tells the user to read.
    The caller is responsible for waiting for daemon.json to appear.

    Returns the ``Popen`` handle so the caller can ``kill()`` the
    half-started daemon if it never publishes daemon.json within the boot
    timeout; returns ``None`` if the spawn itself failed (OSError).
    """
    try:
        return spawn_detached_daemon()
    except OSError as e:
        print(f"coffer: failed to spawn daemon: {e}", file=sys.stderr)
        return None


#: How long the version-skew probe waits. Short: the daemon just answered the
#: liveness probe, and a missed warning costs nothing but the warning.
_SKEW_PROBE_TIMEOUT: float = 2.0


def warn_if_version_skew(info: DaemonInfo) -> None:
    """Print a one-line WARNING to stderr when the daemon ``info`` names is a
    different build than this CLI (ADR daemon-detect-or-spawn: detection, not
    refusal). Silent when the probe fails — the command itself will say so.
    """
    message = skew_warning(probe_status(info, timeout=_SKEW_PROBE_TIMEOUT), caller="coffer")
    if message is not None:
        print(message, file=sys.stderr)


def client_or_exit() -> tuple[httpx.Client, DaemonInfo]:
    """Return an authenticated httpx.Client + DaemonInfo for the running daemon.

    Implements detect-or-spawn: if no daemon is *reachable* — daemon.json
    absent, OR present but stale (a crashed daemon left it behind and nothing is
    serving its port) — spawn one automatically and wait up to
    ``_DAEMON_BOOT_TIMEOUT`` seconds for it to start serving.

    Raises DaemonNotRunning (exit 3) only if the spawn fails or times out.
    """
    # live_daemon() (not discover()) so a stale daemon.json from a crashed
    # daemon is treated as "no daemon" and respawned, instead of returning a
    # client pointed at a dead port that every command would then fail against.
    info = live_daemon()
    if info is None:
        # Detect-or-spawn: auto-spawn the daemon rather than asking the user.
        proc = _spawn_daemon()
        info = _wait_for_daemon(timeout=_DAEMON_BOOT_TIMEOUT)
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

    warn_if_version_skew(info)
    base = f"http://127.0.0.1:{info.port}/api/v1"
    return (
        httpx.Client(
            base_url=base,
            headers={
                "X-Coffer-Token": info.token,
                # Tag every CLI-initiated mutation in audit_log (spec
                # resource-framework "Audit every lifecycle change").
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
    elif isinstance(err, httpx.TransportError):
        # Refused, reset, closed without a response or timed out: from the
        # CLI's side each is the daemon not answering.
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
