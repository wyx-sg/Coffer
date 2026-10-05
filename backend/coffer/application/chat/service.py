"""ChatService — the conversation index for the agent-chat surface.

Responsibilities:
- Create, list, get, rename and delete conversations (the index rows of the
  channel conversations; the text of a conversation lives in the agent's own
  session, Coffer keeps none of it).
- Auto-generate a placeholder title for new conversations; replace it with a
  truncated version of the first message the person wrote (``begin_turn``).

``ConversationRepo`` lives beside the cursor pages of its listings in
``conversation_repo``; it is re-exported here.
Concrete SQLAlchemy implementation lives in ``infrastructure/chat/persistence.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from coffer.application.chat.conversation_repo import EVERY, Narrowing, page_conversations
from coffer.application.chat.conversation_repo import ConversationRepo as ConversationRepo
from coffer.application.chat.ports import ConversationSessionsPort
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.errors import ConversationNotFound, UnknownAgent
from coffer.domain.pagination import Page

_TITLE_MAX_CHARS = 60
_PLACEHOLDER_TITLE = "New conversation"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ChatService:
    """Application service for the conversation index."""

    def __init__(
        self,
        *,
        conversations: ConversationRepo,
        registry: AgentProviderRegistry,
    ) -> None:
        self._conversations = conversations
        self._registry = registry
        self._sessions: ConversationSessionsPort | None = None

    def link_sessions(self, sessions: ConversationSessionsPort | None) -> None:
        """Called by the composition root once the agent kind is wired."""
        self._sessions = sessions

    # ------------------------------------------------------------------
    # Conversation CRUD
    # ------------------------------------------------------------------

    async def create_conversation(
        self,
        *,
        agent_key: str,
        agent_config: dict[str, Any] | None = None,
        channel_uid: str | None = None,
        peer_chat_id: str | None = None,
    ) -> Conversation:
        """Create a conversation for the named agent.

        The agent is resolved through the registry — an unknown ``agent_key``
        raises ``UnknownAgent`` before anything is persisted. After the row is
        created, the agent's provider validates and persists its ``agent_config``
        via ``init_conversation``; if that fails the row is rolled back so an
        invalid configuration leaves nothing half-created.

        An optional channel binding (``channel_uid`` + ``peer_chat_id``) is the
        return address for relaying output back to an IM channel (spec channels).
        ``channel_uid`` is the channel resource's uid — the binding has to keep
        naming the same channel after the user renames it, and only the uid does
        (ADR identity-is-the-uid-inside-the-file). Chat itself never reads the
        channel's label; whoever shows it resolves it from the uid.
        """
        provider = self._registry.get(agent_key)  # raises UnknownAgent (-> 400)

        now = datetime.now(tz=UTC)
        conv = Conversation(
            id=uuid.uuid4().hex,
            agent_key=agent_key,
            title=_PLACEHOLDER_TITLE,
            created_at=now,
            updated_at=now,
            channel_uid=channel_uid,
            peer_chat_id=peer_chat_id,
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
        return final if final is not None else created

    async def page_conversations(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
        q: str | None = None,
        narrow: Narrowing = EVERY,
    ) -> Page[Conversation]:
        """One page of the channel conversations, newest activity first, continued
        by ``cursor``; ``q`` matches the title or the working directory."""
        return await page_conversations(
            self._conversations, limit=limit, cursor=cursor, q=q, narrow=narrow
        )

    async def get_conversation(self, conversation_id: str) -> Conversation:
        """Return a conversation by id; raises ``ConversationNotFound`` if absent."""
        row = await self._conversations.get(conversation_id)
        if row is None:
            raise ConversationNotFound(conversation_id)
        return row

    async def conversations_of_sessions(
        self, session_ids: Sequence[str]
    ) -> dict[str, Conversation]:
        """The conversation each agent session id belongs to; sessions no
        conversation points at are absent."""
        found = await self._conversations.by_session_ids(session_ids)
        return {c.agent_config.session_id: c for c in found if c.agent_config.session_id}

    async def rename_conversation(
        self,
        conversation_id: str,
        *,
        new_title: str,
    ) -> Conversation:
        """Rename a conversation.  Raises ``ConversationNotFound`` if absent."""
        await self.get_conversation(conversation_id)  # existence check
        return await self._conversations.rename(conversation_id, new_title)

    async def retitle_conversation(self, conversation_id: str, *, new_title: str) -> Conversation:
        """Rename a conversation through its agent, then in the index.

        The native session is renamed first; when the agent refuses, its error
        propagates and the index row keeps its title. A conversation with no
        session yet is renamed in the index only.
        """
        conv = await self.get_conversation(conversation_id)
        session_id = conv.agent_config.session_id
        if session_id and self._sessions is not None:
            await self._sessions.rename(conv.agent_key, session_id, new_title)
        return await self._conversations.rename(conversation_id, new_title)

    async def remove_conversation(
        self,
        conversation_id: str,
        *,
        cancel_turn_fn: Callable[[str], object] | None = None,
    ) -> None:
        """Delete a conversation through its agent, then its index row.

        The turn in flight is cancelled, the native session is deleted through
        the agent and the index row goes last. When the agent refuses, its error
        propagates and the index row stays (the turn was already cancelled). A
        conversation with no session yet is deleted from the index only.
        """
        conv = await self.get_conversation(conversation_id)
        session_id = conv.agent_config.session_id
        if session_id and self._sessions is not None:
            if cancel_turn_fn is not None:
                cancel_turn_fn(conversation_id)
            await self._sessions.delete(conv.agent_key, session_id)
        await self.delete_conversation(conversation_id, cancel_turn_fn=cancel_turn_fn)

    async def get_agent_config(self, conversation_id: str) -> AgentConfig:
        """The provider-private agent config (cwd, session id, model) for a
        conversation — used by the channel layer's ``/model`` passthrough."""
        return await self._conversations.get_agent_config(conversation_id)

    async def set_agent_config(self, conversation_id: str, config: AgentConfig) -> None:
        """Persist the provider-private agent config for a conversation."""
        await self._conversations.set_agent_config(conversation_id, config)

    async def delete_conversation(
        self,
        conversation_id: str,
        *,
        cancel_turn_fn: Callable[[str], object] | None = None,
    ) -> None:
        """Delete a conversation's index row.

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

        await self._conversations.delete(conversation_id)

    # ------------------------------------------------------------------
    # Turn bookkeeping
    # ------------------------------------------------------------------

    async def begin_turn(
        self, conversation_id: str, *, text: str, title_hint: str | None = None
    ) -> None:
        """A turn starts: bump the conversation's ``updated_at`` and, while it still
        carries the placeholder title it was created with, name it from the first
        words the person wrote (truncated to ``_TITLE_MAX_CHARS`` chars). A title
        the owner typed is theirs, and outranks the guess.

        ``title_hint`` lets a caller that built the turn's text say which part of
        it the human actually wrote. A channel turn opens with context blocks the
        channel folds in (provenance, thread history) — identical on every turn,
        so naming from the raw text would give every channel conversation the
        same name. Only the caller knows where its own blocks end, so it passes
        the human's words down rather than this layer pattern-matching for a
        format it must not know about. Empty hint (nothing the human wrote) ⇒ the
        conversation keeps its placeholder title, which is honest, rather than
        being named after boilerplate.
        """
        conv = await self.get_conversation(conversation_id)  # existence check
        await self._conversations.touch(conversation_id, datetime.now(tz=UTC))
        if conv.title != _PLACEHOLDER_TITLE:
            return
        words = (title_hint if title_hint is not None else text).strip()
        if words:
            await self._conversations.rename(conversation_id, words[:_TITLE_MAX_CHARS])

    async def end_turn(self, conversation_id: str) -> None:
        """A turn ended: bump ``updated_at`` so the recency-ordered list reflects
        the end of the turn, not just its start."""
        await self._conversations.touch(conversation_id, datetime.now(tz=UTC))
