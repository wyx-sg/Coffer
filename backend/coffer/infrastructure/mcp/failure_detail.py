"""Why an upstream failed, in words Coffer can safely record.

An upstream's own exception text can embed a URL with a query-string secret,
a reflected header or the child's argv, so the call log never stores it. Until
now that left only the class name (``MCPError``, ``ConnectError``), which says
nothing about the cause. These helpers say what happened in Coffer's words:

* an HTTP upstream: the kind of network failure (the host does not resolve,
  the connection was refused, TLS failed, …) or the HTTP status it answered;
* a stdio upstream: that the server exited, with the last line it printed on
  stderr. That line comes from the server's log file, where every value Coffer
  injected is already masked (``stderr_mask``), and it is scrubbed of anything
  else shaped like a secret and cut short.
"""

from __future__ import annotations

import socket
import ssl

import httpx2
from mcp import types as mcp_types

from coffer.domain.mcp.config_summary import scrub
from coffer.infrastructure.logging.upstream_tail import read_upstream_tail

#: The longest stderr line a failure quotes.
STDERR_LINE_MAX = 200
#: How many of the newest log lines are searched for the server's own last line.
_TAIL_LINES = 20

_RESOLVE_HINTS = (
    "name or service not known",
    "nodename nor servname",
    "getaddrinfo",
    "name resolution",
    "no address associated",
)


def _chain(exc: BaseException) -> list[BaseException]:
    """``exc`` and what caused it, outermost first (each group's members too)."""
    out: list[BaseException] = []
    todo = [exc]
    while todo:
        cur = todo.pop(0)
        if any(cur is seen for seen in out):
            continue
        out.append(cur)
        if isinstance(cur, BaseExceptionGroup):
            todo.extend(cur.exceptions)
        for nxt in (cur.__cause__, cur.__context__):
            if nxt is not None:
                todo.append(nxt)
    return out


def _has_cause(
    exc: BaseException, kind: type[BaseException] | tuple[type[BaseException], ...]
) -> bool:
    return any(isinstance(cur, kind) for cur in _chain(exc))


def http_failure_kind(exc: BaseException) -> str:
    """What kind of network failure ``exc`` is. Only classified, never quoted:
    the text is read for a few fixed words and then dropped."""
    text = " ".join(str(cur) for cur in _chain(exc)).lower()
    if isinstance(exc, httpx2.ProxyError):
        return "the proxy refused the connection"
    if isinstance(exc, httpx2.ConnectTimeout):
        return "connecting timed out"
    if isinstance(exc, httpx2.TimeoutException):
        return "the server stopped answering mid-request"
    if isinstance(exc, httpx2.ConnectError):
        if _has_cause(exc, ssl.SSLError) or "ssl" in text or "certificate" in text:
            return "the TLS handshake failed"
        if _has_cause(exc, socket.gaierror) or any(hint in text for hint in _RESOLVE_HINTS):
            return "the server's host name does not resolve"
        if _has_cause(exc, ConnectionRefusedError) or "refused" in text:
            return "the connection was refused"
        return "could not connect"
    if isinstance(exc, httpx2.RemoteProtocolError):
        return "the server closed the connection mid-answer"
    if isinstance(exc, httpx2.HTTPError):
        return "the request failed on the network"
    return type(exc).__name__


def status_failure(status: int) -> str:
    return f"the server answered HTTP {status}"


def last_stderr_line(server_name: str) -> str | None:
    """The newest line the server itself printed, scrubbed and cut, if any."""
    try:
        tail = read_upstream_tail(server_name, _TAIL_LINES)
    except OSError:
        return None
    for line in tail.lines:  # newest first
        if line.source == "stderr" and line.text.strip():
            return scrub(line.text.strip())[:STDERR_LINE_MAX]
    return None


def exited_detail(server_name: str) -> str:
    """``the server exited`` and, when it printed one, its last stderr line."""
    line = last_stderr_line(server_name)
    return "the server exited" + (f"; its last stderr line: {line}" if line else "")


__all__ = [
    "STDERR_LINE_MAX",
    "exited_detail",
    "http_failure_kind",
    "last_stderr_line",
    "status_failure",
]


def leaf_exception(exc: BaseException) -> BaseException:
    """Unwrap single-member exception groups so the real transport error is named.

    anyio surfaces a crashed transport task as a (possibly nested)
    ExceptionGroup on scope exit; a one-leaf group is the one exception it
    carries.
    """
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


def request_failure(
    code: int, network: BaseException | None, last_status: int | None
) -> str | None:
    """Why an HTTP upstream's request failed, when it was the exchange and not
    the server answering with a JSON-RPC error: the network failure's kind, or
    the error status the upstream answered with. ``None`` for a real answer."""
    if code == mcp_types.CONNECTION_CLOSED:
        return http_failure_kind(network) if network is not None else "the connection closed"
    if last_status is not None and last_status >= 400:
        return status_failure(last_status)
    return None


def init_failure(
    leaf: BaseException, network: BaseException | None, first_error_status: int | None
) -> str | None:
    """Why an HTTP upstream's start failed, or None when nothing more is known."""
    if isinstance(leaf, httpx2.HTTPError):
        return http_failure_kind(leaf)
    if network is not None:
        return http_failure_kind(network)
    if first_error_status is not None:
        return status_failure(first_error_status)
    return None
