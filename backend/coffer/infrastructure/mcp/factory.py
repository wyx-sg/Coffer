"""Concrete upstream-connection factory.

Bridges the application layer's ``UpstreamFactory`` port (see
``coffer.application.mcp.supervisor``) to the two infrastructure adapters.
Lives in infrastructure so both the composition root and integration tests
can inject it explicitly — the supervisor itself never imports adapters
(CODE-005), and there is no hidden importlib fallback (CODE-L3).
"""

from __future__ import annotations

from coffer.domain.mcp.server_config import HttpTransport, StdioTransport
from coffer.infrastructure.mcp.http_client import HttpUpstreamConnection
from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection


def build_upstream(
    transport: HttpTransport | StdioTransport,
    overlay: dict[str, str],
    spawn_timeout: int,
    request_timeout: int,
    server_name: str,
) -> StdioUpstreamConnection | HttpUpstreamConnection:
    """Build the right upstream connection for ``transport``."""
    if isinstance(transport, StdioTransport):
        return StdioUpstreamConnection(
            transport=transport,
            env_overlay=overlay,
            spawn_timeout_seconds=spawn_timeout,
            request_timeout_seconds=request_timeout,
            server_name=server_name,
        )
    return HttpUpstreamConnection(
        transport=transport,
        header_overlay=overlay,
        spawn_timeout_seconds=spawn_timeout,
        request_timeout_seconds=request_timeout,
    )
