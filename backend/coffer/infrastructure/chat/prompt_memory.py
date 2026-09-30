"""The notes a channel turn's prompt names, added to that prompt (spec memory
"Retrieve the notes a prompt names for a channel turn").

Coffer composes a channel turn's memory itself, and the memory hook in the
process it spawns leaves ``UserPromptSubmit`` to the turn
(``coffer.domain.channel_turn``). So the provider hands its adapter a
:data:`PromptMemory` bound to the conversation, and the adapter adds what it
returns after the user's text in the prompt it sends —
where a ``UserPromptSubmit`` hook's context would land, so the notes stay in
the agent's own session for the turns after it. Only a channel turn gets one;
a turn the developer drives receives these notes through its own hook.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

#: (agent_key, cwd, prompt, conversation_id) -> the notes to add, or None.
MemoryRetriever = Callable[[str, str, str, str], Awaitable[str | None]]
#: prompt -> the notes to add, or None; a :data:`MemoryRetriever` bound to one turn.
PromptMemory = Callable[[str], Awaitable[str | None]]


def bind_prompt_memory(
    retrieve: MemoryRetriever | None,
    *,
    channel_uid: str,
    agent_key: str,
    cwd: str,
    conversation_id: str,
) -> PromptMemory | None:
    """The retriever for one turn — ``None`` unless the turn came from a channel."""
    if retrieve is None or not channel_uid:
        return None

    async def _for_prompt(prompt: str) -> str | None:
        return await retrieve(agent_key, cwd, prompt, conversation_id)

    return _for_prompt


async def prompt_with_memory(prompt: str, memory: PromptMemory | None) -> str:
    """``prompt`` with the notes it names after it. Fails open: a retrieval
    that raises costs the turn its notes, never the turn."""
    if memory is None or not prompt:
        return prompt
    try:
        notes = await memory(prompt)
    except Exception:
        logger.exception("memory.prompt_retrieval.failed")
        return prompt
    return f"{prompt}\n\n{notes}" if notes else prompt


__all__ = ["MemoryRetriever", "PromptMemory", "bind_prompt_memory", "prompt_with_memory"]
