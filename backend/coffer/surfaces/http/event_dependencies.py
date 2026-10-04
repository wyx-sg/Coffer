"""FastAPI dependency providers for the daemon-wide event stream.

The broker is a module-global singleton set once by the lifespan, like the
reconciler's; a getter called before its setter raises. The heartbeat
interval is a dependency of its own so a test can shorten it through
``app.dependency_overrides``.
"""

from __future__ import annotations

from coffer.application.events.broker import EventBroker

#: How long an idle stream waits before it sends a heartbeat.
HEARTBEAT_SECONDS = 15.0

_broker: EventBroker | None = None


def set_event_broker(broker: EventBroker | None) -> None:
    global _broker
    _broker = broker


def get_event_broker() -> EventBroker:
    if _broker is None:
        raise RuntimeError("event broker not initialised")
    return _broker


def announce_change(kind: str, uid: str | None) -> None:
    """Announce that something under ``kind`` changed outside a resource write.

    For the files a kind owns — a collection's inbox and documents, a partition's
    notes — which change without touching the resource row, so the resource hint
    never fires for them. An invalidation only (the page refetches); a daemon whose
    stream is not up yet, or a failure, announces nothing and costs the page one
    refetch it would otherwise have missed.
    """
    if _broker is None:
        return
    try:
        _broker.publish(kind, uid)
    except Exception:  # pragma: no cover - publish only appends and offers
        return


def get_heartbeat_seconds() -> float:
    return HEARTBEAT_SECONDS


__all__ = [
    "HEARTBEAT_SECONDS",
    "announce_change",
    "get_event_broker",
    "get_heartbeat_seconds",
    "set_event_broker",
]
