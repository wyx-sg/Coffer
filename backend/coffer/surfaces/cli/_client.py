"""HTTP client wrapper that reads ~/.coffer/daemon.json and attaches the token."""

from __future__ import annotations

import contextlib
import os
import sys
import traceback
from pathlib import Path

import httpx
import typer

from coffer.infrastructure.daemon.pid_lock import DaemonInfo, read
from coffer.surfaces.cli._options import ExitCode


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


def client_or_exit() -> tuple[httpx.Client, DaemonInfo]:
    info = discover()
    if info is None:
        print(
            "daemon not running. start it with: coffer daemon start",
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
            "daemon not reachable (is it running? try `coffer daemon start`)",
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
