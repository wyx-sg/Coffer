"""What "nobody is using the daemon" means, and who may say otherwise.

The daemon is a login service: launchd starts it when the user logs in and
restarts it if it crashes (``coffer daemon install-service``). Resident by
default is the behaviour a vault an agent talks to has to have — a daemon that
is only up while its window is open is a daemon that is down whenever the work
is happening somewhere else. Resident *forever* is a different thing, though,
and not one anybody asked for: a python process, its MCP upstreams and its
channel listeners have no business surviving a weekend nobody worked.

So the daemon stands down once nothing has wanted it for long enough. This
module is the "long enough" clock, and it is deliberately the whole of it:
one monotonic timestamp and a set of named holds.

**Why holds exist.** Idleness cannot be read off the request log alone. A
channel listener is a mouth open to the outside world — a SeaTalk message at
nine in the morning reaches a daemon that has served nobody since yesterday
afternoon, and a daemon that stood down overnight is one that silently stops
answering the user's bot. Work like that is not *requests*, it is *readiness*
to take them, and a hold is how a subsystem says so. While any hold is held
the daemon is not idle, full stop; nothing here weighs holds against time.

**Why a request in flight is one of them.** `/mcp` is served over SSE, and an
agent's shim holds that stream open for the whole session. Counting only the
instant a request *arrives* would read a connected agent that has not called
a tool since last night as nobody at all — and standing down under an open
stream is worse than pointless, because the shutdown then waits on the very
connection that should have prevented it.

Monotonic, not wall clock: a laptop that slept for nine hours did not thereby
go nine hours unused, and the clock that says otherwise would stand the daemon
down the moment the lid opened, exactly when its user came back.
"""

from __future__ import annotations

import threading
import time

#: Guards the three fields below. The request bracket comes from the ASGI
#: middleware (twice per request, on the event loop) and holds from the
#: channel runtime; the reader is a background task. All cheap, all frequent,
#: none contended.
_lock = threading.Lock()
_last_activity: float = time.monotonic()
_holds: set[str] = set()
_in_flight: int = 0


def request_started() -> None:
    """A request has arrived and has not finished. Pairs with `request_ended`."""
    global _in_flight, _last_activity
    with _lock:
        _in_flight += 1
        _last_activity = time.monotonic()


def request_ended() -> None:
    """A request has finished, however it finished."""
    global _in_flight, _last_activity
    with _lock:
        _in_flight = max(0, _in_flight - 1)
        _last_activity = time.monotonic()


def in_flight() -> int:
    """How many requests are open right now — for diagnostics and for tests."""
    with _lock:
        return _in_flight


def hold(name: str) -> None:
    """Declare that ``name`` keeps the daemon in service regardless of traffic.

    Idempotent, and paired with :func:`release` by name rather than by a
    handle, so a subsystem that reconciles itself repeatedly (the channel
    runtime does, every few seconds) can assert the current state each pass
    instead of tracking whether it already asserted it.
    """
    with _lock:
        _holds.add(name)


def release(name: str) -> None:
    """Drop ``name``'s hold. Idempotent, for the same reason."""
    with _lock:
        _holds.discard(name)


def holds() -> frozenset[str]:
    """The holds currently in force — for diagnostics and for tests."""
    with _lock:
        return frozenset(_holds)


def idle_seconds() -> float:
    """How long the daemon has gone unwanted, in seconds.

    ``0.0`` while a request is open or any hold is in force: either way
    something wants this daemon now, however long ago the last one finished.
    """
    with _lock:
        if _holds or _in_flight:
            return 0.0
        return max(0.0, time.monotonic() - _last_activity)


def reset() -> None:
    """Forget every hold and start the clock again. Tests only."""
    global _last_activity, _in_flight
    with _lock:
        _holds.clear()
        _in_flight = 0
        _last_activity = time.monotonic()
