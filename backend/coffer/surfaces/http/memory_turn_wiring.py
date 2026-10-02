"""What a channel-driven turn reads memory through (spec memory "Deliver to
channel turns through the system prompt", "Retrieve the notes a prompt names
for a channel turn").

Coffer composes a channel turn's memory itself, through two closures the
composition root hands ``wire_chat``: the index, appended to the turn's system
prompt, and the notes the turn's prompt names, added to the prompt. The
providers call both only for a turn that came from a channel, and mark that
turn's process so the memory hook firing inside it leaves those two moments to
the turn (``coffer.domain.channel_turn``); a turn the developer drives gets
memory through its agent's own hook instead, never both. Both fail open:
memory is an addition to the turn, not a precondition of it.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from coffer.application.memory.turn_retrieval import TurnRetrieval
from coffer.domain.features import MEMORY

logger = logging.getLogger(__name__)


def memory_context_composer(
    turns: TurnRetrieval, is_enabled: Callable[[str], bool] = lambda _key: True
) -> Callable[[str, str, str], Awaitable[str | None]]:
    """The closure a channel turn's system prompt reads the index through:
    ``(agent_key, cwd, conversation_id)`` → the index, or ``None`` when nothing
    should be appended.

    ``None`` when the composed index is empty, because an empty memory header
    is worse than none. A failure to read the tree is logged and also answers
    ``None``. Every enabled partition is served to every agent; ``agent_key``
    names the agent the delivery is audited against.

    ``is_enabled`` answers whether a feature is on; the ``memory`` feature is
    read per turn so a switch lands on the next turn: while it is off nothing is
    appended (spec experimental-features "Withdraw what a switched-off feature
    put in front of agents").
    """

    async def _compose(agent_key: str, cwd: str, conversation_id: str) -> str | None:
        if not is_enabled(MEMORY):
            return None
        try:
            return await turns.index_for_turn(
                agent_key=agent_key, cwd=cwd, conversation_id=conversation_id
            )
        except Exception:
            # A tree that cannot be read costs this turn its index, not its reply.
            logger.exception("memory.channel_context.failed")
            return None

    return _compose


def memory_turn_retriever(
    turns: TurnRetrieval, is_enabled: Callable[[str], bool] = lambda _key: True
) -> Callable[[str, str, str, str], Awaitable[str | None]]:
    """The closure a channel turn's prompt is ranked against the notes through:
    ``(agent_key, cwd, prompt, conversation_id)`` → the notes to add, or
    ``None`` when nothing is found, on a failure (logged), or while the
    ``memory`` feature is off."""

    async def _retrieve(agent_key: str, cwd: str, prompt: str, conversation_id: str) -> str | None:
        if not is_enabled(MEMORY):
            return None
        try:
            return await turns.for_turn(
                agent_key=agent_key, cwd=cwd, prompt=prompt, conversation_id=conversation_id
            )
        except Exception:
            logger.exception("memory.channel_retrieval.failed")
            return None

    return _retrieve


__all__ = ["memory_context_composer", "memory_turn_retriever"]
