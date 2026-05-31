"""Ports the chat application layer depends on (Protocols only).

Concrete implementations are wired at the composition root:
- repos -> ``coffer.infrastructure.chat.persistence``
- runtimes -> ``coffer.infrastructure.chat.builtin_runtime`` / ``…external_runtime``

Per the layering contract, application code imports only these Protocols; it
never imports infrastructure directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from coffer.domain.chat.conversation import Conversation, ConversationStatus, Message
from coffer.domain.chat.runtime import ChatTurnRequest, RuntimeEvent
from coffer.domain.resource import ResourceRef


class ConversationRepo(Protocol):
    async def create(self, conversation: Conversation) -> Conversation: ...
    async def get(self, conversation_id: str) -> Conversation | None: ...
    async def list(
        self,
        *,
        status: ConversationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]: ...
    async def set_title(self, conversation_id: str, title: str) -> Conversation: ...
    async def set_status(
        self, conversation_id: str, status: ConversationStatus
    ) -> Conversation: ...
    async def touch(self, conversation_id: str) -> None: ...
    async def delete(self, conversation_id: str) -> None: ...


class MessageRepo(Protocol):
    async def add(self, message: Message) -> Message: ...
    async def list_for(self, conversation_id: str) -> list[Message]: ...
    async def update(
        self,
        message_id: str,
        *,
        content: str | None = None,
        status: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        error: dict[str, Any] | None = None,
    ) -> Message: ...


class AgentRuntime(Protocol):
    """A single turn's execution for one conversation target.

    ``stream`` yields runtime events until it ends with a ``DoneEvent`` or
    ``ErrorEvent``. When it yields a ``ConfirmationRequest`` it suspends until
    ``resolve_confirmation`` is called with the matching id. ``stop`` cancels
    the turn (terminating any spawned subprocess).
    """

    def stream(self, request: ChatTurnRequest) -> AsyncIterator[RuntimeEvent]: ...
    async def resolve_confirmation(self, request_id: str, approve: bool) -> None: ...
    async def stop(self) -> None: ...


class RuntimeFactory(Protocol):
    """Builds the right ``AgentRuntime`` for a conversation target.

    ``target.kind`` selects the implementation (``builtin_agent`` -> LangGraph
    runtime; ``agent`` -> external subprocess runtime); ``config`` is the
    resolved ``Resource.config`` of that target.
    """

    def build(self, *, target: ResourceRef, config: dict[str, Any]) -> AgentRuntime: ...


class TitleGenerator(Protocol):
    """Produces a short conversation title from the first exchange. May return
    ``None`` (caller falls back to a truncated first message)."""

    async def generate(self, user_message: str, assistant_message: str) -> str | None: ...
