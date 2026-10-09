"""The ``/mcp`` route's session state: what each downstream client's session
holds, and how an idle one is dropped.

Process-local, one entry per session id: the gateway session, its notification
queue, last activity, in-flight POST count and the stop signal for its SSE
stream. ``protocol_routes`` owns the HTTP handlers; this module owns the
bookkeeping and the idle reaper (spec mcp-gateway "Take the agent identity from
the handshake" says what a dropped session must not silently become).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable

from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.runtime.supervisor import spawn
from coffer.application.runtime.wakeable import WakeableLoop
from coffer.application.runtime.workers import WorkerMode

_logger = logging.getLogger(__name__)

# A notification-queue caps the worst-case memory a misbehaving upstream can
# consume while no downstream client is draining the SSE stream. When the
# queue is full we drop the oldest message — keeping the latest event is
# more useful than blocking the upstream.
_QUEUE_MAXSIZE = 1000

# Default idle timeout for the session reaper. A session is considered idle
# when neither a downstream POST nor a forwarded upstream notification has
# touched it for this many seconds; holding a GET stream open is not activity.
# Each session owns its own upstream connections, so a short window bounds what
# an abandoned client costs; a client that comes back after it is dropped gets
# 404 and handshakes again. The ``start_session_reaper``
# constructor knobs override these; env wiring is
# ``COFFER_MCP_SESSION_IDLE_S`` / ``COFFER_MCP_SESSION_REAPER_INTERVAL_S``.
_DEFAULT_IDLE_TIMEOUT_S = 10 * 60

# How often an idle SSE stream wakes to re-check for a stop signal; it does not
# refresh the session's idle timer.
_STREAM_KEEPALIVE_S = 15

# How often the session reaper wakes up.
_REAPER_INTERVAL_S = 60

# Per-session notification queues (process-local).
# Key: session_id; Value: bounded asyncio.Queue[str] of pre-serialised JSON payloads.
_NOTIFICATION_QUEUES: dict[str, asyncio.Queue[str]] = {}

# Per-session MCPGatewaySession instances.
_ACTIVE_SESSIONS: dict[str, MCPGatewaySession] = {}

# Per-session last-activity timestamp (time.monotonic()). Updated on every
# downstream POST and every upstream-originated sink push (never by an open
# stream or its keepalive wake-up). Used by the
# session reaper to evict idle sessions.
_LAST_ACTIVITY: dict[str, float] = {}

# Per-session in-flight POST refcount. _drop_session() waits for this to
# reach zero before disposing the gateway session so a concurrent POST
# handler that is mid-request never sees a half-disposed session.
# Keyed by session_id; absent entries imply 0 refs.
_SESSION_REFS: dict[str, int] = {}
# Per-session lock guarding the dispose path so only one _drop_session
# runs at a time per session. asyncio.Lock is cheap and lives for the
# session's lifetime.
_SESSION_DISPOSE_LOCKS: dict[str, asyncio.Lock] = {}

# Per-session "stream should stop" signal. An idle GET /mcp SSE
# generator parks on ``queue.get()``; when the reaper drops the session it
# pops the queue but the generator keeps its own reference and would block
# forever, leaking the HTTP connection + task. _drop_session sets this event
# so the parked generator wakes and terminates cleanly.
_SESSION_STREAM_STOP: dict[str, asyncio.Event] = {}


def _stream_stop_event(session_id: str) -> asyncio.Event:
    return _SESSION_STREAM_STOP.setdefault(session_id, asyncio.Event())


def _touch(session_id: str) -> None:
    _LAST_ACTIVITY[session_id] = time.monotonic()
    if _REAPER is not None:
        _REAPER.set_demand(True)


def _acquire_session_ref(session_id: str) -> None:
    _SESSION_REFS[session_id] = _SESSION_REFS.get(session_id, 0) + 1


def _release_session_ref(session_id: str) -> None:
    current = _SESSION_REFS.get(session_id, 0)
    if current <= 1:
        _SESSION_REFS.pop(session_id, None)
    else:
        _SESSION_REFS[session_id] = current - 1


def _release_stream(session_id: str) -> None:
    """Tear down per-stream state for a closed SSE connection, leaving the
    session itself intact for reuse / the idle reaper.

    A single stream-stop event is shared per session id; clearing it (rather
    than popping it) keeps the same object the next GET looks up via
    ``_stream_stop_event`` while ensuring that next stream starts un-signalled.
    """
    if (ev := _SESSION_STREAM_STOP.get(session_id)) is not None:
        ev.clear()


# Maximum number of 100ms polls _drop_session will perform waiting for an
# in-flight POST to release its refcount before forcibly disposing.
_DROP_WAIT_MAX_POLLS = 50


async def _drop_session(session_id: str) -> None:
    """Dispose a session, waiting for any in-flight POST to drain first.

    Concurrent POST handlers acquire a refcount via ``_acquire_session_ref``;
    this function spins (up to ~5 s) until that count is zero and then
    swaps the session out atomically inside a per-session lock so two
    concurrent _drop_session calls cannot double-dispose.
    """
    lock = _SESSION_DISPOSE_LOCKS.setdefault(session_id, asyncio.Lock())
    async with lock:
        # Wake any parked SSE generator for this session so it
        # terminates instead of blocking forever on the about-to-be-dropped
        # queue. Set before the refcount wait so the stream unwinds promptly.
        if (ev := _SESSION_STREAM_STOP.get(session_id)) is not None:
            ev.set()

        # Wait briefly for in-flight POSTs to release their refcount. We
        # bound the wait so a stuck handler can't keep memory pinned forever.
        for _ in range(_DROP_WAIT_MAX_POLLS):
            if _SESSION_REFS.get(session_id, 0) == 0:
                break
            await asyncio.sleep(0.1)

        session = _ACTIVE_SESSIONS.pop(session_id, None)
        _NOTIFICATION_QUEUES.pop(session_id, None)
        _LAST_ACTIVITY.pop(session_id, None)
        _SESSION_REFS.pop(session_id, None)
        _SESSION_STREAM_STOP.pop(session_id, None)
        if session is not None:
            with contextlib.suppress(Exception):
                await session.dispose()
    # Drop the lock entry only after release so future _drop_session calls
    # for the same id (rare; usually a no-op anyway) get a fresh lock.
    _SESSION_DISPOSE_LOCKS.pop(session_id, None)


async def shutdown_all_sessions() -> None:
    """Called by app lifespan on shutdown."""
    for sid in list(_ACTIVE_SESSIONS.keys()):
        await _drop_session(sid)


async def reap_idle_sessions(max_idle_seconds: float = _DEFAULT_IDLE_TIMEOUT_S) -> list[str]:
    """Drop sessions whose last activity is older than ``max_idle_seconds``.

    Returns the list of dropped session ids (useful for logging/testing).
    """
    now = time.monotonic()
    # A session with a request in flight is not idle, however long it has run: a
    # ``coffer__ask`` waits on the owner for hours.
    stale = [
        sid
        for sid, last in list(_LAST_ACTIVITY.items())
        if now - last > max_idle_seconds and _SESSION_REFS.get(sid, 0) == 0
    ]
    for sid in stale:
        await _drop_session(sid)
    return stale


#: The running reaper's loop: parked while no session is open (ADR
#: background-workers-wake-on-events), woken by the first activity.
_REAPER: WakeableLoop | None = None


def _reaper_pass(max_idle_seconds: float) -> Callable[[bool], Awaitable[None]]:
    async def reap(_poked: bool) -> None:
        stale = await reap_idle_sessions(max_idle_seconds)
        if stale:
            _logger.info("mcp.session.reaped", extra={"count": len(stale), "session_ids": stale})
        if not _LAST_ACTIVITY and _REAPER is not None:
            _REAPER.set_demand(False)

    return reap


def start_session_reaper(
    *,
    interval_seconds: float = _REAPER_INTERVAL_S,
    max_idle_seconds: float = _DEFAULT_IDLE_TIMEOUT_S,
) -> asyncio.Task[None]:
    """Spawn the background session reaper task. Caller must cancel on shutdown."""
    global _REAPER
    _REAPER = WakeableLoop(
        "mcp-session-reaper",
        _reaper_pass(max_idle_seconds),
        fallback=interval_seconds,
        mode=WorkerMode.ON_DEMAND,
        failure_event="mcp.session.reaper_failed",
    )
    _REAPER.set_demand(bool(_LAST_ACTIVITY))
    return spawn(_REAPER.serve(), name="mcp-session-reaper")
