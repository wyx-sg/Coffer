"""Per-session lifecycle orchestration for upstream MCP connections.

Owned by an MCPGatewaySession (T054+). Each session has its own
SubprocessSupervisor so concurrent client sessions don't share upstream
subprocess state (ADR session-subprocess-model).
"""

from __future__ import annotations

import asyncio
import logging
import os
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
from coffer.domain.resource import Resource

# A factory the composition root injects to build connections without
# pulling the infrastructure adapters into the application layer.
# Signature: (transport, credentials_overlay, spawn_timeout, request_timeout,
#             resource) -> UpstreamConnectionPort.
#
# The whole ``Resource`` rather than its name because the connection needs both
# halves of a resource and for different reasons: the NAME is what a timeout
# message and the upstream's own stderr file are titled with — a uid there would
# make every diagnostic unreadable — while the UID is what the spawned process's
# PID file is recorded under, since that file has to name the same server after a
# rename (ADR resource-identity-is-an-immutable-uid).
UpstreamFactory = Callable[
    [
        HttpTransport | StdioTransport,
        dict[str, str],
        int,
        int,
        Resource,
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
# How many upstreams one supervisor cold-starts at the same time. A listing
# fan-out over N registered servers would otherwise open N subprocesses / N
# HTTP initialize handshakes at once; a few slow ones then starve the rest of
# CPU and file descriptors and push *every* spawn past its timeout.
_DEFAULT_MAX_CONCURRENT_SPAWNS = 4
_MAX_CONCURRENT_SPAWNS_ENV = "COFFER_MCP_MAX_CONCURRENT_SPAWNS"


def _max_concurrent_spawns_from_env() -> int:
    """Read ``COFFER_MCP_MAX_CONCURRENT_SPAWNS``; invalid or non-positive → default.

    Same knob style as ``reaper_kwargs_from_env``: env so a
    deployment can tune it without a code change, silently ignored when it
    does not parse.
    """
    value = _DEFAULT_MAX_CONCURRENT_SPAWNS
    if raw := os.environ.get(_MAX_CONCURRENT_SPAWNS_ENV):
        with suppress(ValueError):
            parsed = int(raw)
            if parsed > 0:
                value = parsed
    return value


@dataclass
class _UpstreamEntry:
    connection: UpstreamConnectionPort | None = None
    state: UpstreamHealth = UpstreamHealth.UNHEALTHY  # not yet attempted
    consecutive_failures: int = 0
    cooldown_until: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    spawn_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    #: Bumped by every eviction. A spawn reads it before starting and again
    #: when it finishes; a change means the connection it just built is for a
    #: registration that no longer exists, so it is closed instead of cached.
    #: This is what lets ``evict`` take no lock at all — see its docstring.
    generation: int = 0


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
        max_concurrent_spawns: int | None = None,  # None → env knob, else default
    ) -> None:
        self._resources = resource_service
        self._credentials = credential_resolver
        # The caller injects the upstream factory so application
        # code never imports infrastructure adapters. The composition root and
        # tests both inject ``coffer.infrastructure.mcp.factory.build_upstream``
        # (the importlib-hidden fallback that used to live here was deleted,
        # so the dependency is visible to importlinter again).
        self._upstream_factory = upstream_factory
        self._retry_delays = retry_delays
        self._cooldown_seconds = cooldown_seconds
        self._entries: dict[str, _UpstreamEntry] = {}
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        if max_concurrent_spawns is None or max_concurrent_spawns <= 0:
            max_concurrent_spawns = _max_concurrent_spawns_from_env()
        self._max_concurrent_spawns = max_concurrent_spawns
        # Bounds cold starts across DIFFERENT servers (spawn_lock is per
        # server). Held only around build + spawn_and_initialize, never across
        # a retry sleep or a cooldown, so a waiting-out server holds no slot.
        self._spawn_slots = asyncio.Semaphore(max_concurrent_spawns)

    @property
    def max_concurrent_spawns(self) -> int:
        """How many upstream cold starts this supervisor runs at once."""
        return self._max_concurrent_spawns

    def _now(self) -> datetime:
        return self._clock()

    def health(self, server_name: str) -> UpstreamHealth:
        entry = self._entries.get(server_name)
        return entry.state if entry else UpstreamHealth.UNHEALTHY

    def _enforce_cooldown(self, entry: _UpstreamEntry, server_name: str) -> None:
        """Raise if the entry is in an active cooldown; reset an expired one.

        Called both BEFORE acquiring spawn_lock (cheap fast-fail for the many
        waiters during cooldown) and AGAIN after acquiring it: a
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

    async def get_or_spawn(self, server_name: str) -> UpstreamConnectionPort:
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

            # Re-check cooldown under the lock: a racer ahead of us may
            # have just entered cooldown — don't restart the retry ladder.
            self._enforce_cooldown(entry, server_name)

            entry.state = UpstreamHealth.STARTING
            # Read BEFORE the ladder: anything that evicts while we are down
            # there is telling us the answer is no longer wanted.
            generation = entry.generation

            # Look up the config
            resource = await self._resources.get_by_name("mcp_server", server_name)
            if not resource.enabled:
                entry.state = UpstreamHealth.UNHEALTHY
                raise UpstreamUnavailable(f"{server_name!r} is disabled")
            # Per-agent scope is NOT enforced here: the supervisor has no
            # session context, and a server's per-agent scope is enforced at
            # the gateway (the seam that knows which agent is asking).

            config = MCPServerConfig.model_validate(resource.config)

            # Attempt with retry. Catch only the transient failure modes a
            # subprocess/HTTP-MCP spawn legitimately produces; let unexpected
            # exceptions (e.g. programming errors, ValueError from bad config,
            # asyncio.CancelledError from shutdown) propagate so they surface
            # to the caller instead of silently burning the retry budget.
            # asyncio.CancelledError is BaseException-derived, so
            # the `except Exception`-based clause below excludes it naturally
            # — the ladder stops on the spot, no retry sleep, no cooldown.
            last_error: Exception | None = None
            for attempt_idx in range(len(self._retry_delays) + 1):
                try:
                    async with self._spawn_slots:
                        conn = await self._build_connection(resource, config)
                        await conn.spawn_and_initialize()
                    if entry.generation != generation:
                        # Evicted while we were starting. Caching this would
                        # hand out a live subprocess for a server that has
                        # since been deleted or renamed — the exact leak the
                        # eviction was asked to prevent.
                        with suppress(Exception):
                            await conn.close()
                        raise UpstreamUnavailable(
                            f"{server_name!r} was evicted while it was starting"
                        )
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
        self, resource: Resource, config: MCPServerConfig
    ) -> UpstreamConnectionPort:
        if isinstance(config.transport, StdioTransport | HttpTransport):
            # materialize() is a synchronous, potentially-blocking
            # store read (sqlite, or the OS keychain in legacy setups).
            # Offload to a thread so a slow read can't freeze the whole
            # event loop and stall every other concurrent session.
            overlay = await asyncio.to_thread(
                self._credentials.materialize, config.transport.credential_refs
            )
            return self._upstream_factory(
                config.transport,
                overlay,
                config.spawn_timeout_seconds,
                config.request_timeout_seconds,
                resource,
            )
        raise UpstreamUnavailable(f"unsupported transport type: {type(config.transport).__name__}")

    async def evict(self, server_name: str) -> None:
        """Drop this server's connection — after a crash, a delete, or a rename.

        Deliberately takes **no lock**. ``get_or_spawn`` holds ``spawn_lock``
        across its whole retry ladder, which for a command that cannot speak
        MCP is every attempt and every backoff between them; queueing here
        behind it made deleting such a server wait for a subprocess nobody
        wanted the answer to any more. The browser saw a request that never
        came back.

        Waiting was never what eviction needed. The caller is saying this
        registration is finished, and a spawn still in flight for it is not a
        thing to be patient with — it is a thing to invalidate. So the
        generation counter goes up, which the spawner rechecks the moment it
        has a connection; whichever of the two finishes second cleans up after
        itself, and neither waits for the other.
        """
        entry = self._entries.get(server_name)
        if entry is None:
            return
        entry.generation += 1
        conn, entry.connection = entry.connection, None
        entry.state = UpstreamHealth.UNHEALTHY
        if conn is not None:
            with suppress(Exception):
                await conn.close()

    async def dispose(self) -> None:
        """Close all connections owned by this supervisor. Called on session end.

        Closes are intentionally SEQUENTIAL. The stdio/HTTP
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
