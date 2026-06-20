"""ConversationBus — per-conversation fan-out of turn events to N subscribers.

The orchestrator publishes a turn's ``AgentEvent``s to the bus, which

  (a) keeps a **ring buffer** of the *current* turn's events so a late subscriber
      (the desktop opened mid-turn, or watching a turn another surface started)
      catches up, then

  (b) **fans** each event out to every attached subscriber queue.

Queue-changed events are conversation-level (the pending queue, ADR-031): kept as
a single latest snapshot replayed to new subscribers, not in the per-turn buffer.

Process-global and single-daemon by design (ADR-031); no cross-process fan-out.
"""

from __future__ import annotations

import asyncio

from coffer.domain.chat.events import AgentEvent


class ConversationBus:
    """Fan-out + replay for one conversation's live turn events."""

    def __init__(self) -> None:
        # A ``None`` enqueued into a subscriber queue is the close sentinel.
        self._subscribers: set[asyncio.Queue[AgentEvent | None]] = set()
        self._turn_buffer: list[AgentEvent] = []
        self._queue_snapshot: AgentEvent | None = None

    def begin_turn(self) -> None:
        """Start a new turn's replay buffer (clears the previous turn's)."""
        self._turn_buffer = []

    def end_turn(self) -> None:
        """A turn completed: its content is now persisted and loaded from history,
        so drop the replay buffer to avoid double-rendering for late subscribers.
        """
        self._turn_buffer = []

    def publish(self, event: AgentEvent) -> None:
        """Append a turn event to the replay buffer and fan it out live."""
        self._turn_buffer.append(event)
        self._fan_out(event)

    def publish_queue_changed(self, event: AgentEvent) -> None:
        """Fan out a queue-changed snapshot and remember it for replay."""
        self._queue_snapshot = event
        self._fan_out(event)

    def subscribe(self) -> asyncio.Queue[AgentEvent | None]:
        """Attach a subscriber, replaying the in-flight turn buffer + the latest
        queue snapshot so it catches up immediately, then stream live.

        Replay is enqueued synchronously before the queue joins the subscriber
        set, so a concurrent ``publish`` (which can only run on another event-loop
        tick) never interleaves ahead of the replay.
        """
        q: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        for event in self._turn_buffer:
            q.put_nowait(event)
        if self._queue_snapshot is not None:
            q.put_nowait(self._queue_snapshot)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[AgentEvent | None]) -> None:
        self._subscribers.discard(q)

    def close(self) -> None:
        """End every subscriber stream (conversation deleted)."""
        for q in self._subscribers:
            q.put_nowait(None)
        self._subscribers.clear()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def _fan_out(self, event: AgentEvent) -> None:
        for q in self._subscribers:
            q.put_nowait(event)
