"""Integration test: the interrupt route stops a turn, keeping its partial output.

A turn streams partial text and then blocks; the real ``POST .../interrupt``
route handler stops it. The stream closes with a terminal ``TurnDone`` (stop
reason ``interrupted``) and the partial assistant message is persisted —
distinct from deleting the conversation, which discards the turn.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.application.chat.ports import ApprovalGate
from coffer.application.chat.turn_orchestrator import active_turns, clear_active_turns
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from coffer.domain.chat.message import Role, TextBlock
from coffer.surfaces.http.chat.turn_routes import interrupt_turn
from tests.unit.chat.conftest import FakeAgentProvider, make_chat_services


class _BlockingAdapter:
    """Streams partial text, then blocks until the turn task is cancelled."""

    model_id = None

    async def run_turn(self, *, history: Any, approvals: ApprovalGate) -> AsyncIterator[AgentEvent]:
        async def gen() -> AsyncIterator[AgentEvent]:
            yield TurnStarted()
            yield TextDelta(text="partial answer")
            await asyncio.sleep(3600)

        return gen()


@pytest.fixture(autouse=True)
def _reset() -> Any:
    clear_active_turns()
    yield
    clear_active_turns()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="008-agent-chat", scenario="stop a running turn")
async def test_interrupt_route_stops_turn_and_keeps_partial_output() -> None:
    chat_svc, _model_svc, orchestrator, _registry = make_chat_services(
        provider=FakeAgentProvider(_BlockingAdapter(), agent_key="builtin")
    )
    conv = await chat_svc.create_conversation()

    queue = await orchestrator.start_turn(conv.id, "hi")
    await asyncio.wait_for(queue.get(), timeout=5.0)  # TurnStarted
    text_event = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(text_event, TextDelta)
    assert conv.id in active_turns()

    # Stop the running turn through the real POST .../interrupt route handler.
    resp = await interrupt_turn(conv.id, svc=chat_svc, orchestrator=orchestrator)
    assert resp.status_code == 204

    # The stream ends with an interrupted turn_done.
    rest: list[AgentEvent] = []
    while True:
        item = await asyncio.wait_for(queue.get(), timeout=5.0)
        if item is None:
            break
        rest.append(item)
    assert any(isinstance(e, TurnDone) and e.stop_reason == "interrupted" for e in rest)
    assert conv.id not in active_turns()

    # The partial assistant message was persisted (status complete).
    msgs = await chat_svc.list_messages(conv.id)
    assistant = next(m for m in msgs if m.role == Role.ASSISTANT)
    assert assistant.status == "complete"
    text = "".join(b.text for b in assistant.content if isinstance(b, TextBlock))
    assert "partial answer" in text
