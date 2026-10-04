"""Numbered invalidation envelopes, a bounded replay buffer, and subscribers.

Every change the daemon announces becomes one :class:`Envelope` with the next
``seq`` of this daemon run (the first is 1). An envelope says *what* changed —
the kind, the resource's uid, ``upsert`` or ``delete`` — never the new state: a
client refetches through the typed endpoints.

Memory is bounded twice over:

- the broker keeps only the latest ``buffer_size`` envelopes, which is how far
  back a reconnecting client can resume;
- each subscriber holds at most ``queue_size`` undelivered items. One that
  falls further behind loses what is queued and is handed a single
  :class:`Resync` instead, then carries on live.

A client that reconnects with a ``seq`` the buffer cannot cover — older than
its oldest entry, or one this run never issued (a daemon restart, a garbage
header) — gets one :class:`Resync` before anything live, because it may have
missed something. Sequence numbers restart at 1 with every run, so a ``seq``
alone cannot say which run issued it: :attr:`EventBroker.run` is a random name
for this run that the surface puts beside the ``seq`` in each event's id, and a
resume naming another run is treated as never issued. Pure asyncio, no I/O.
"""

from __future__ import annotations

import asyncio
import secrets
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from coffer.domain.reconcile import Changed, ChangeOp

#: How many recent envelopes a reconnecting client can resume across.
DEFAULT_BUFFER_SIZE = 1024
#: How many undelivered items one subscriber may hold before it is resynced.
DEFAULT_QUEUE_SIZE = 256


@dataclass(frozen=True)
class Envelope:
    """One announced change: an invalidation hint, never the state itself."""

    seq: int
    kind: str
    id: str | None
    op: ChangeOp


@dataclass(frozen=True)
class Resync:
    """The subscriber may have missed envelopes: refetch everything.

    ``seq`` is the head at the time, so a client knows where live resumes.
    """

    seq: int


StreamItem = Envelope | Resync


class Subscription:
    """One subscriber's queue: replay (or a resync) first, then live items."""

    def __init__(self, broker: EventBroker, limit: int, first: Iterable[StreamItem]) -> None:
        self._broker = broker
        self._limit = limit
        self._items: deque[StreamItem] = deque(first)
        self._ready = asyncio.Event()
        if self._items:
            self._ready.set()

    def offer(self, envelope: Envelope) -> None:
        """Queue a live envelope, or — past the limit — drop what is queued
        and queue one resync in its place."""
        if len(self._items) >= self._limit:
            self._items.clear()
            self._items.append(Resync(envelope.seq))
        else:
            self._items.append(envelope)
        self._ready.set()

    async def next(self, timeout: float | None = None) -> StreamItem | None:
        """The next item, waiting up to ``timeout`` seconds; ``None`` when
        nothing arrived in that time."""
        if not self._items:
            self._ready.clear()
            try:
                await asyncio.wait_for(self._ready.wait(), timeout)
            except TimeoutError:
                return None
        return self._items.popleft()

    def pending(self) -> int:
        return len(self._items)

    def close(self) -> None:
        """Stop receiving; idempotent."""
        self._broker.unsubscribe(self)


class EventBroker:
    """Numbers each change of this daemon run and fans it out."""

    def __init__(
        self,
        *,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        queue_size: int = DEFAULT_QUEUE_SIZE,
    ) -> None:
        if buffer_size < 1 or queue_size < 1:
            raise ValueError("buffer_size and queue_size must be at least 1")
        self._seq = 0
        #: A random name for this daemon run; a resume that names another run
        #: is one this run never issued.
        self.run = secrets.token_hex(6)
        self._buffer: deque[Envelope] = deque(maxlen=buffer_size)
        self._queue_size = queue_size
        self._subscribers: set[Subscription] = set()

    @property
    def head(self) -> int:
        """The last ``seq`` issued; 0 before the first."""
        return self._seq

    @property
    def buffered(self) -> tuple[Envelope, ...]:
        return tuple(self._buffer)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, kind: str, id: str | None, op: ChangeOp = "upsert") -> Envelope:
        """Issue the next envelope, buffer it, and offer it to every subscriber."""
        self._seq += 1
        envelope = Envelope(self._seq, kind, id, op)
        self._buffer.append(envelope)
        for subscriber in tuple(self._subscribers):
            subscriber.offer(envelope)
        return envelope

    def publish_changed(self, changed: Changed) -> None:
        """A resource write's hint, as an envelope (a ``HintSink``)."""
        self.publish(changed.kind, changed.uid, changed.op)

    def subscribe(self, last_event_id: int | None = None) -> Subscription:
        """A new subscriber. With ``last_event_id`` it first receives every
        buffered envelope after it — or one :class:`Resync` when the buffer
        cannot cover the gap (a negative id counts as never issued)."""
        first = [] if last_event_id is None else self._replay_after(last_event_id)
        subscription = Subscription(self, self._queue_size, first)
        self._subscribers.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscribers.discard(subscription)

    def _replay_after(self, seq: int) -> list[StreamItem]:
        if seq < 0 or seq > self._seq:
            return [Resync(self._seq)]
        oldest = self._buffer[0].seq if self._buffer else self._seq + 1
        if seq < oldest - 1:
            return [Resync(self._seq)]
        return [e for e in self._buffer if e.seq > seq]


__all__ = [
    "DEFAULT_BUFFER_SIZE",
    "DEFAULT_QUEUE_SIZE",
    "Envelope",
    "EventBroker",
    "Resync",
    "StreamItem",
    "Subscription",
]
