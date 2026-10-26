"""The turns a question can be raised on: each running turn's token, which the
adapter puts into its agent process's environment as ``COFFER_TURN_TOKEN``.

Split out of :mod:`questions` (at its size budget), which re-exports it.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coffer.application.runtime import correlation
from coffer.application.turn_ask import TURN_TOKEN_ENV
from coffer.domain.chat.events import AgentEvent

#: Publishes one event on the turn that asked (the runner fans it out to the bus
#: and the channel renderer).
EventSink = Callable[[AgentEvent], Awaitable[None]]


@dataclass
class TurnContext:
    """What a live turn token names."""

    token: str
    conversation_id: str
    turn_id: str
    on_event: EventSink | None = None
    #: Told ``True`` when the turn starts waiting on a question and ``False``
    #: when the last one closes (the runner suspends its idle watchdog).
    on_waiting: Callable[[bool], None] | None = None


_TURNS: dict[str, TurnContext] = {}
_TURN_BY_CONVERSATION: dict[str, TurnContext] = {}


def register_turn(conversation_id: str) -> TurnContext:
    """Mint the token of a turn that is starting and register it."""
    ctx = TurnContext(
        token=secrets.token_hex(16),
        conversation_id=conversation_id,
        turn_id=correlation.new_id(),
    )
    _TURNS[ctx.token] = ctx
    _TURN_BY_CONVERSATION[conversation_id] = ctx
    return ctx


def turn_env(conversation_id: str) -> dict[str, str]:
    """The environment a turn's agent process gets: its token, when one is live."""
    token = token_for(conversation_id)
    return {TURN_TOKEN_ENV: token} if token else {}


def token_for(conversation_id: str) -> str | None:
    """The token of the conversation's live turn, for the adapter's environment."""
    ctx = _TURN_BY_CONVERSATION.get(conversation_id)
    return ctx.token if ctx is not None else None


def turn_is_live(token: str | None) -> bool:
    """Whether ``token`` names a turn that is running now."""
    return token is not None and token in _TURNS


__all__ = [
    "EventSink",
    "TurnContext",
    "register_turn",
    "token_for",
    "turn_env",
    "turn_is_live",
]
