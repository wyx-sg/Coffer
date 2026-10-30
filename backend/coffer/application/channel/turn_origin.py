"""Where each running channel turn came from, by conversation, for the tools an
agent calls from inside it.

A built-in tool is handed its arguments and, from the gateway, the token of the
turn calling it (``coffer.application.turn_scope``). The token names the
conversation; this names what the channel knows about that turn and the
conversation index does not: which thread of which chat the reply goes to, who
asked, whether they own the bot, and — for a turn a scheduled task started —
which task and which link of a follow-up chain it is. ``coffer__schedule_task``
reads it, so an agent books a follow-up in the thread it is answering without
copying ids out of its prompt, and a turn someone who may only ask started
books nothing (spec channels "Let an agent book a follow-up in the thread it is
answering").

Process-global and in memory, like the turn tokens: an origin lives exactly as
long as the turn's renderer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__ = ["TurnOrigin", "clear", "forget", "origin_of", "remember"]


@dataclass(frozen=True)
class TurnOrigin:
    channel_uid: str
    chat_id: str
    chat_kind: str
    thread_id: str
    conversation_thread_id: str
    asker_is_owner: bool
    mention_user_id: str = ""
    mention_user_email: str = ""
    mention_user_name: str = ""
    #: Set when a scheduled task started this turn.
    task_uid: str = ""
    #: Whether that task repeats: a repeating task's run books nothing.
    task_repeats: bool = False
    #: The follow-up chain the task belongs to, when it is one.
    chain_started_at: datetime | None = None
    chain_index: int = 0


_ORIGINS: dict[str, TurnOrigin] = {}


def remember(conversation_id: str, origin: TurnOrigin) -> None:
    _ORIGINS[conversation_id] = origin


def forget(conversation_id: str, origin: TurnOrigin) -> None:
    """Drop ``origin`` unless a later turn of the conversation replaced it."""
    if _ORIGINS.get(conversation_id) is origin:
        del _ORIGINS[conversation_id]


def origin_of(conversation_id: str) -> TurnOrigin | None:
    return _ORIGINS.get(conversation_id)


def clear() -> None:
    """Forget every origin (test teardown only)."""
    _ORIGINS.clear()
