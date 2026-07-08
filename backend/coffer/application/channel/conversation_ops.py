"""Conversation creation for channel-driven turns — shared by the inbound
turn-driver and the command router.

A channel conversation's structural choice (agent) is resolved from the
peer's sticky preference plus the channel default, then fixed at creation;
switching opens a fresh conversation. These helpers are pure given their
injected ports — no per-processor state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from coffer.application.channel.conversation_spec import resolve_conversation_spec
from coffer.domain.chat.errors import ConversationNotFound
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.ports import (
        ChannelBinding,
        ChannelPeer,
        ChannelThreadConversationRepoPort,
    )


class _ConversationPort(Protocol):
    async def create_conversation(
        self,
        *,
        agent_key: str,
        agent_config: dict[str, Any] | None,
        actor: str,
        channel_name: str | None = None,
        peer_chat_id: str | None = None,
    ) -> Any: ...

    async def get_conversation(self, conversation_id: str) -> Any: ...


async def open_conversation(
    conversations: _ConversationPort,
    threads: ChannelThreadConversationRepoPort,
    binding: ChannelBinding,
    peer: ChannelPeer,
    thread_id: str = "",
) -> str:
    """Create a conversation from this thread's sticky choices + channel
    defaults (resolver) and make it the thread's active conversation (FR-032).

    Conversation identity is per ``(resource_id, chat_id, thread_id)`` — a DM
    (``thread_id=""``) and each group thread open independently, so concurrent
    turns in different threads never collide on one conversation."""
    row = await threads.get(binding.resource_id, peer.chat_id, thread_id)
    spec = resolve_conversation_spec(
        default_agent=binding.default_agent,
        default_agent_config=binding.default_agent_config,
        preferred_agent=row.preferred_agent if row is not None else None,
    )
    conv = await conversations.create_conversation(
        agent_key=spec.agent_key,
        agent_config=spec.agent_config,
        actor="channel",
        channel_name=binding.name,
        peer_chat_id=peer.chat_id,
    )
    await threads.set_active_conversation(binding.resource_id, peer.chat_id, thread_id, conv.id)
    return str(conv.id)


async def ensure_conversation(
    conversations: _ConversationPort,
    threads: ChannelThreadConversationRepoPort,
    binding: ChannelBinding,
    peer: ChannelPeer,
    thread_id: str = "",
) -> str:
    """Return this thread's active conversation, recreating it if it was deleted."""
    row = await threads.get(binding.resource_id, peer.chat_id, thread_id)
    if row is not None and row.active_conversation_id is not None:
        try:
            await conversations.get_conversation(row.active_conversation_id)
        except ConversationNotFound:
            pass
        else:
            return row.active_conversation_id
    return await open_conversation(conversations, threads, binding, peer, thread_id)


def explain_conversation_error(e: CofferError) -> str:
    """Friendly chat text for a conversation-creation failure."""
    return f"⚠️ {e} [{e.code}]"
