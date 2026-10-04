"""One id to join a request's or a turn's records across three logs.

The daemon keeps three records of what happened: the audit log (``runs.db``
``audit_log``), the MCP invocation log (``mcp_invocations``) and the daemon log
(``daemon.log``). Each used to carry its own handle — the audit row none at
all, the invocation row the MCP session id, the log line a ``trace_id`` — so
"what else did this request do?" could only be answered by lining up
timestamps.

A :class:`Correlation` is the set of ids the current unit of work carries, held
in one context variable so every record written while it is bound inherits it:

* ``trace_id`` — the HTTP request's id (``X-Coffer-Trace``), or the turn's own
  id for a turn nothing requested over HTTP. It is THE join key: the audit row,
  the invocation row and the log line all store it.
* ``session_id`` — the MCP session a ``/mcp`` call arrived on.
* ``conversation_id`` and ``turn_id`` — the chat conversation and the one turn
  of it that is running, for a web chat or a channel turn.

A context variable, because ``asyncio`` copies the context into every task it
creates: a turn spawned by a request keeps the request's trace id, and a
background task spawned by a turn keeps the turn's ids, with no parameter
threaded through the code in between. Binding returns a token and resetting
restores what was there, so a nested bind (a turn inside a request) never
leaks outward.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from typing import Final

#: What a record carries when no trace id is bound (a boot-time line, a
#: periodic worker). The log reader and the CLI treat it as "no id".
NO_TRACE: Final = "-"


@dataclass(frozen=True)
class Correlation:
    """The ids the current unit of work carries; ``None`` where one does not apply."""

    trace_id: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    turn_id: str | None = None

    def log_fields(self) -> dict[str, str]:
        """The ids as log-line fields: ``trace_id`` always, the others when set."""
        fields = {"trace_id": self.trace_id or NO_TRACE}
        for key in ("session_id", "conversation_id", "turn_id"):
            value = getattr(self, key)
            if value:
                fields[key] = value
        return fields


_EMPTY: Final = Correlation()
_CURRENT: ContextVar[Correlation] = ContextVar("coffer_correlation", default=_EMPTY)


def new_id() -> str:
    """A fresh id. Half a UUID is plenty to separate concurrent requests and turns."""
    return uuid.uuid4().hex[:16]


def current() -> Correlation:
    """The ids bound in this context (all ``None`` when nothing is)."""
    return _CURRENT.get()


def bind(
    *,
    trace_id: str | None = None,
    session_id: str | None = None,
    conversation_id: str | None = None,
    turn_id: str | None = None,
) -> Token[Correlation]:
    """Add ids to the current correlation; fields passed as ``None`` are kept.

    Returns the token :func:`reset` takes to restore what was bound before.
    """
    updates = {
        key: value
        for key, value in (
            ("trace_id", trace_id),
            ("session_id", session_id),
            ("conversation_id", conversation_id),
            ("turn_id", turn_id),
        )
        if value is not None
    }
    return _CURRENT.set(replace(_CURRENT.get(), **updates))


def reset(token: Token[Correlation]) -> None:
    """Restore the correlation that was bound before ``token``'s bind."""
    _CURRENT.reset(token)


@contextmanager
def correlated(
    *,
    trace_id: str | None = None,
    session_id: str | None = None,
    conversation_id: str | None = None,
    turn_id: str | None = None,
) -> Iterator[Correlation]:
    """Bind ids for the duration of a ``with`` block."""
    token = bind(
        trace_id=trace_id,
        session_id=session_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
    )
    try:
        yield _CURRENT.get()
    finally:
        reset(token)


def begin_turn(conversation_id: str) -> Token[Correlation]:
    """Bind a new turn of ``conversation_id``; return the token that unbinds it.

    The turn gets its own id. It keeps the trace id already bound — a web chat
    turn belongs to the request that started it — and adopts its turn id as the
    trace id when there is none, which is the channel case: a message that
    arrived over a websocket or a long poll has no HTTP request behind it, and
    the turn is then the unit whose records should read as one story.

    The caller binds around the spawn of the turn's task and resets right
    after: the task copies the context at creation, so the turn keeps its ids
    for its whole life while the caller's context is left as it was.
    """
    turn_id = new_id()
    bound = _CURRENT.get()
    return _CURRENT.set(
        replace(
            bound,
            trace_id=bound.trace_id or turn_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
        )
    )


@contextmanager
def turn(conversation_id: str) -> Iterator[Correlation]:
    """:func:`begin_turn` for the duration of a ``with`` block."""
    token = begin_turn(conversation_id)
    try:
        yield _CURRENT.get()
    finally:
        reset(token)


def bind_trace_id(trace_id: str | None) -> None:
    """Set (or clear, with ``None``) only the trace id.

    The HTTP middleware's writer: it binds a request's id on the way in and
    clears it on the way out, which must also clear any session or turn ids a
    route bound, so ``None`` resets the whole correlation.
    """
    if trace_id is None:
        _CURRENT.set(_EMPTY)
        return
    _CURRENT.set(replace(_CURRENT.get(), trace_id=trace_id))


def get_trace_id() -> str:
    """The bound trace id, or :data:`NO_TRACE`."""
    return _CURRENT.get().trace_id or NO_TRACE
