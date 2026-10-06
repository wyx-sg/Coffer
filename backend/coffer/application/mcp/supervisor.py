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

from coffer.application.mcp.custom_tool_secrets import env_secret_resolver
from coffer.application.mcp.ports import UpstreamConnectionPort
from coffer.application.mcp.supervisor_failures import UpstreamFailureLedger
from coffer.application.resource_service import ResourceService
from coffer.application.secret.resolver import SecretResolver
from coffer.domain.errors import (
    UpstreamAuthRejected,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from coffer.domain.mcp.http_api import HttpApiTransport
from coffer.domain.mcp.secret_target import mcp_destination
from coffer.domain.mcp.server_config import AnyTransport, MCPServerConfig
from coffer.domain.resource import Resource

# (transport, secrets_overlay, spawn_timeout, request_timeout, resource) ->
# connection, injected by the composition root. The whole ``Resource``: the NAME
# titles diagnostics and the stderr file, the UID names the child's PID file
# (ADR identity-is-the-uid-inside-the-file).
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

#: uids of servers being deleted, consulted by EVERY supervisor in the process.
#: The delete hook runs before the row is removed, so a spawn starting after its
#: own supervisor was evicted — or in a session the hook never walked — still
#: finds the row; this is what refuses it. A uid is never reissued.
_retired_uids: set[str] = set()


def retire_server(uid: str) -> None:
    """Refuse and close every connection to ``uid`` from now on, in every session."""
    _retired_uids.add(uid)


def restore_server(uid: str) -> None:
    """Lift :func:`retire_server` for a server that turned out to still exist."""
    _retired_uids.discard(uid)


class _Evicted(UpstreamUnavailable):
    """The connection being started was evicted; retrying cannot help."""


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
    """Read ``COFFER_MCP_MAX_CONCURRENT_SPAWNS``; invalid or non-positive → default."""
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
        # ``coffer.infrastructure.mcp.factory.build_upstream`` in production.
        self._upstream_factory = upstream_factory
        self._retry_delays = retry_delays
        self._entries: dict[str, _UpstreamEntry] = {}
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._disposed = False
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
        #: Run on every connection this supervisor builds, BEFORE it starts: the
        #: SDK fixes a session's sampling/roots callbacks when it is constructed.
        self.prepare_connection: Callable[[str, UpstreamConnectionPort], None] | None = None

    @property
    def max_concurrent_spawns(self) -> int:
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
        if self._disposed:
            raise UpstreamUnavailable(f"{server_name!r}: this session has ended")
        entry = self._entries.setdefault(server_name, _UpstreamEntry())
        # Checked BEFORE spawn_lock too, so waiters during a cooldown never queue.
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
        if resource.uid in _retired_uids:
            entry.state = UpstreamHealth.UNHEALTHY
            raise UpstreamUnavailable(f"{server_name!r} is being deleted")
        # Per-agent scope is enforced at the gateway, which knows the agent.
        config = MCPServerConfig.model_validate(resource.config)

        # Retry only the transient failures a spawn legitimately produces;
        # anything else (bad config, a bug, CancelledError) propagates at once.
        last_error: Exception | None = None
        for attempt_idx in range(len(self._retry_delays) + 1):
            try:
                async with self._spawn_slots:
                    conn = await self._build_connection(resource, config)
                    if self.prepare_connection is not None:
                        self.prepare_connection(server_name, conn)
                    try:
                        await conn.spawn_and_initialize()
                    except BaseException:
                        # Cancelled (the listing budget, a shutdown) or
                        # failed: the half-open child, its pipes and its pid
                        # file must not outlive the attempt.
                        with suppress(Exception):
                            await conn.close()
                        raise
                if entry.generation != generation or resource.uid in _retired_uids:
                    # Evicted, deleted or its session ended while starting:
                    # caching it would leave a child nothing will ever close.
                    with suppress(Exception):
                        await conn.close()
                    raise _Evicted(f"{server_name!r} was evicted while it was starting")
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
                if isinstance(e, _Evicted):
                    raise  # not a failure of the server: no retry, no backoff
                last_error = e
                if isinstance(e, UpstreamAuthRejected):
                    # Asking again with the same key cannot succeed.
                    break
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
        # A refused key keeps its own type, so the gateway can say so in health.
        failure = (
            UpstreamAuthRejected
            if isinstance(last_error, UpstreamAuthRejected)
            else UpstreamUnavailable
        )
        raise failure(
            f"{server_name!r} failed to spawn after "
            f"{len(self._retry_delays) + 1} attempts: {last_error}"
        )

    async def _build_connection(
        self, resource: Resource, config: MCPServerConfig
    ) -> UpstreamConnectionPort:
        transport = config.transport
        if isinstance(transport, HttpApiTransport):
            # A custom-tool group resolves secrets per call, for the one
            # environment the call names (spec mcp-gateway "Wait for approval
            # before a custom tool sends its secret"): a missing or unapproved
            # secret in one environment must not stop the others, so nothing
            # is resolved here.
            conn = self._upstream_factory(
                transport,
                {},
                config.spawn_timeout_seconds,
                config.request_timeout_seconds,
                resource,
            )
            use = getattr(conn, "use_env_secrets", None)
            if use is not None:
                use(env_secret_resolver(self._secrets, resource))
            return conn
        # materialize() is a synchronous, potentially-blocking store read
        # (the encrypted store). Offload to a thread
        # so a slow read can't freeze the whole event loop and stall every
        # other concurrent session. Named destination: the boundary injects
        # nothing into a target nobody approved (spec secret "Hold a
        # secret for a new destination until a person approves it").
        overlay = await asyncio.to_thread(
            self._secrets.materialize,
            transport.secret_refs,
            mcp_destination(resource.uid, resource.name, config),
        )
        return self._upstream_factory(
            transport,
            overlay,
            config.spawn_timeout_seconds,
            config.request_timeout_seconds,
            resource,
        )

    async def evict(self, server_name: str) -> None:
        """Drop this server's connection — after a crash, a delete or an edit.

        Deliberately takes **no lock**: ``get_or_spawn`` holds ``spawn_lock``
        across its whole retry ladder, and deleting a server that cannot speak
        MCP used to wait out that ladder. A spawn in flight is invalidated
        instead — the generation goes up, the spawner rechecks it the moment it
        has a connection, and whichever finishes second cleans up.
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

        A spawn still in flight sees its entry's generation move and closes
        what it built, and nothing spawns here afterwards.
        """
        self._disposed = True
        for _name, entry in list(self._entries.items()):
            entry.generation += 1
            if entry.connection is not None:
                with suppress(Exception):
                    await entry.connection.close()
            entry.connection = None
            entry.state = UpstreamHealth.UNHEALTHY
        self._entries.clear()
