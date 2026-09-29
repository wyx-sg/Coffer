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


def get_heartbeat_seconds() -> float:
    return HEARTBEAT_SECONDS


__all__ = [
    "HEARTBEAT_SECONDS",
    "get_event_broker",
    "get_heartbeat_seconds",
    "set_event_broker",
]
