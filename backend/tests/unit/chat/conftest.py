"""Shared in-memory fakes for unit/chat tests.

All fake repository, adapter, and provider classes live here as the single
source of truth. Individual test modules import from this module rather than
defining their own copies.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any

from coffer.application.chat.ports import ToolSpec
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.domain.audit import AuditEntry
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from coffer.domain.chat.message import Message, Role, TextBlock
from coffer.domain.errors import ConversationNotFound

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

    async def list(self, *, archived: bool = False) -> list[Conversation]:
        rows = [c for c in self._store.values() if (c.archived_at is not None) == archived]
        return sorted(rows, key=lambda c: c.updated_at, reverse=True)

    async def rename(self, conversation_id: str, new_title: str) -> Conversation:
        conv = self._store[conversation_id]
        updated = dataclasses.replace(conv, title=new_title)
        self._store[conversation_id] = updated
        return updated

    async def touch(self, conversation_id: str, updated_at: datetime) -> None:
        conv = self._store[conversation_id]
        self._store[conversation_id] = dataclasses.replace(conv, updated_at=updated_at)

    async def set_model(self, conversation_id: str, model_id: str | None) -> Conversation:
        conv = self._store[conversation_id]
        updated = dataclasses.replace(conv, model_id=model_id)
        self._store[conversation_id] = updated
        return updated

    async def set_archived(
        self, conversation_id: str, archived_at: datetime | None
    ) -> Conversation:
        conv = self._store[conversation_id]
        updated = dataclasses.replace(conv, archived_at=archived_at)
        self._store[conversation_id] = updated
        return updated

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


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class FakeMessageRepo:
    """In-memory MessageRepo that fully satisfies the MessageRepo Protocol."""

    def __init__(self) -> None:
        self._messages: list[Message] = []

    async def append(self, message: Message) -> Message:
        self._messages.append(message)
        return message

    async def finalize(
        self,
        message_id: str,
        *,
        content: list[Any],
        status: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> None:
        for i, m in enumerate(self._messages):
            if m.id == message_id:
                self._messages[i] = dataclasses.replace(
                    m,
                    content=content,
                    status=status,  # type: ignore[arg-type]
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
                return

    async def delete_message(self, message_id: str) -> None:
        self._messages = [m for m in self._messages if m.id != message_id]

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        return sorted(
            [m for m in self._messages if m.conversation_id == conversation_id],
            key=lambda m: m.seq,
        )

    async def next_seq(self, conversation_id: str) -> int:
        msgs = [m for m in self._messages if m.conversation_id == conversation_id]
        return len(msgs)

    async def delete_by_conversation(self, conversation_id: str) -> None:
        self._messages = [m for m in self._messages if m.conversation_id != conversation_id]

    async def sweep_streaming(self) -> int:
        """Flip all ``status='streaming'`` rows to ``'failed'``; return count."""
        flipped = 0
        updated: list[Message] = []
        for msg in self._messages:
            if msg.status == "streaming":
                updated.append(dataclasses.replace(msg, status="failed"))  # type: ignore[call-overload]
                flipped += 1
            else:
                updated.append(msg)
        self._messages = updated
        return flipped

    def all_messages(self) -> list[Message]:
        return list(self._messages)


# ---------------------------------------------------------------------------
# Tool gateway
# ---------------------------------------------------------------------------


class FakeToolGateway:
    """Minimal ToolGateway that returns an empty skill catalogue by default."""

    def __init__(self, skill_response: dict[str, Any] | None = None) -> None:
        self._skill_response = skill_response or {"skills": []}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self) -> list[ToolSpec]:
        return []

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, args))
        if name == "coffer__list_skills":
            return self._skill_response
        return {}


# ---------------------------------------------------------------------------
# Agent adapter
# ---------------------------------------------------------------------------


class FakeAgentAdapter:
    """Scripted ``AgentAdapter``: yields a fixed sequence of ``AgentEvent``s.

    Records the history received on each ``run_turn`` so tests can assert on
    it. ``model_id`` is exposed because the orchestrator reads it (best-effort)
    to stamp the assistant message.
    """

    def __init__(self, events: list[AgentEvent], *, model_id: str | None = None) -> None:
        self._events = events
        self.model_id = model_id
        self.recorded_histories: list[list[Message]] = []

    async def run_turn(self, *, history: Sequence[Message]) -> AsyncIterator[AgentEvent]:
        self.recorded_histories.append(list(history))
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
    adapter (e.g. a missing credential).
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
    projection (ADR-032).
    """
    from coffer.application.audit_service import AuditService
    from coffer.application.chat.service import ChatService
    from coffer.application.chat.turn_orchestrator import TurnOrchestrator

    audit = AuditService(repo=FakeAuditRepo())  # type: ignore[arg-type]
    conv_repo = FakeConversationRepo()
    msg_repo = FakeMessageRepo()

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
        messages=msg_repo,
        registry=registry,
        audit=audit,  # type: ignore[arg-type]
    )
    orchestrator = TurnOrchestrator(chat_service=chat_svc, registry=registry, audit=audit)
    return chat_svc, orchestrator, registry


# ---------------------------------------------------------------------------
# Domain object helpers
# ---------------------------------------------------------------------------


def make_message(
    seq: int,
    text: str,
    conversation_id: str = "c1",
    role: Role = Role.USER,
    status: str = "complete",
) -> Message:
    return Message(
        id=f"msg-{seq}",
        conversation_id=conversation_id,
        seq=seq,
        role=role,
        content=[TextBlock(text=text)],
        status=status,  # type: ignore[arg-type]
        model_id=None,
        prompt_tokens=None,
        completion_tokens=None,
        created_at=datetime.now(tz=UTC),
    )
