"""The registry is the only way a turn reaches an agent, and the adapter it
builds is self-contained: the orchestrator hands it the history and nothing
else (spec chat "Route every turn through the agent-provider registry",
"Keep each agent adapter self-contained")."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator, clear_active_turns
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from coffer.domain.chat.message import Message

from .conftest import (
    FakeAgentAdapter,
    FakeAgentProvider,
    FakeConversationRepo,
    FakeMessageRepo,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_active_turns()
    yield
    clear_active_turns()


class _CountingProvider(FakeAgentProvider):
    """A fake provider that counts how often it is asked for an adapter."""

    def __init__(self, adapter: Any, *, agent_key: str) -> None:
        super().__init__(adapter, agent_key=agent_key)
        self.builds: list[str] = []

    async def build_adapter(self, conversation_id: str) -> Any:
        self.builds.append(conversation_id)
        return await super().build_adapter(conversation_id)


class _RecordingAdapter:
    """An adapter that records every keyword argument ``run_turn`` receives."""

    model_id: str | None = None

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run_turn(self, **kwargs: Any) -> AsyncIterator[AgentEvent]:
        self.calls.append(kwargs)
        return self._events()

    async def _events(self) -> AsyncIterator[AgentEvent]:
        yield TurnStarted()
        yield TextDelta(text="ok")
        yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


def _platform(*providers: Any) -> tuple[TurnOrchestrator, ChatService]:
    registry = AgentProviderRegistry()
    for provider in providers:
        registry.register(provider, display_name=provider.agent_key.title())
    chat = ChatService(
        conversations=FakeConversationRepo(),
        messages=FakeMessageRepo(),
        registry=registry,
    )
    return TurnOrchestrator(chat_service=chat, registry=registry), chat


async def _drain(queue: Any) -> list[AgentEvent]:
    out: list[AgentEvent] = []
    while (event := await queue.get()) is not None:
        out.append(event)
    return out


@pytest.mark.acceptance(spec="chat", scenario="a turn reaches the agent the conversation names")
async def test_a_turn_reaches_the_agent_the_conversation_names() -> None:
    alpha_adapter = FakeAgentAdapter(
        [TextDelta(text="from alpha"), TurnDone(None, None, "end_turn")]
    )
    beta_adapter = FakeAgentAdapter([TextDelta(text="from beta"), TurnDone(None, None, "end_turn")])
    alpha = _CountingProvider(alpha_adapter, agent_key="alpha")
    beta = _CountingProvider(beta_adapter, agent_key="beta")
    orchestrator, chat = _platform(alpha, beta)

    conv = await chat.create_conversation(agent_key="beta")
    events = await _drain(await orchestrator.start_turn(conv.id, "hello"))

    assert beta.builds == [conv.id]
    assert alpha.builds == []
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["from beta"]
    assert len(beta_adapter.recorded_histories) == 1
    assert alpha_adapter.recorded_histories == []


@pytest.mark.acceptance(spec="chat", scenario="the orchestrator hands an adapter only the history")
async def test_the_orchestrator_hands_an_adapter_only_the_history() -> None:
    adapter = _RecordingAdapter()
    provider = FakeAgentProvider(adapter, agent_key="solo")
    orchestrator, chat = _platform(provider)

    conv = await chat.create_conversation(agent_key="solo")
    await _drain(await orchestrator.start_turn(conv.id, "what is on disk?"))

    assert len(adapter.calls) == 1
    call = adapter.calls[0]
    # History and the turn's attachments are the whole of what it is given —
    # no model, tool list or configuration is injected by the orchestrator.
    assert set(call) == {"history", "attachments"}
    history: Sequence[Message] = call["history"]
    assert [m.content[0].text for m in history] == ["what is on disk?"]  # type: ignore[union-attr]
    assert list(call["attachments"]) == []
