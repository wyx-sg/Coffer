"""Bounded recently-seen-id set for idempotent inbound-event de-dup (FR-039).

IM ingress redelivers events: SeaTalk's Open Platform retries a callback when
the listener does not 2xx quickly, and a network hiccup can double-deliver.
Without de-dup a redelivered event would drive the SAME turn twice. This tiny
in-memory, per-process set drops an id already seen — correct because the
redelivery window is short (seconds), so surviving a restart is unnecessary.
"""

from __future__ import annotations

from collections import OrderedDict

_DEFAULT_CAPACITY = 2048


class SeenIds:
    """A bounded FIFO set of recently-seen ids; oldest evicted past capacity."""

    def __init__(self, capacity: int = _DEFAULT_CAPACITY) -> None:
        self._capacity = capacity
        self._ids: OrderedDict[str, None] = OrderedDict()

    def add(self, key: str) -> bool:
        """Record ``key``; return True if newly seen, False if already present."""
        if key in self._ids:
            return False
        self._ids[key] = None
        if len(self._ids) > self._capacity:
            self._ids.popitem(last=False)  # evict the oldest id
        return True
