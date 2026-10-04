"""Integration test: interrupting a turn stops it.

A turn streams partial text and then blocks; ``TurnOrchestrator.interrupt_turn``
stops it. The stream closes with a terminal ``TurnDone`` (stop reason
``interrupted``) — distinct from discarding the conversation, which ends the turn
silently. A channel reaches this through ``ChannelTurnDriver``'s
``TurnPort.interrupt_turn``, the web through ``POST .../interrupt``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.application.chat.turn_orchestrator import active_turns
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from tests.support.chat_turns import start_turn
from tests.unit.chat.conftest import FakeAgentProvider, make_chat_services


class _BlockingAdapter:
    """Streams partial text, then blocks until the turn task is cancelled."""

    model_id = None

    async def run_turn(self, prompt: str, attachments: Any = ()) -> AsyncIterator[AgentEvent]:
        async def gen() -> AsyncIterator[AgentEvent]:
            yield TurnStarted()
            yield TextDelta(text="partial answer")
            await asyncio.sleep(3600)

        return gen()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="chat", scenario="stop a running turn")
async def test_interrupt_stops_the_turn() -> None:
    chat_svc, orchestrator, _registry = make_chat_services(
        provider=FakeAgentProvider(_BlockingAdapter(), agent_key="builtin")
    )
    conv = await chat_svc.create_conversation(agent_key="builtin")

    queue = await start_turn(orchestrator, conv.id, "hi")
    await asyncio.wait_for(queue.get(), timeout=5.0)  # TurnStarted
    text_event = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(text_event, TextDelta)
    assert conv.id in active_turns()

    # Stop the running turn the way a channel does.
    orchestrator.interrupt_turn(conv.id)

    # The stream ends with an interrupted turn_done.
    rest: list[AgentEvent] = []
    while True:
        item = await asyncio.wait_for(queue.get(), timeout=5.0)
        if item is None:
            break
        rest.append(item)
    assert any(isinstance(e, TurnDone) and e.stop_reason == "interrupted" for e in rest)
    assert conv.id not in active_turns()
