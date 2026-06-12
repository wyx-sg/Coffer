"""ChatService — conversation and message CRUD for the agent-chat surface.

Responsibilities:
- Create, list, get, rename, set-model, and delete conversations.
- Append and list messages within a conversation.
- Auto-generate a placeholder title for new conversations; replace it with a
  truncated version of the first user message text.
- Cascade delete: messages first, then the conversation row; emit audit events.

The ``ConversationRepo`` and ``MessageRepo`` Protocols are defined inline here
(same pattern as ``MemoryRecordRepo`` in ``application/memory/service.py``).
Concrete SQLAlchemy implementations live in ``infrastructure/chat/persistence.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from coffer.application.audit_service import AuditService
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.domain.audit import AuditEventType
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.message import ContentBlock, Message, Role, TextBlock
from coffer.domain.errors import ConversationNotFound, UnknownAgent

_TITLE_MAX_CHARS = 60
_PLACEHOLDER_TITLE = "New conversation"


# ---------------------------------------------------------------------------
# Repository Protocols
# ---------------------------------------------------------------------------


class ConversationRepo(Protocol):
    """Persistence port for ``Conversation`` rows."""

    async def create(self, conversation: Conversation) -> Conversation: ...

    async def get(self, conversation_id: str) -> Conversation | None: ...

    async def list(self) -> list[Conversation]:
        """Return all conversations, newest first (by ``updated_at`` desc)."""
        ...

    async def rename(self, conversation_id: str, new_title: str) -> Conversation: ...

    async def touch(self, conversation_id: str, updated_at: datetime) -> None:
        """Bump ``updated_at`` for the given conversation."""
        ...

    async def set_model(self, conversation_id: str, model_id: str | None) -> Conversation: ...

    async def delete(self, conversation_id: str) -> None: ...


class MessageRepo(Protocol):
    """Persistence port for ``chat_messages`` rows."""

    async def append(self, message: Message) -> Message: ...

    async def finalize(
        self,
        message_id: str,
        *,
        content: list[ContentBlock],
        status: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> None:
        """Update an existing (streaming) message with its final content/status."""
        ...

    async def delete_message(self, message_id: str) -> None:
        """Delete a single message by id."""
        ...

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        """Return messages ordered by ``seq`` ascending."""
        ...

    async def next_seq(self, conversation_id: str) -> int:
        """Return the next sequence number for the given conversation."""
        ...

    async def delete_by_conversation(self, conversation_id: str) -> None: ...

    async def sweep_streaming(self) -> int:
        """Flip all ``status='streaming'`` rows to ``'failed'``.

        Called once at startup to recover from a prior crash.  Returns the
        number of rows updated.
        """
        ...


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ChatService:
    """Application service for conversation and message lifecycle."""

    def __init__(
        self,
        *,
        conversations: ConversationRepo,
        messages: MessageRepo,
        registry: AgentProviderRegistry,
        audit: AuditService,
    ) -> None:
        self._conversations = conversations
        self._messages = messages
        self._registry = registry
        self._audit = audit

    # ------------------------------------------------------------------
    # Conversation CRUD
    # ------------------------------------------------------------------

    async def create_conversation(
        self,
        *,
        agent_key: str = "builtin",
        agent_config: dict[str, Any] | None = None,
        actor: str = "user",
    ) -> Conversation:
        """Create a conversation for the named agent.

        The agent is resolved through the registry — an unknown ``agent_key``
        raises ``UnknownAgent`` before anything is persisted. After the row is
        created, the agent's provider validates and persists its ``agent_config``
        via ``init_conversation``; if that fails the row is rolled back so an
        invalid configuration leaves nothing half-created.
        """
        provider = self._registry.get(agent_key)  # raises UnknownAgent (-> 400)

        now = datetime.now(tz=UTC)
        conv = Conversation(
            id=uuid.uuid4().hex,
            agent_key=agent_key,
            title=_PLACEHOLDER_TITLE,
            model_id=None,
            created_at=now,
            updated_at=now,
        )
        created = await self._conversations.create(conv)

        try:
            await provider.init_conversation(created.id, agent_config or {})
        except Exception:
            # Roll back so an invalid agent_config leaves nothing persisted.
            await self._conversations.delete(created.id)
            raise

        # init_conversation may have set agent-specific state (e.g. the model
        # override on the row); re-read so the caller sees the final shape.
        final = await self._conversations.get(created.id)
        result = final if final is not None else created

        await self._audit.record(
            AuditEventType.CONVERSATION_CREATED.value,
            actor=actor,
            details={"conversation_id": result.id},
        )
        return result

    async def list_conversations(self) -> list[Conversation]:
        """Return all conversations, newest first."""
        return await self._conversations.list()

    async def get_conversation(self, conversation_id: str) -> Conversation:
        """Return a conversation by id; raises ``ConversationNotFound`` if absent."""
        row = await self._conversations.get(conversation_id)
        if row is None:
            raise ConversationNotFound(conversation_id)
        return row

    async def rename_conversation(
        self,
        conversation_id: str,
        *,
        new_title: str,
    ) -> Conversation:
        """Rename a conversation.  Raises ``ConversationNotFound`` if absent."""
        await self.get_conversation(conversation_id)  # existence check
        return await self._conversations.rename(conversation_id, new_title)

    async def set_conversation_model(
        self,
        conversation_id: str,
        *,
        model_id: str | None,
    ) -> Conversation:
        """Override (or clear) the model for a conversation."""
        await self.get_conversation(conversation_id)  # existence check
        return await self._conversations.set_model(conversation_id, model_id)

    async def delete_conversation(
        self,
        conversation_id: str,
        *,
        actor: str = "user",
        cancel_turn_fn: Callable[[str], object] | None = None,
    ) -> None:
        """Delete a conversation and all its messages.

        Callers may supply ``cancel_turn_fn`` (a callable accepting a
        ``conversation_id``) which is invoked *before* the delete so any
        in-flight turn task is cancelled first.
        The actual turn-cancellation is owned by the ``TurnOrchestrator``; this
        parameter keeps ``ChatService`` free of a direct import of
        ``TurnOrchestrator``.

        The conversation's agent provider is given a chance to tear down any
        per-conversation state via ``on_conversation_deleted`` (best effort — a
        conversation whose agent is no longer registered is still deletable).
        """
        conv = await self.get_conversation(conversation_id)  # existence check

        if cancel_turn_fn is not None:
            cancel_turn_fn(conversation_id)

        try:
            provider = self._registry.get(conv.agent_key)
        except UnknownAgent:
            provider = None
        if provider is not None:
            await provider.on_conversation_deleted(conversation_id)

        await self._messages.delete_by_conversation(conversation_id)
        await self._conversations.delete(conversation_id)
        await self._audit.record(
            AuditEventType.CONVERSATION_DELETED.value,
            actor=actor,
            details={"conversation_id": conversation_id},
        )

    # ------------------------------------------------------------------
    # Message operations
    # ------------------------------------------------------------------

    async def append_message(
        self,
        conversation_id: str,
        *,
        role: Role,
        content: list[ContentBlock],
        status: str = "complete",
        model_id: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> Message:
        """Append a new message and bump the conversation's ``updated_at``.

        For the first user message, the conversation title is auto-generated
        from the message text (truncated to ``_TITLE_MAX_CHARS`` chars).
        """
        await self.get_conversation(conversation_id)  # existence check

        seq = await self._messages.next_seq(conversation_id)
        now = datetime.now(tz=UTC)
        msg = Message(
            id=uuid.uuid4().hex,
            conversation_id=conversation_id,
            seq=seq,
            role=role,
            content=content,
            status=status,  # type: ignore[arg-type]
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            created_at=now,
        )
        saved = await self._messages.append(msg)
        await self._conversations.touch(conversation_id, now)

        # Auto-generate title from the first user message.
        if role == Role.USER and seq == 0:
            text = _extract_text(content)
            if text:
                title = text[:_TITLE_MAX_CHARS]
                await self._conversations.rename(conversation_id, title)

        return saved

    async def finalize_message(
        self,
        conversation_id: str,
        message_id: str,
        *,
        content: list[ContentBlock],
        status: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> None:
        """Finalize a streaming placeholder message with its final content.

        Also bumps the conversation's ``updated_at`` so the recency-ordered
        conversation list reflects turn completion, not just turn start.
        """
        await self._messages.finalize(
            message_id,
            content=content,
            status=status,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        await self._conversations.touch(conversation_id, datetime.now(tz=UTC))

    async def delete_message(self, message_id: str) -> None:
        """Delete a single message by id (used to discard a placeholder row)."""
        await self._messages.delete_message(message_id)

    async def list_messages(self, conversation_id: str) -> list[Message]:
        """Return messages for a conversation ordered by ``seq`` ascending."""
        await self.get_conversation(conversation_id)  # existence check
        return await self._messages.list_by_conversation(conversation_id)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_text(content: list[ContentBlock]) -> str:
    """Extract the concatenated text from all ``TextBlock``s in a content list."""
    parts = [block.text for block in content if isinstance(block, TextBlock)]
    return " ".join(parts).strip()
