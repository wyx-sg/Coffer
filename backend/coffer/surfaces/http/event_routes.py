"""``GET /api/v1/events`` — the daemon-wide event stream (spec
resource-framework "Announce every change on one daemon-wide event stream").

One Server-Sent Events stream for the whole daemon, gated by the token header
like every other management call (so a client reads it with ``fetch``, not
``EventSource``). It carries three events, each with a JSON ``data:`` line
(:mod:`coffer.surfaces.http.event_schemas`):

- ``change`` — an invalidation hint ``{seq, kind, id, op}``; its SSE id
  is ``<run>.<seq>``, naming this daemon run beside the ``seq`` because every
  run numbers from 1 again, so a resume from an earlier run is recognised;
- ``resync`` — the client may have missed something and refetches
  everything: sent first when ``Last-Event-ID`` is one the buffer cannot
  cover, or in place of a backlog the client fell too far behind on;
- ``heartbeat`` — the head ``seq``, sent while nothing changes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import APIRouter, Depends, Header
from fastapi.sse import EventSourceResponse, ServerSentEvent

from coffer.application.events.broker import Envelope, EventBroker, StreamItem
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.event_dependencies import get_event_broker, get_heartbeat_seconds
from coffer.surfaces.http.event_schemas import (
    EventStreamMessage,
    HeartbeatEventOut,
    ResyncEventOut,
    change_out,
)

router = APIRouter(prefix="/api/v1/events", tags=["events"], dependencies=[Depends(require_token)])

#: What an unparseable ``Last-Event-ID`` is read as: a ``seq`` no run issues,
#: so the client is told to resync rather than silently resumed from nowhere.
_UNKNOWN_EVENT_ID = -1


def event_id(broker: EventBroker, seq: int) -> str:
    """The SSE id of the ``change`` event carrying ``seq``."""
    return f"{broker.run}.{seq}"


def parse_last_event_id(value: str | None, run: str) -> int | None:
    """``None`` for a first connection; the ``seq`` of an id this run issued;
    and for anything else — another run's id, a bare number, garbage — a
    ``seq`` no run issues, so the client is told to resync."""
    if value is None or value.strip() == "":
        return None
    prefix, _, seq = value.strip().partition(".")
    if prefix != run or not seq.isdigit():
        return _UNKNOWN_EVENT_ID
    return int(seq)


def to_sse(broker: EventBroker, item: StreamItem) -> ServerSentEvent:
    """A ``change`` event (its SSE id ``<run>.<seq>``) or a ``resync`` event."""
    if isinstance(item, Envelope):
        return ServerSentEvent(data=change_out(item), event="change", id=event_id(broker, item.seq))
    return ServerSentEvent(data=ResyncEventOut(seq=item.seq), event="resync")


def heartbeat(broker: EventBroker) -> ServerSentEvent:
    return ServerSentEvent(data=HeartbeatEventOut(seq=broker.head), event="heartbeat")


@router.get(
    "",
    response_class=EventSourceResponse,
    response_description="A Server-Sent Events stream of `change`, `resync` and `heartbeat` "
    "events that stays open until the client disconnects.",
)
async def stream_events(
    last_event_id: str | None = Header(
        default=None,
        alias="Last-Event-ID",
        description="The SSE id of the last `change` event seen; resume after it.",
    ),
    broker: EventBroker = Depends(get_event_broker),  # noqa: B008
    heartbeat_seconds: float = Depends(get_heartbeat_seconds),
) -> AsyncIterator[EventStreamMessage]:
    """Every change the daemon announces, as invalidation hints, from now on
    (or from after `Last-Event-ID`, replayed from a bounded buffer).

    Each event's `data:` is the JSON model its `event:` name selects:
    `change`, `resync` or `heartbeat`."""
    subscription = broker.subscribe(parse_last_event_id(last_event_id, broker.run))
    try:
        while True:
            item = await subscription.next(timeout=heartbeat_seconds)
            event = heartbeat(broker) if item is None else to_sse(broker, item)
            # FastAPI sends a ServerSentEvent as it is; the annotation above
            # names the data model, which is what the OpenAPI document shows.
            yield cast(Any, event)
    finally:
        subscription.close()


__all__ = ["event_id", "heartbeat", "parse_last_event_id", "router", "to_sse"]
