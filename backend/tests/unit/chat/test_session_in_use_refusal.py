"""A turn that would resume a session open in a terminal is refused, not started.

Spec chat "Run a session in one place at a time". The in-use port is a fake.
"""

from __future__ import annotations

import pytest

from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator, active_turns
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.errors import SessionInUse
from coffer.domain.chat.events import (
    SESSION_IN_USE,
    SESSION_IN_USE_MESSAGE,
    TextDelta,
    TurnDone,
    TurnError,
)
from tests.support.chat_turns import start_turn

from .conftest import FakeAgentAdapter, FakeConversationRepo, make_registry
from .test_turn_orchestrator_with_fake_adapter import drain_queue

SID = "550e8400-e29b-41d4-a716-446655440000"


class _InUse:
    def __init__(self, busy: bool) -> None:
        self.busy = busy
        self.asked: list[str] = []

    async def in_use(self, session_id: str) -> bool:
        self.asked.append(session_id)
        return self.busy


async def _setup(busy: bool, *, session_id: str | None = SID):
    repo = FakeConversationRepo()
    adapter = FakeAgentAdapter(
        [
            TextDelta(text="hi"),
            TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn"),
        ]
    )
    registry, _ = make_registry(adapter)
    chat = ChatService(conversations=repo, registry=registry)
    port = _InUse(busy)
    orchestrator = TurnOrchestrator(chat_service=chat, registry=registry, session_in_use=port)
    conv = await chat.create_conversation(agent_key="builtin", channel_uid="c", peer_chat_id="p")
    if session_id is not None:
        await chat.set_agent_config(conv.id, AgentConfig(session_id=session_id))
    return orchestrator, adapter, port, conv.id


@pytest.mark.acceptance(
    spec="chat", scenario="a session open in a terminal refuses the channel turn"
)
async def test_a_session_open_elsewhere_ends_the_turn_with_the_refusal_and_runs_nothing() -> None:
    orchestrator, adapter, port, conv_id = await _setup(busy=True)

    queue = await start_turn(orchestrator, conv_id, "hello")

    events = await drain_queue(queue)
    assert events == [TurnError(code=SESSION_IN_USE, message=SESSION_IN_USE_MESSAGE)]
    assert adapter.recorded_prompts == []
    assert port.asked == [SID]
    assert conv_id not in active_turns()


async def test_the_refused_message_is_not_retried_or_held() -> None:
    orchestrator, adapter, port, conv_id = await _setup(busy=True)

    await drain_queue(await start_turn(orchestrator, conv_id, "one"))
    # Free now: the next message starts a turn; the refused one did not come back.
    port.busy = False
    events = await drain_queue(await start_turn(orchestrator, conv_id, "two"))

    assert adapter.recorded_prompts == ["two"]
    assert isinstance(events[-1], TurnDone)


@pytest.mark.acceptance(spec="chat", scenario="a session whose terminal closed runs again")
async def test_a_free_session_runs_the_turn() -> None:
    orchestrator, adapter, _port, conv_id = await _setup(busy=False)

    events = await drain_queue(await start_turn(orchestrator, conv_id, "hello"))

    assert adapter.recorded_prompts == ["hello"]
    assert isinstance(events[-1], TurnDone)


async def test_a_conversation_with_no_session_is_not_asked() -> None:
    orchestrator, _adapter, port, conv_id = await _setup(busy=True, session_id=None)

    events = await drain_queue(await start_turn(orchestrator, conv_id, "first"))

    assert port.asked == []
    assert isinstance(events[-1], TurnDone)


async def test_a_message_with_no_renderer_raises_the_refusal() -> None:
    orchestrator, _adapter, _port, conv_id = await _setup(busy=True)

    with pytest.raises(SessionInUse):
        await orchestrator.enqueue_message(conv_id, "hello")

    assert conv_id not in active_turns()
