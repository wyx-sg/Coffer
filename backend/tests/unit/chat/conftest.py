"""Shared in-memory fakes for unit/chat tests.

All fake repository, adapter, and provider classes live here as the single
source of truth. Individual test modules import from this module rather than
defining their own copies.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import datetime
from typing import Any

import pytest

from coffer.application.chat.conversation_repo import EVERY, Narrowing
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.turn_orchestrator import clear_active_turns
from coffer.domain.audit import AuditEntry
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.errors import ConversationNotFound
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted


@pytest.fixture(autouse=True)
def _clear_active_turns_between_tests() -> Iterator[None]:
    """The per-conversation turn registry is process-global; start and end clean."""
    clear_active_turns()
    yield
    clear_active_turns()


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class FakeAuditRepo:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def insert(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    async def query(self, **kwargs: Any) -> list[AuditEntry]:
        return self.entries


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


class FakeConversationRepo:
    def __init__(self) -> None:
        self._store: dict[str, Conversation] = {}
        self._agent_configs: dict[str, AgentConfig] = {}

    async def create(self, conversation: Conversation) -> Conversation:
        self._store[conversation.id] = conversation
        return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._store.get(conversation_id)

    async def list(
        self,
        *,
        limit: int | None = None,
        after: tuple[datetime, str] | None = None,
        contains: str | None = None,
        narrow: Narrowing = EVERY,
    ) -> list[Conversation]:
        rows = [c for c in self._store.values() if c.channel_uid is not None]
        if contains:
            needle = contains.casefold()
            rows = [
                c
                for c in rows
                if needle in (c.title or "").casefold()
                or needle in (self._configs_cwd(c.id) or "").casefold()
            ]
        if sources := narrow.sources:
            rows = [c for c in rows if c.channel_uid in sources]
        if narrow.agents:
            rows = [c for c in rows if c.agent_key in narrow.agents]
        rows.sort(key=lambda c: (c.updated_at, c.id), reverse=True)
        if after is not None:
            rows = [c for c in rows if (c.updated_at, c.id) < after]
        return rows if limit is None else rows[:limit]

    def _configs_cwd(self, conversation_id: str) -> str | None:
        return self._agent_configs.get(conversation_id, AgentConfig()).cwd

    async def by_session_ids(self, session_ids: Sequence[str]) -> Sequence[Conversation]:
        wanted = set(session_ids)
        return [
            c
            for c in self._store.values()
            if (self._agent_configs.get(c.id) or c.agent_config).session_id in wanted
        ]

    async def rename(self, conversation_id: str, new_title: str) -> Conversation:
        conv = self._store[conversation_id]
        updated = dataclasses.replace(conv, title=new_title)
        self._store[conversation_id] = updated
        return updated

    async def touch(self, conversation_id: str, updated_at: datetime) -> None:
        conv = self._store[conversation_id]
        self._store[conversation_id] = dataclasses.replace(conv, updated_at=updated_at)

    async def delete(self, conversation_id: str) -> None:
        self._store.pop(conversation_id, None)

    async def get_agent_config(self, conversation_id: str) -> AgentConfig:
        if conversation_id not in self._store:
            raise ConversationNotFound(conversation_id)
        return self._agent_configs.get(conversation_id, AgentConfig())

    async def set_agent_config(self, conversation_id: str, config: AgentConfig) -> None:
        if conversation_id not in self._store:
            raise ConversationNotFound(conversation_id)
        self._agent_configs[conversation_id] = config
        self._store[conversation_id] = dataclasses.replace(
            self._store[conversation_id], agent_config=config
        )


# ---------------------------------------------------------------------------
# Agent adapter
# ---------------------------------------------------------------------------


class FakeAgentAdapter:
    """Scripted ``AgentAdapter``: yields a fixed sequence of ``AgentEvent``s.

    Records the prompt and attachments received on each ``run_turn`` so tests
    can assert on them.
    """

    def __init__(self, events: list[AgentEvent], *, model_id: str | None = None) -> None:
        self._events = events
        self.model_id = model_id
        self.recorded_prompts: list[str] = []
        self.recorded_attachments: list[list[Any]] = []

    async def run_turn(
        self, prompt: str, attachments: Sequence[Any] = ()
    ) -> AsyncIterator[AgentEvent]:
        self.recorded_prompts.append(prompt)
        self.recorded_attachments.append(list(attachments))
        return self._yield_events()

    async def _yield_events(self) -> AsyncIterator[AgentEvent]:
        for event in self._events:
            yield event


# ---------------------------------------------------------------------------
# Agent provider
# ---------------------------------------------------------------------------


class FakeAgentProvider:
    """An ``AgentProvider`` for tests: builds a given adapter, records calls.

    ``build_error`` makes ``build_adapter`` raise unconditionally — used to
    exercise the turn path's clean failure when a provider can't build its
    adapter (e.g. a missing secret).
    """

    def __init__(
        self,
        adapter: Any,
        *,
        agent_key: str = "builtin",
        available: bool = True,
        build_error: BaseException | None = None,
        init_error: BaseException | None = None,
    ) -> None:
        self.agent_key = agent_key
        self._adapter = adapter
        self._available = available
        self._build_error = build_error
        self._init_error = init_error
        self.init_calls: list[tuple[str, dict[str, Any]]] = []
        self.deleted: list[str] = []

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        if self._init_error is not None:
            raise self._init_error
        self.init_calls.append((conversation_id, agent_config))

    async def build_adapter(self, conversation_id: str) -> Any:
        if self._build_error is not None:
            raise self._build_error
        return self._adapter

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        self.deleted.append(conversation_id)

    async def availability(self) -> bool:
        return self._available


def make_registry(
    adapter: Any = None,
    *,
    agent_key: str = "builtin",
    provider: Any = None,
) -> tuple[AgentProviderRegistry, FakeAgentProvider]:
    """Build a registry holding one ``FakeAgentProvider`` (or a supplied provider)."""
    prov = provider if provider is not None else FakeAgentProvider(adapter, agent_key=agent_key)
    registry = AgentProviderRegistry()
    registry.register(prov, display_name="Coffer Assistant")
    return registry, prov


def make_chat_services(
    events: list[AgentEvent] | None = None,
    *,
    provider: Any = None,
) -> tuple[Any, Any, AgentProviderRegistry]:
    """Build wired in-memory chat services + registry for HTTP / CLI integration tests.

    Returns ``(chat_service, turn_orchestrator, registry)``. The registry holds
    one ``FakeAgentProvider`` (or the supplied ``provider``). Chat no longer owns
    a model registry — a managed agent brings its own model via provider
    projection (ADR provider-connections-projected-into-agent-config).
    """
    from coffer.application.chat.service import ChatService
    from coffer.application.chat.turn_orchestrator import TurnOrchestrator

    conv_repo = FakeConversationRepo()

    if provider is None:
        default_events: list[AgentEvent] = events or [
            TurnStarted(),
            TextDelta(text="Hello from agent!"),
            TurnDone(prompt_tokens=10, completion_tokens=5, stop_reason="end_turn"),
        ]
        provider = FakeAgentProvider(FakeAgentAdapter(default_events), agent_key="builtin")

    registry = AgentProviderRegistry()
    registry.register(provider, display_name="Coffer Assistant")
    chat_svc = ChatService(
        conversations=conv_repo,
        registry=registry,
    )
    orchestrator = TurnOrchestrator(chat_service=chat_svc, registry=registry)
    return chat_svc, orchestrator, registry
