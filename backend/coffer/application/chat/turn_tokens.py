"""The turns Coffer is running, by token: each running turn's token, which the
adapter puts into its agent process's environment as ``COFFER_TURN_TOKEN``. The
shim forwards it as ``X-Coffer-Turn``, which is how the gateway knows a session
belongs to a Coffer turn and offers it the turn-scoped built-in tools.

Process-global and in memory: a turn's token lives exactly as long as the turn.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from coffer.application.runtime import correlation
from coffer.application.turn_scope import TURN_TOKEN_ENV


@dataclass
class TurnContext:
    """What a live turn token names."""

    token: str
    conversation_id: str
    turn_id: str


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


def release_turn(ctx: TurnContext) -> None:
    """The turn is over: its token no longer names a live turn."""
    _TURNS.pop(ctx.token, None)
    if _TURN_BY_CONVERSATION.get(ctx.conversation_id) is ctx:
        del _TURN_BY_CONVERSATION[ctx.conversation_id]


def clear_all() -> None:
    """Forget every turn (test teardown only)."""
    _TURNS.clear()
    _TURN_BY_CONVERSATION.clear()


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


class TurnLiveness:
    """The chat kind's side of :class:`coffer.application.turn_scope.TurnLivePort`."""

    def is_live(self, token: str | None) -> bool:
        return turn_is_live(token)


__all__ = [
    "TurnContext",
    "TurnLiveness",
    "clear_all",
    "register_turn",
    "release_turn",
    "token_for",
    "turn_env",
    "turn_is_live",
]
