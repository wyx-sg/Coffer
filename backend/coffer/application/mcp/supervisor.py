"""Per-session lifecycle orchestration for upstream MCP connections.

Owned by an MCPGatewaySession (T054+). Each session has its own
SubprocessSupervisor so concurrent client sessions don't share upstream
subprocess state ([ADR-005](../../../../docs/decisions/ADR-005-session-subprocess-model.md)).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from coffer.application.mcp.credential_resolver import CredentialResolver
from coffer.application.mcp.ports import UpstreamConnectionPort
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import (
    UpstreamTimeout,
    UpstreamUnavailable,
)
from coffer.domain.mcp.server_config import (
    HttpTransport,
    MCPServerConfig,
    StdioTransport,
)
from coffer.domain.resource import ResourceRef

# A factory the composition root injects to build connections without
# pulling the infrastructure adapters into the application layer (CODE-005).
# Signature: (transport, credentials_overlay, spawn_timeout, request_timeout,
#             server_name) -> UpstreamConnectionPort.
UpstreamFactory = Callable[
    [
        HttpTransport | StdioTransport,
        dict[str, str],
        int,
        int,
        str,
    ],
    UpstreamConnectionPort,
]

_logger = logging.getLogger(__name__)


def _default_upstream_factory(
    transport: HttpTransport | StdioTransport,
    overlay: dict[str, str],
    spawn_timeout: int,
    request_timeout: int,
    server_name: str,
) -> UpstreamConnectionPort:
    """Lazy-resolve the infrastructure adapters as a constructor fallback.

    Uses :func:`importlib.import_module` so the dependency is invisible to
    importlinter's static analysis — composition root SHOULD inject the
    factory explicitly (see ``surfaces/http/app.py::_build_upstream``); this
    fallback exists only so legacy in-tree tests/fixtures keep compiling.
    """
    import importlib

    if isinstance(transport, StdioTransport):
        mod = importlib.import_module("coffer.infrastructure.mcp.subprocess")
        cls = mod.StdioUpstreamConnection
        conn: UpstreamConnectionPort = cls(
            transport=transport,
            env_overlay=overlay,
            spawn_timeout_seconds=spawn_timeout,
            request_timeout_seconds=request_timeout,
            server_name=server_name,
        )
        return conn
    mod = importlib.import_module("coffer.infrastructure.mcp.http_client")
    cls = mod.HttpUpstreamConnection
    http_conn: UpstreamConnectionPort = cls(
        transport=transport,
        header_overlay=overlay,
        spawn_timeout_seconds=spawn_timeout,
        request_timeout_seconds=request_timeout,
    )
    return http_conn


class UpstreamHealth(StrEnum):
    HEALTHY = "healthy"
    STARTING = "starting"
    UNHEALTHY = "unhealthy"
    COOLDOWN = "cooldown"


_RETRY_DELAYS_SECONDS = (1.0, 5.0, 30.0)
_COOLDOWN_SECONDS = 60


# Re-export the port under the legacy name so existing callers that imported
# ``UpstreamConnection`` from this module keep compiling unchanged.
UpstreamConnection = UpstreamConnectionPort


@dataclass
class _UpstreamEntry:
    connection: UpstreamConnectionPort | None = None
    state: UpstreamHealth = UpstreamHealth.UNHEALTHY  # not yet attempted
    consecutive_failures: int = 0
    cooldown_until: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    spawn_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SubprocessSupervisor:
    """One-per-session orchestrator over upstream connections."""

    def __init__(
        self,
        resource_service: ResourceService,
        credential_resolver: CredentialResolver,
        upstream_factory: UpstreamFactory | None = None,
        *,
        retry_delays: tuple[float, ...] = _RETRY_DELAYS_SECONDS,
        cooldown_seconds: int = _COOLDOWN_SECONDS,
        clock: Any = None,  # callable returning datetime; None → datetime.now(UTC)
    ) -> None:
        self._resources = resource_service
        self._credentials = credential_resolver
        # CODE-005: the composition root injects the upstream factory so we
        # don't import infrastructure adapters from application code. The
        # ``None`` fallback uses a dynamic import (``importlib.import_module``)
        # purely so this constructor keeps working in tests/fixtures that
        # predate the explicit-factory plumbing; the lazy import is hidden
        # from importlinter by construction.
        self._upstream_factory = upstream_factory or _default_upstream_factory
        self._retry_delays = retry_delays
        self._cooldown_seconds = cooldown_seconds
        self._entries: dict[str, _UpstreamEntry] = {}
        self._clock = clock or (lambda: datetime.now(tz=UTC))

    def _now(self) -> datetime:
        return self._clock()

    def health(self, server_name: str) -> UpstreamHealth:
        entry = self._entries.get(server_name)
        return entry.state if entry else UpstreamHealth.UNHEALTHY

    async def get_or_spawn(self, server_name: str) -> UpstreamConnection:
        """Return a live connection for `server_name`, lazily spawning if needed.

        Raises UpstreamUnavailable if the server is currently in cooldown
        or if all retry attempts fail.
        """
        entry = self._entries.setdefault(server_name, _UpstreamEntry())

        # Cooldown gate — checked BEFORE acquiring spawn_lock to avoid
        # blocking many waiters during cooldown.
        if entry.state == UpstreamHealth.COOLDOWN:
            if entry.cooldown_until and self._now() < entry.cooldown_until:
                raise UpstreamUnavailable(
                    f"{server_name!r} is in cooldown until {entry.cooldown_until.isoformat()}"
                )
            # Cooldown elapsed — reset and let the spawn proceed
            entry.state = UpstreamHealth.UNHEALTHY
            entry.consecutive_failures = 0
            entry.cooldown_until = None

        async with entry.spawn_lock:
            # Re-check after acquiring the lock: another coroutine may have spawned.
            if entry.connection is not None and entry.state == UpstreamHealth.HEALTHY:
                return entry.connection

            entry.state = UpstreamHealth.STARTING

            # Look up the config
            resource = await self._resources.get(ResourceRef("mcp_server", server_name))
            if not resource.enabled:
                entry.state = UpstreamHealth.UNHEALTHY
                raise UpstreamUnavailable(f"{server_name!r} is disabled")
            config = MCPServerConfig.model_validate(resource.config)

            # Attempt with retry. Catch only the transient failure modes a
            # subprocess/HTTP-MCP spawn legitimately produces; let unexpected
            # exceptions (e.g. programming errors, ValueError from bad config,
            # asyncio.CancelledError from shutdown) propagate so they surface
            # to the caller instead of silently burning the retry budget
            # (CODE-003). asyncio.CancelledError is BaseException-derived, so
            # the `except Exception`-based clause below excludes it naturally.
            last_error: Exception | None = None
            for attempt_idx in range(len(self._retry_delays) + 1):
                try:
                    conn = await self._build_connection(server_name, config)
                    await conn.spawn_and_initialize()
                    entry.connection = conn
                    entry.state = UpstreamHealth.HEALTHY
                    entry.consecutive_failures = 0
                    entry.last_success_at = self._now()
                    return conn
                except (
                    UpstreamUnavailable,
                    UpstreamTimeout,
                    OSError,
                    ConnectionError,
                    TimeoutError,
                ) as e:
                    last_error = e
                    entry.consecutive_failures += 1
                    entry.last_failure_at = self._now()
                    _logger.warning(
                        "mcp.upstream.spawn_failed",
                        extra={
                            "server": server_name,
                            "attempt": attempt_idx + 1,
                            "error": str(e),
                        },
                    )
                    if attempt_idx < len(self._retry_delays):
                        await asyncio.sleep(self._retry_delays[attempt_idx])

            # All retries exhausted — enter cooldown
            entry.state = UpstreamHealth.COOLDOWN
            entry.cooldown_until = self._now() + timedelta(seconds=self._cooldown_seconds)
            entry.connection = None
            raise UpstreamUnavailable(
                f"{server_name!r} failed to spawn after "
                f"{len(self._retry_delays) + 1} attempts: {last_error}"
            )

    async def _build_connection(
        self, server_name: str, config: MCPServerConfig
    ) -> UpstreamConnectionPort:
        if isinstance(config.transport, StdioTransport | HttpTransport):
            overlay = self._credentials.materialize(config.transport.credential_refs)
            return self._upstream_factory(
                config.transport,
                overlay,
                config.spawn_timeout_seconds,
                config.request_timeout_seconds,
                server_name,
            )
        raise UpstreamUnavailable(f"unsupported transport type: {type(config.transport).__name__}")

    async def evict(self, server_name: str) -> None:
        """Forcefully close a connection (e.g., after a crash detected during request())."""
        entry = self._entries.get(server_name)
        if entry is None:
            return
        async with entry.spawn_lock:
            if entry.connection is not None:
                with suppress(Exception):
                    await entry.connection.close()
                entry.connection = None
            entry.state = UpstreamHealth.UNHEALTHY

    async def dispose(self) -> None:
        """Close all connections owned by this supervisor. Called on session end."""
        for _name, entry in list(self._entries.items()):
            if entry.connection is not None:
                with suppress(Exception):
                    await entry.connection.close()
            entry.connection = None
            entry.state = UpstreamHealth.UNHEALTHY
        self._entries.clear()
