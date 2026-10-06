"""HTTP client wrapper that reads ~/.coffer/daemon.json and attaches the token.

Implements the detect-or-spawn ADR: when the daemon is absent,
``client_or_exit()`` spawns it automatically instead of asking the user to
run ``coffer daemon start``.
"""

from __future__ import annotations

import contextlib
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
from coffer.infrastructure.vault.home import daemon_json_path
from coffer.surfaces.cli._options import ExitCode

# How long (seconds) to wait for daemon.json to appear after spawning.
_DAEMON_BOOT_TIMEOUT: float = 10.0


#: What the CLI says when the running daemon's answer lacks a field this CLI
#: reads: the daemon is older than the CLI talking to it.
OUTDATED_DAEMON = "the running daemon predates this CLI; restart it: coffer daemon restart"


class DaemonNotRunning(SystemExit):
    """Exit code 3 — daemon not reachable."""

    code = 3


class ClientUnavailable(Exception):  # noqa: N818
    """Why no client could be had, for a ``--json`` caller to render as its
    error envelope instead of the text :func:`client_or_exit` prints."""

    def __init__(
        self, code: str, message: str, exit_code: ExitCode, details: dict[str, object]
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.exit_code, self.details = code, message, exit_code, details


def _daemon_json_path() -> Path:
    return daemon_json_path()


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


def warn_if_version_skew(info: DaemonInfo) -> dict[str, object] | None:
    """Print a one-line WARNING to stderr when the daemon ``info`` names is a
    different build than this CLI (ADR daemon-detect-or-spawn: detection, not
    refusal). Silent when the probe fails — the command itself will say so.
    Returns the status body it read, ``None`` when nothing answered.
    """
    status = probe_status(info, timeout=_SKEW_PROBE_TIMEOUT)
    message = skew_warning(status, caller="coffer")
    if message is not None:
        print(message, file=sys.stderr)
    return status


def waiting_for_git(status: dict[str, object] | None) -> dict[str, object] | None:
    """What the daemon waits for while it is in its setup state, else ``None``."""
    if not status or status.get("status") != "setup":
        return None
    setup = status.get("setup")
    return setup if isinstance(setup, dict) else None


def print_waiting_for_git(setup: dict[str, object]) -> None:
    """Say why the daemon waits — the message and the hand-off the page shows
    (spec daemon "Wait in a setup state when git is missing or too old")."""
    typer.echo(str(setup.get("message", "Coffer needs git.")), err=True)
    handoff = setup.get("handoff")
    if isinstance(handoff, dict) and handoff.get("prompt"):
        typer.echo("\nTo hand this to your agent, give it this prompt:\n", err=True)
        typer.echo(str(handoff["prompt"]), err=True)


def daemon_is_running() -> bool:
    """Whether a live daemon answers now — a probe that never spawns one.

    For commands that report on the daemon (``coffer daemon status``), where
    :func:`client_or_exit`'s detect-or-spawn would change the answer.
    """
    return live_daemon() is not None


def client_or_exit(
    *, allow_setup: bool = False, as_json: bool = False
) -> tuple[httpx.Client, DaemonInfo]:
    """Return an authenticated httpx.Client + DaemonInfo for the running daemon.

    Implements detect-or-spawn: if no daemon is *reachable* — daemon.json
    absent, OR present but stale (a crashed daemon left it behind and nothing is
    serving its port) — spawn one automatically and wait up to
    ``_DAEMON_BOOT_TIMEOUT`` seconds for it to start serving.

    Raises DaemonNotRunning (exit 3) only if the spawn fails or times out. A
    daemon waiting for git is answered here, before the command's own request:
    the reason and the hand-off, exit 10 — unless ``allow_setup`` (``coffer
    daemon status``, which reports it).

    With ``as_json`` neither failure prints: :class:`ClientUnavailable` is
    raised for the caller to render as the ``--json`` error envelope.
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
            message = (
                "daemon failed to start within "
                f"{_DAEMON_BOOT_TIMEOUT:.0f}s; check ~/.coffer/logs/daemon.log"
            )
            if as_json:
                raise ClientUnavailable(
                    "DAEMON_UNREACHABLE", message, ExitCode.DAEMON_UNREACHABLE, {}
                )
            print(message, file=sys.stderr)
            raise DaemonNotRunning()

    setup = waiting_for_git(warn_if_version_skew(info))
    if setup is not None and not allow_setup:
        if as_json:
            raise ClientUnavailable(
                "DAEMON_WAITING_FOR_GIT",
                str(setup.get("message", "Coffer needs git.")),
                ExitCode.GIT_NEEDED,
                {"handoff": setup["handoff"]} if isinstance(setup.get("handoff"), dict) else {},
            )
        print_waiting_for_git(setup)
        raise typer.Exit(int(ExitCode.GIT_NEEDED))
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


def check(r: httpx.Response, *, verbose: bool = False, as_json: bool = False) -> None:
    """Return when ``r`` succeeded; otherwise render its error and exit.

    The older hand-written readers call this; it renders exactly as the
    management commands' :func:`coffer.surfaces.cli._io.check` does — the same
    exit codes and, with ``as_json``, the same error envelope on stderr — so
    ``--json`` holds on every path. ``verbose`` is kept for those callers;
    ``coffer --verbose`` itself is read once, by ``_io``.
    """
    del verbose
    if 200 <= r.status_code < 300:
        return
    from coffer.surfaces.cli import _io

    _io.check(r, as_json=as_json)


def render_http_error(
    err: Exception,
    *,
    verbose: bool,
) -> ExitCode:
    """Print a transport failure (or anything unexpected) and return its exit code.

    Callers should ``raise typer.Exit(int(render_http_error(err, verbose=v)))``.
    Secrets must never be passed here — this function may print context to stderr.
    """
    if isinstance(err, httpx.HTTPStatusError):
        from coffer.surfaces.cli import _io

        code, message, details = _io.envelope_of(err.response)
        exit_code = _io.exit_code_for(err.response.status_code, code)
        _io.render_failure(code, message, int(exit_code), as_json=False, details=details)
        return exit_code
    if isinstance(err, httpx.TransportError):
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
