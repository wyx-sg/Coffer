"""Conversation creation for channel-driven turns — shared by the inbound
turn-driver and the command router.

A channel conversation's structural choices (agent, workspace) are resolved
from the peer's sticky preferences plus the channel defaults, then fixed at
creation; switching either opens a fresh one. These helpers are pure given
their injected ports — no per-processor state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from coffer.application.channel.conversation_spec import resolve_conversation_spec
from coffer.domain.chat.errors import AgentConfigRejected, ConversationNotFound
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.ports import ChannelBinding, ChannelPeer, ChannelPeerRepoPort


class _ConversationPort(Protocol):
    async def create_conversation(
        self, *, agent_key: str, agent_config: dict[str, Any] | None, actor: str
    ) -> Any: ...

    async def get_conversation(self, conversation_id: str) -> Any: ...


async def open_conversation(
    conversations: _ConversationPort,
    peers: ChannelPeerRepoPort,
    binding: ChannelBinding,
    peer: ChannelPeer,
) -> str:
    """Create a conversation from the peer's sticky choices + channel defaults
    (resolver) and make it the peer's active conversation."""
    spec = resolve_conversation_spec(
        default_agent=binding.default_agent,
        default_agent_config=binding.default_agent_config,
        workspaces=binding.workspaces,
        default_workspace=binding.default_workspace,
        preferred_agent=peer.preferred_agent,
        preferred_workspace=peer.preferred_workspace,
    )
    conv = await conversations.create_conversation(
        agent_key=spec.agent_key, agent_config=spec.agent_config, actor="channel"
    )
    await peers.set_active_conversation(binding.resource_id, conv.id)
    return str(conv.id)


async def ensure_conversation(
    conversations: _ConversationPort,
    peers: ChannelPeerRepoPort,
    binding: ChannelBinding,
    peer: ChannelPeer,
) -> str:
    """Return the peer's active conversation, recreating it if it was deleted."""
    if peer.active_conversation_id is not None:
        try:
            await conversations.get_conversation(peer.active_conversation_id)
        except ConversationNotFound:
            pass
        else:
            return peer.active_conversation_id
    return await open_conversation(conversations, peers, binding, peer)


def explain_conversation_error(binding: ChannelBinding, e: CofferError) -> str:
    """Friendly chat text for a conversation-creation failure — a bridged agent
    with no workspace points the owner at ``/cwd`` instead of a raw error code."""
    if isinstance(e, AgentConfigRejected) and e.reason in {"invalid_cwd", "cwd_not_a_directory"}:
        available = ", ".join(sorted(binding.workspaces)) or "(none configured)"
        return f"⚠️ That agent needs a workspace. Pick one with /cwd <name>. Available: {available}"
    return f"⚠️ {e} [{e.code}]"
