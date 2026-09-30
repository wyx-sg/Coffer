"""What a channel-driven turn reads memory through (spec memory "Deliver to
channel turns through the system prompt", "Retrieve the notes a prompt names
for a channel turn").

A turn Coffer drives from a channel runs no hook of Coffer's, so memory reaches
it through two closures the composition root hands ``wire_chat``: the index,
appended to the turn's system prompt, and the notes the turn's prompt names,
added to the prompt. The providers call both only for a turn that came from a
channel, so a turn the developer drives gets memory through its agent's own
hook instead, never both. Both read the ``memory`` feature per turn, so the
switch lands on the next turn (spec experimental-features "Close every surface
of a switched-off feature"), and both fail open: memory is an addition to the
turn, not a precondition of it.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from coffer.application.features import FeatureService
from coffer.application.memory.context import MemoryPort, compose_context
from coffer.application.memory.turn_retrieval import TurnRetrieval

logger = logging.getLogger(__name__)


def memory_context_composer(
    memory: MemoryPort, features: FeatureService
) -> Callable[[str, str], Awaitable[str | None]]:
    """The closure a channel turn's system prompt reads the index through.

    ``None`` whenever nothing should be appended: while the ``memory`` feature
    is switched off, and when the composed index is empty, because an empty
    memory header is worse than none. A failure to read the tree is logged and
    also answers ``None``. ``agent_key`` is accepted and ignored: every enabled
    partition is served to every agent.
    """

    async def _compose(agent_key: str, cwd: str) -> str | None:
        del agent_key
        if not features.is_enabled("memory"):
            return None
        try:
            composed = await compose_context(memory, cwd=cwd)
        except Exception:
            # A tree that cannot be read costs this turn its index, not its reply.
            logger.exception("memory.channel_context.failed")
            return None
        return composed.text or None

    return _compose


def memory_turn_retriever(
    turns: TurnRetrieval, features: FeatureService
) -> Callable[[str, str, str, str], Awaitable[str | None]]:
    """The closure a channel turn's prompt is ranked against the notes through:
    ``(agent_key, cwd, prompt, conversation_id)`` → the notes to add, or
    ``None`` while the feature is off, when nothing is found, or on a failure
    (logged)."""

    async def _retrieve(agent_key: str, cwd: str, prompt: str, conversation_id: str) -> str | None:
        if not features.is_enabled("memory"):
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
