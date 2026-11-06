"""Map an HTTP upstream's failure to start onto a domain error.

httpx2 and transport exceptions can embed the request URL (which may carry a
query-string secret) or reflected headers, so the message names only the
exception type and, from ``failure_detail``, the kind of failure in Coffer's
words; callers chain the original via ``from``.
"""

from __future__ import annotations

import asyncio

import httpx2

from coffer.domain.errors import UpstreamAuthRejected, UpstreamTimeout, UpstreamUnavailable
from coffer.infrastructure.mcp.failure_detail import init_failure, leaf_exception

#: The statuses that say the key or token the upstream was given is refused.
AUTH_STATUSES = (401, 403)


def auth_rejected(name: str, status: int | None) -> UpstreamAuthRejected:
    return UpstreamAuthRejected(f"MCP server {name!r} rejected its credentials (HTTP {status})")


def init_error(
    exc: BaseException,
    *,
    name: str,
    spawn_timeout: int,
    first_error_status: int | None,
    network: BaseException | None,
) -> UpstreamAuthRejected | UpstreamTimeout | UpstreamUnavailable:
    """The domain error for a lifetime task that failed to initialize."""
    leaf = leaf_exception(exc)
    if first_error_status in AUTH_STATUSES:
        return auth_rejected(name, first_error_status)
    if isinstance(leaf, httpx2.TimeoutException):
        return UpstreamTimeout(
            f"MCP server {name!r} did not finish starting within "
            f"{spawn_timeout}s (its spawn timeout)"
        )
    if isinstance(leaf, asyncio.CancelledError):
        # anyio delivers a crashed transport task to the awaiting coroutine
        # as a CancelledError; when scope exit surfaced nothing better,
        # this is all we know.
        return UpstreamUnavailable(f"upstream init cancelled: {type(leaf).__name__}")
    reason = init_failure(leaf, network, first_error_status)
    detail = f" ({reason})" if reason is not None else ""
    return UpstreamUnavailable(f"upstream init failed: {type(leaf).__name__}{detail}")
