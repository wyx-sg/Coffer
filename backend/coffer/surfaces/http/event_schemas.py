"""Wire models for ``GET /api/v1/events`` — the daemon-wide event stream.

Each Server-Sent Event's ``event:`` name says which model its ``data:`` is:
``change`` → :class:`ChangeEventOut`, ``resync`` → :class:`ResyncEventOut`,
``heartbeat`` → :class:`HeartbeatEventOut`. None carries a resource's state:
an envelope is an invalidation hint, and a client refetches through the typed
endpoints.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, RootModel

from coffer.application.events.broker import Envelope


class ChangeEventOut(BaseModel):
    """The data of a `change` event: something changed; refetch what shows it.

    Sent once per resource write through the framework, and once per change in
    what the attention list reports (`kind` `attention`, no `id`, no `rev`).
    The event's SSE id is `seq`, so a reconnecting client resumes with
    `Last-Event-ID`.
    """

    seq: int = Field(description="Grows by one per event across this daemon run; the first is 1.")
    kind: str = Field(description="The resource kind, or `attention`.")
    id: str | None = Field(description="The resource's uid; null for `attention`.")
    rev: int | None = Field(
        description="The revision the write produced (a delete: the last one plus one); "
        "null for `attention`."
    )
    op: Literal["upsert", "delete"] = Field(
        description="`upsert`: the resource exists with new content. `delete`: it is gone."
    )


class ResyncEventOut(BaseModel):
    """The data of a `resync` event: events may have been missed; refetch everything.

    Sent first on a reconnect whose `Last-Event-ID` the buffer cannot cover
    (older than its oldest entry, or never issued by this daemon run), and in
    place of the backlog when a client falls too far behind. Live `change`
    events follow it.
    """

    seq: int = Field(description="The head `seq` when the resync was issued.")


class HeartbeatEventOut(BaseModel):
    """The data of a `heartbeat` event: sent at a fixed interval while nothing changes.

    A client whose last seen `seq` is below `seq` is behind and should reconnect.
    """

    seq: int = Field(description="The current head `seq`; 0 before the first change.")


class EventStreamMessage(RootModel[ChangeEventOut | ResyncEventOut | HeartbeatEventOut]):
    """The `data:` of one event on `GET /api/v1/events`, chosen by its SSE `event:` name.

    `change` carries a ChangeEventOut, `resync` a ResyncEventOut, `heartbeat` a
    HeartbeatEventOut.
    """


def change_out(envelope: Envelope) -> ChangeEventOut:
    return ChangeEventOut(
        seq=envelope.seq, kind=envelope.kind, id=envelope.id, rev=envelope.rev, op=envelope.op
    )


__all__ = [
    "ChangeEventOut",
    "EventStreamMessage",
    "HeartbeatEventOut",
    "ResyncEventOut",
    "change_out",
]
