"""The registry is the only way a turn reaches an agent, and the adapter it
builds is self-contained: the orchestrator hands it the prompt and the
attachments and nothing else (spec chat "Route every turn through the
agent-provider registry", "Keep each agent adapter self-contained")."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from tests.support.chat_turns import start_turn

from .conftest import (
    FakeAgentAdapter,
    FakeAgentProvider,
    FakeConversationRepo,
)

pytestmark = pytest.mark.asyncio


class _CountingProvider(FakeAgentProvider):
    """A fake provider that counts how often it is asked for an adapter."""

    def __init__(self, adapter: Any, *, agent_key: str) -> None:
        super().__init__(adapter, agent_key=agent_key)
        self.builds: list[str] = []

    async def build_adapter(self, conversation_id: str) -> Any:
        self.builds.append(conversation_id)
        return await super().build_adapter(conversation_id)


class _RecordingAdapter:
    """An adapter that records every argument ``run_turn`` receives."""

    model_id: str | None = None

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Any]]] = []

    async def run_turn(self, prompt: str, attachments: Any = ()) -> AsyncIterator[AgentEvent]:
        self.calls.append((prompt, list(attachments)))
        return self._events()

    async def _events(self) -> AsyncIterator[AgentEvent]:
        yield TurnStarted()
        yield TextDelta(text="ok")
        yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")


def _platform(*providers: Any) -> tuple[TurnOrchestrator, ChatService]:
    registry = AgentProviderRegistry()
    for provider in providers:
        registry.register(provider, display_name=provider.agent_key.title())
    chat = ChatService(conversations=FakeConversationRepo(), registry=registry)
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
    events = await _drain(await start_turn(orchestrator, conv.id, "hello"))

    assert beta.builds == [conv.id]
    assert alpha.builds == []
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["from beta"]
    assert beta_adapter.recorded_prompts == ["hello"]
    assert alpha_adapter.recorded_prompts == []


@pytest.mark.acceptance(spec="chat", scenario="the orchestrator hands an adapter only the turn")
async def test_the_orchestrator_hands_an_adapter_only_the_prompt() -> None:
    adapter = _RecordingAdapter()
    provider = FakeAgentProvider(adapter, agent_key="solo")
    orchestrator, chat = _platform(provider)

    conv = await chat.create_conversation(agent_key="solo")
    await _drain(await start_turn(orchestrator, conv.id, "what is on disk?"))

    # The prompt and the turn's attachments are the whole of what it is given —
    # no history, model, tool list or configuration is injected by the orchestrator.
    assert adapter.calls == [("what is on disk?", [])]
