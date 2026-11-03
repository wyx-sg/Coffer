"""What a request that got no answer from the daemon means.

ADR ``cli-request-wait-budgets``. httpx raises one family,
``TransportError``, for three different situations, and each tells the person
something different:

- **unreachable** (``ConnectError``, ``ConnectTimeout``): nothing accepted the
  connection; the daemon is not running. ``DAEMON_UNREACHABLE``, exit 3.
- **connection lost** (``ReadError``, ``WriteError``, ``RemoteProtocolError``
  and the rest): the daemon took the request and the connection closed before
  an answer; it may have restarted or crashed. ``DAEMON_CONNECTION_LOST``,
  exit 3.
- **no answer in time** (``ReadTimeout``, ``WriteTimeout``, ``PoolTimeout``):
  the daemon is there but did not answer within the wait. It may still finish
  the operation, so this is not reported as a crash. ``CLI_REQUEST_TIMEOUT``,
  exit 13, naming the request and the wait.
"""

from __future__ import annotations

from typing import Any

import httpx

from coffer.surfaces.cli._options import ExitCode

UNREACHABLE = "daemon not reachable — it may have crashed; check ~/.coffer/logs/daemon.log"
LOST = (
    "the daemon closed the connection before answering — it may have restarted or "
    "crashed; check ~/.coffer/logs/daemon.log"
)


def _request_of(err: httpx.TransportError) -> tuple[str, str, float | None]:
    try:
        request = err.request
    except RuntimeError:
        return "", "", None
    timeouts = request.extensions.get("timeout") or {}
    read = timeouts.get("read") if isinstance(timeouts, dict) else None
    path = request.url.path.removeprefix("/api/v1")
    return request.method, path, float(read) if isinstance(read, int | float) else None


def classify(err: httpx.TransportError) -> tuple[str, str, ExitCode, dict[str, Any]]:
    """The error code, message, exit code and details ``err`` is reported with."""
    if isinstance(err, httpx.ConnectError | httpx.ConnectTimeout):
        return "DAEMON_UNREACHABLE", UNREACHABLE, ExitCode.DAEMON_UNREACHABLE, {}
    method, path, waited = _request_of(err)
    where = f"{method} {path}".strip()
    if isinstance(err, httpx.TimeoutException):
        within = f" within {waited:g} s" if waited is not None else " in time"
        message = (
            f"the daemon did not answer {where or 'the request'}{within}. It is likely still "
            "working on it, so the operation may still finish: check its result before "
            "retrying, or wait longer with `coffer --request-timeout <seconds> …`."
        )
        details: dict[str, Any] = {"method": method, "path": path, "waited_s": waited}
        return "CLI_REQUEST_TIMEOUT", message, ExitCode.WAIT_TIMEOUT, details
    return (
        "DAEMON_CONNECTION_LOST",
        LOST,
        ExitCode.DAEMON_UNREACHABLE,
        {"method": method, "path": path},
    )


__all__ = ["LOST", "UNREACHABLE", "classify"]
