"""Whether calls record their content, and the capture every recording path uses.

Spec mcp-gateway "Switch call content recording per machine" and "Record
invocations with redacted, bounded content". The switch is one setting per
machine (``record_call_content`` in ``daemon-config.json``), read once at
startup and held here, so every gateway session — and every built-in tool —
reads the same answer without being handed it: a switch flipped on the
Settings page applies to the next call anywhere.

A custom HTTP tool's request and response are built inside its connection,
where the per-call headers are known and masked; the connection publishes
them on :data:`_exchange`, which the gateway opens around ``request()``.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Protocol

from coffer.domain.activity_content import capture_parts


class CallContentSettingPort(Protocol):
    """Where the machine's choice is kept."""

    def read(self) -> bool | None:
        """The stored choice, or ``None`` when there is none (on, by default)."""
        ...

    def write(self, enabled: bool) -> None:
        """Persist the choice. Raises if it could not be kept."""
        ...


class CallContentRecording:
    """The held switch; :meth:`set` writes the file before the held value."""

    def __init__(self, port: CallContentSettingPort) -> None:
        self._port = port
        stored = port.read()
        self._enabled = True if stored is None else stored

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set(self, enabled: bool) -> bool:
        """Switch recording; returns the value it had before."""
        before = self._enabled
        self._port.write(enabled)
        self._enabled = enabled
        return before


_current: CallContentRecording | None = None


def configure(recording: CallContentRecording | None) -> None:
    """Install the machine's switch (the composition root; ``None`` in tests)."""
    global _current
    _current = recording


def current() -> CallContentRecording | None:
    """The installed switch, for the route that reads and changes it."""
    return _current


def recording_enabled() -> bool:
    """On unless the machine switched it off; on before anything is installed."""
    return _current.enabled if _current is not None else True


def call_content(parts: Mapping[str, Any], secrets: Iterable[str] = ()) -> dict[str, Any] | None:
    """A call's parts captured for its row, or ``None`` while recording is off."""
    if not recording_enabled():
        return None
    return capture_parts(parts, secrets)


#: The request and response a custom tool's connection made for the current
#: call, already masked with that call's own secrets.
_exchange: ContextVar[dict[str, Any] | None] = ContextVar("coffer_call_exchange", default=None)


@contextmanager
def exchange_scope() -> Iterator[dict[str, Any]]:
    """Open a place for the current call's HTTP exchange; yields it."""
    sink: dict[str, Any] = {}
    token = _exchange.set(sink)
    try:
        yield sink
    finally:
        _exchange.reset(token)


def publish_exchange(*, request: Mapping[str, Any], response: Mapping[str, Any] | None) -> None:
    """Called by a custom tool's connection once its request returned or failed."""
    sink = _exchange.get()
    if sink is not None:
        sink["request"] = dict(request)
        sink["response"] = dict(response) if response is not None else None


__all__ = [
    "CallContentRecording",
    "CallContentSettingPort",
    "call_content",
    "configure",
    "current",
    "exchange_scope",
    "publish_exchange",
    "recording_enabled",
]
