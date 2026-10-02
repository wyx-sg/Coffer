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
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from coffer.application.mcp.ports import UpstreamConnectionPort
from coffer.application.mcp.supervisor_failures import UpstreamFailureLedger
from coffer.application.resource_service import ResourceService
from coffer.application.secret.resolver import SecretResolver
from coffer.domain.errors import (
    UpstreamTimeout,
    UpstreamUnavailable,
)
from coffer.domain.mcp.secret_target import mcp_destination
from coffer.domain.mcp.server_config import AnyTransport, MCPServerConfig
from coffer.domain.resource import Resource

# A factory the composition root injects to build connections without
# pulling the infrastructure adapters into the application layer.
# Signature: (transport, secrets_overlay, spawn_timeout, request_timeout,
#             resource) -> UpstreamConnectionPort.
#
# The whole ``Resource`` rather than its name because the connection needs both
# halves of a resource and for different reasons: the NAME is what a timeout
# message and the upstream's own stderr file are titled with — a uid there would
# make every diagnostic unreadable — while the UID is what the spawned process's
# PID file is recorded under, since that file has to name the same server after a
# rename (ADR identity-is-the-uid-inside-the-file).
UpstreamFactory = Callable[
    [
        AnyTransport,
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


# Short on purpose: the ladder runs under the server's spawn lock, so every
# second of it is a second a caller waits. Waiting out a dead server is the
# ledger's backoff (minutes, shared by every session), not this ladder's job.
_RETRY_DELAYS_SECONDS = (1.0, 5.0)
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
        secret_resolver: SecretResolver,
        upstream_factory: UpstreamFactory,
        *,
        retry_delays: tuple[float, ...] = _RETRY_DELAYS_SECONDS,
        cooldown_seconds: int = _COOLDOWN_SECONDS,
        clock: Any = None,  # callable returning datetime; None → datetime.now(UTC)
        failures: UpstreamFailureLedger | None = None,  # shared across sessions
        max_concurrent_spawns: int | None = None,  # None → env knob, else default
    ) -> None:
        self._resources = resource_service
        self._secrets = secret_resolver
        # The caller injects the upstream factory so application
        # code never imports infrastructure adapters. The composition root and
        # tests both inject ``coffer.infrastructure.mcp.factory.build_upstream``
        # (the importlib-hidden fallback that used to live here was deleted,
        # so the dependency is visible to importlinter again).
        self._upstream_factory = upstream_factory
        self._retry_delays = retry_delays
        self._entries: dict[str, _UpstreamEntry] = {}
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        # The composition root passes ONE ledger to every session's supervisor
        # so a dead server is backed off once for the daemon, not once per
        # session. Alone (tests, scripts) a supervisor keeps its own.
        self._failures = failures or UpstreamFailureLedger(
            base_seconds=float(cooldown_seconds), clock=self._clock
        )
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

    @property
    def failures(self) -> UpstreamFailureLedger:
        """The failure ledger (backoff and circuit-breaker state) behind this supervisor."""
        return self._failures

    def health(self, server_name: str) -> UpstreamHealth:
        entry = self._entries.get(server_name)
        return entry.state if entry else UpstreamHealth.UNHEALTHY

    def _enforce_cooldown(self, entry: _UpstreamEntry, server_name: str) -> None:
        """Raise while the shared failure ledger says this server is backing off.

        Called both BEFORE acquiring spawn_lock (cheap fast-fail for the many
        waiters during a backoff) and AGAIN after acquiring it: a concurrent
        caller may have exhausted the retry ladder while we were queued on the
        lock. Without the second check every waiter re-ran the entire ladder.
        The ledger is shared by every session's supervisor, so a second session
        asking for the same dead server fails here too instead of trying again.
        """
        rec = self._failures.backing_off(server_name)
        if rec is None:
            if entry.state == UpstreamHealth.COOLDOWN:
                entry.state = UpstreamHealth.UNHEALTHY  # backoff elapsed: try again
            return
        entry.state = UpstreamHealth.COOLDOWN
        assert rec.retry_at is not None
        flag = " (failing)" if rec.failing else ""
        raise UpstreamUnavailable(
            f"{server_name!r} is unreachable{flag}; the last error was {rec.last_error}. "
            f"Next attempt after {rec.retry_at.isoformat()} "
            f"({rec.consecutive_failures} failed in a row)"
        )

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

            try:
                return await self._spawn_under_lock(entry, server_name)
            finally:
                if entry.state == UpstreamHealth.STARTING:
                    # Left by anything the ladder does not catch — a secret
                    # awaiting approval, a cancel: nothing is starting.
                    entry.state = UpstreamHealth.UNHEALTHY

    async def _spawn_under_lock(
        self, entry: _UpstreamEntry, server_name: str
    ) -> UpstreamConnectionPort:
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
                    try:
                        await conn.spawn_and_initialize()
                    except BaseException:
                        # Cancelled (the listing budget, a shutdown) or
                        # failed: the half-open child, its pipes and its pid
                        # file must not outlive the attempt.
                        with suppress(Exception):
                            await conn.close()
                        raise
                if entry.generation != generation:
                    # Evicted while we were starting. Caching this would
                    # hand out a live subprocess for a server that has
                    # since been deleted or renamed — the exact leak the
                    # eviction was asked to prevent.
                    with suppress(Exception):
                        await conn.close()
                    raise UpstreamUnavailable(f"{server_name!r} was evicted while it was starting")
                entry.connection = conn
                entry.state = UpstreamHealth.HEALTHY
                self._failures.record_success(server_name)
                return conn
            except (
                UpstreamUnavailable,
                UpstreamTimeout,
                OSError,
                ConnectionError,
                TimeoutError,
            ) as e:
                last_error = e
                # Loud only for the first ladder of a streak; the circuit
                # breaker's own "mcp.upstream.failing" line speaks for the
                # rest, so a dead server does not fill the log.
                known = self._failures.get(server_name)
                _logger.log(
                    logging.DEBUG if known and known.failing else logging.WARNING,
                    "mcp.upstream.spawn_failed",
                    extra={
                        "server": server_name,
                        "attempt": attempt_idx + 1,
                        "error": str(e),
                    },
                )
                if attempt_idx < len(self._retry_delays):
                    await asyncio.sleep(self._retry_delays[attempt_idx])

        # All retries exhausted — back off (shared by every session)
        self._failures.record_failure(server_name, str(last_error))
        entry.state = UpstreamHealth.COOLDOWN
        entry.connection = None
        raise UpstreamUnavailable(
            f"{server_name!r} failed to spawn after "
            f"{len(self._retry_delays) + 1} attempts: {last_error}"
        )

    async def _build_connection(
        self, resource: Resource, config: MCPServerConfig
    ) -> UpstreamConnectionPort:
        # materialize() is a synchronous, potentially-blocking store read
        # (the encrypted store). Offload to a thread
        # so a slow read can't freeze the whole event loop and stall every
        # other concurrent session. Named destination: the boundary injects
        # nothing into a target nobody approved (spec secret "Hold a
        # secret for a new destination until a person approves it") — for a
        # custom-tool group the target is its base URL.
        overlay = await asyncio.to_thread(
            self._secrets.materialize,
            config.transport.secret_refs,
            mcp_destination(resource.uid, resource.name, config),
        )
        return self._upstream_factory(
            config.transport,
            overlay,
            config.spawn_timeout_seconds,
            config.request_timeout_seconds,
            resource,
        )

    async def evict(self, server_name: str) -> None:
        """Drop this server's connection — after a crash, a delete or an edit.

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
        # An edit or a delete is the person answering whatever was failing.
        self._failures.forget(server_name)
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
