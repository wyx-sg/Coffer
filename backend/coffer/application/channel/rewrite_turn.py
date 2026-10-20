"""Running the follow-up turn that says a too-long reply again short (spec
channels "Ask for the short version of a reply too long for a chat"; the what
and why are in ``reply_rewrite``).

Split out of ``turn_driver`` (at its size budget). It goes through the
orchestrator's ordinary queue like any message, so the web shows it and the
conversation's FIFO stays one queue.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Callable
from typing import Any, Protocol

from coffer.application.channel.reply_rewrite import rewrite_prompt
from coffer.domain.errors import CofferError

__all__ = ["start_rewrite"]

_logger = logging.getLogger(__name__)


class _Turns(Protocol):
    async def enqueue_message(
        self,
        conversation_id: str,
        user_text: str,
        *,
        title_hint: str | None = None,
        on_start: Callable[[asyncio.Queue[Any]], None] | None = None,
    ) -> bool: ...

    def pending(self, conversation_id: str) -> list[str]: ...


async def start_rewrite[Item](
    turns: _Turns,
    conversation_id: str,
    item: Item,
    lines: int,
    *,
    render: Callable[[Item, str, asyncio.Queue[Any]], None],
) -> bool:
    """Queue the follow-up turn for the reply ``item`` (the driver's
    ``QueuedInbound``, typed loosely as ``turn_driver`` imports this) drove, of ``lines``
    lines, rendered by ``render`` into the same place; ``True`` when it was
    taken. A message the owner sent meanwhile would run first and make "your
    last reply" mean something else, so with anything waiting nothing is queued
    and the long reply is sent as it is instead."""
    if turns.pending(conversation_id):
        return False
    text = rewrite_prompt(lines)
    again = dataclasses.replace(  # type: ignore[type-var]
        item, text=text, attachments=(), title_hint="", rewrite=True
    )
    try:
        # An empty hint: Coffer's note never names the conversation.
        queued = await turns.enqueue_message(
            conversation_id,
            text,
            title_hint="",
            on_start=lambda queue: render(again, conversation_id, queue),
        )
    except CofferError:
        return False
    if queued:
        # Something got in first after all; it runs, then the follow-up does.
        _logger.info("channel.reply_rewrite.queued", extra={"conversation": conversation_id})
    return True
