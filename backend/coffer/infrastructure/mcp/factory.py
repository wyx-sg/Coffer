"""Concrete upstream-connection factory.

Bridges the application layer's ``UpstreamFactory`` port (see
``coffer.application.mcp.supervisor``) to the two infrastructure adapters.
Lives in infrastructure so both the composition root and integration tests
can inject it explicitly — the supervisor itself never imports adapters,
and there is no hidden importlib fallback.
"""

from __future__ import annotations

from coffer.domain.mcp.server_config import HttpTransport, StdioTransport
from coffer.domain.resource import Resource
from coffer.infrastructure.mcp.http_client import HttpUpstreamConnection
from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection


def build_upstream(
    transport: HttpTransport | StdioTransport,
    overlay: dict[str, str],
    spawn_timeout: int,
    request_timeout: int,
    server: Resource,
) -> StdioUpstreamConnection | HttpUpstreamConnection:
    """Build the right upstream connection for ``transport``.

    The resource is split here, once, into the two things a connection actually
    needs. ``server.name`` is the LABEL: it titles the upstream's stderr file and
    every timeout message the user reads, and those would become unreadable if
    they carried a uuid. ``server.uid`` is the IDENTITY: the stdio adapter
    records a PID file per spawned child, and that file has to keep naming the
    same server after a rename (ADR resource-identity-is-an-immutable-uid). The
    HTTP adapter spawns nothing, so it is handed only the label.
    """
    if isinstance(transport, StdioTransport):
        return StdioUpstreamConnection(
            transport=transport,
            env_overlay=overlay,
            spawn_timeout_seconds=spawn_timeout,
            request_timeout_seconds=request_timeout,
            server_name=server.name,
            server_uid=server.uid,
        )
    return HttpUpstreamConnection(
        transport=transport,
        header_overlay=overlay,
        spawn_timeout_seconds=spawn_timeout,
        request_timeout_seconds=request_timeout,
        server_name=server.name,
    )
