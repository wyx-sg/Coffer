"""Start a chat turn right now and hand back its event queue — a test seam.

Production starts turns through ``TurnOrchestrator.enqueue_message`` (start now, or
queue behind the running turn) and a channel renderer reads the turn's own queue via
``on_start``. Tests that only need "this turn, now, and its events" use this helper,
which rides the same path with an ``on_start`` sink.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.events import AgentEvent


async def start_turn(
    orchestrator: TurnOrchestrator,
    conversation_id: str,
    user_text: str,
    *,
    attachments: Sequence[Attachment] = (),
    title_hint: str | None = None,
) -> asyncio.Queue[AgentEvent | None]:
    """Start a turn for the message and return its dedicated event queue (ending in
    ``None``). Fails the test when the message was queued instead of started."""
    captured: list[asyncio.Queue[AgentEvent | None]] = []
    queued = await orchestrator.enqueue_message(
        conversation_id,
        user_text,
        attachments=attachments,
        title_hint=title_hint,
        on_start=captured.append,
    )
    assert not queued and captured, "the turn did not start immediately"
    return captured[0]
