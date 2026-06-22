"""In-memory registry of in-flight async operations.

Tracks only transient states (queued / running / error) keyed by
``(op_type, item_key)``. Durable "done"/"unchanged" outcomes are derived from
each operation's own data (ledgers, content hashes), so nothing here needs to
survive a daemon restart: an in-flight operation interrupted by a restart simply
drops back to its derived status and can be re-run.

Mutations are plain dict assignments with no ``await`` between read and write,
so they are safe under the single-threaded asyncio event loop without a lock.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OpState(StrEnum):
    """Transient state of an in-flight async operation."""

    queued = "queued"
    running = "running"
    error = "error"


@dataclass(frozen=True)
class InflightEntry:
    """A single in-flight operation's state (and message when it errored)."""

    state: OpState
    message: str | None = None  # populated only when state is OpState.error


class AsyncOpRegistry:
    """Holds the in-flight state of async operations across the daemon."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], InflightEntry] = {}

    def mark_queued(self, op_type: str, item_key: str) -> None:
        self._entries[(op_type, item_key)] = InflightEntry(OpState.queued)

    def mark_running(self, op_type: str, item_key: str) -> None:
        self._entries[(op_type, item_key)] = InflightEntry(OpState.running)

    def mark_error(self, op_type: str, item_key: str, message: str) -> None:
        self._entries[(op_type, item_key)] = InflightEntry(OpState.error, message)

    def clear(self, op_type: str, item_key: str) -> None:
        """Drop an entry (called on success — the item's durable status takes over)."""
        self._entries.pop((op_type, item_key), None)

    def get(self, op_type: str, item_key: str) -> InflightEntry | None:
        return self._entries.get((op_type, item_key))

    def snapshot(self, op_type: str, *, prefix: str | None = None) -> dict[str, InflightEntry]:
        """All in-flight entries for *op_type*, optionally restricted to item keys
        starting with *prefix* (used to scope a status query to one agent/owner)."""
        return {
            item_key: entry
            for (otype, item_key), entry in self._entries.items()
            if otype == op_type and (prefix is None or item_key.startswith(prefix))
        }
