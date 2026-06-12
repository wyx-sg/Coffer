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

from coffer.application.credentials.resolver import CredentialResolver
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
        upstream_factory: UpstreamFactory,
        *,
        retry_delays: tuple[float, ...] = _RETRY_DELAYS_SECONDS,
        cooldown_seconds: int = _COOLDOWN_SECONDS,
        clock: Any = None,  # callable returning datetime; None → datetime.now(UTC)
    ) -> None:
        self._resources = resource_service
        self._credentials = credential_resolver
        # CODE-005: the caller injects the upstream factory so application
        # code never imports infrastructure adapters. The composition root and
        # tests both inject ``coffer.infrastructure.mcp.factory.build_upstream``
        # (the importlib-hidden fallback that used to live here was deleted —
        # CODE-L3 — so the dependency is visible to importlinter again).
        self._upstream_factory = upstream_factory
        self._retry_delays = retry_delays
        self._cooldown_seconds = cooldown_seconds
        self._entries: dict[str, _UpstreamEntry] = {}
        self._clock = clock or (lambda: datetime.now(tz=UTC))

    def _now(self) -> datetime:
        return self._clock()

    def health(self, server_name: str) -> UpstreamHealth:
        entry = self._entries.get(server_name)
        return entry.state if entry else UpstreamHealth.UNHEALTHY

    def _enforce_cooldown(self, entry: _UpstreamEntry, server_name: str) -> None:
        """Raise if the entry is in an active cooldown; reset an expired one.

        Called both BEFORE acquiring spawn_lock (cheap fast-fail for the many
        waiters during cooldown) and AGAIN after acquiring it (CODE-H1): a
        concurrent caller may have exhausted the retry ladder and entered
        cooldown while we were queued on the lock. Without the second check,
        every waiter re-ran the entire ladder, amplifying the work N-fold and
        wedging a session's tool calls for minutes against a single dead
        upstream.
        """
        if entry.state == UpstreamHealth.COOLDOWN:
            if entry.cooldown_until and self._now() < entry.cooldown_until:
                raise UpstreamUnavailable(
                    f"{server_name!r} is in cooldown until {entry.cooldown_until.isoformat()}"
                )
            # Cooldown elapsed — reset and let the spawn proceed
            entry.state = UpstreamHealth.UNHEALTHY
            entry.consecutive_failures = 0
            entry.cooldown_until = None

    async def get_or_spawn(self, server_name: str) -> UpstreamConnection:
        """Return a live connection for `server_name`, lazily spawning if needed.

        Raises UpstreamUnavailable if the server is currently in cooldown
        or if all retry attempts fail.
        """
        entry = self._entries.setdefault(server_name, _UpstreamEntry())

        # Cooldown gate — checked BEFORE acquiring spawn_lock to avoid
        # blocking many waiters during cooldown.
        self._enforce_cooldown(entry, server_name)

        async with entry.spawn_lock:
            # Re-check after acquiring the lock: another coroutine may have spawned.
            if entry.connection is not None and entry.state == UpstreamHealth.HEALTHY:
                return entry.connection

            # Re-check cooldown under the lock (CODE-H1): a racer ahead of us may
            # have just entered cooldown — don't restart the retry ladder.
            self._enforce_cooldown(entry, server_name)

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
            # CODE-034: keyring.get() is a synchronous, potentially-blocking OS
            # keychain call (macOS securityd can stall on first-unlock/IPC).
            # Offload to a thread so a slow/locked keychain can't freeze the
            # whole event loop and stall every other concurrent session.
            overlay = await asyncio.to_thread(
                self._credentials.materialize, config.transport.credential_refs
            )
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
        """Close all connections owned by this supervisor. Called on session end.

        CODE-037 note: closes are intentionally SEQUENTIAL. The stdio/HTTP
        upstreams wrap an mcp ClientSession inside an anyio task group; that
        group's cancel scope is bound to the task that opened it, and aclosing
        it from a child task (as ``asyncio.gather`` would require) raises
        anyio's "cancel scope in a different task" error. Each close() is
        already bounded by its own ~5s teardown timeout, so a hung upstream
        cannot stall shutdown unboundedly even serially.
        """
        for _name, entry in list(self._entries.items()):
            if entry.connection is not None:
                with suppress(Exception):
                    await entry.connection.close()
            entry.connection = None
            entry.state = UpstreamHealth.UNHEALTHY
        self._entries.clear()
