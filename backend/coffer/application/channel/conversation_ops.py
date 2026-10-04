"""Conversation creation for channel-driven turns — shared by the inbound
turn-driver and the command router.

A channel conversation's structural choice (agent) is resolved from the
peer's sticky preference plus the channel default, then fixed at creation;
switching opens a fresh conversation. These helpers are pure given their
injected ports — no per-processor state.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from coffer.application.channel.conversation_spec import resolve_conversation_spec
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.errors import ConversationNotFound
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import (
    ChannelPeer,
    ChannelThreadConversation,
    ChannelThreadConversationRepoPort,
)

__all__ = [
    "ConversationPort",
    "ensure_conversation",
    "explain_conversation_error",
    "inherited_setting",
    "open_conversation",
]


class ConversationPort(Protocol):
    """The slice of the chat platform's conversation service the channel core
    uses — declared once, here, for the turn driver, the command router and
    these helpers alike."""

    async def create_conversation(
        self,
        *,
        agent_key: str,
        agent_config: dict[str, Any] | None,
        channel_uid: str | None = None,
        peer_chat_id: str | None = None,
    ) -> Any: ...

    async def get_conversation(self, conversation_id: str) -> Any: ...

    async def get_agent_config(self, conversation_id: str) -> AgentConfig: ...

    async def set_agent_config(self, conversation_id: str, config: AgentConfig) -> None: ...

    async def rename_conversation(self, conversation_id: str, *, new_title: str) -> Any: ...


def inherited_setting(
    row: ChannelThreadConversation | None,
    group: ChannelThreadConversation | None,
    field: str,
) -> str | None:
    """One sticky ``preferred_*`` setting of a thread: its own, else its group's
    (spec channels "Keep a chat's settings across its conversations").

    The group's model and effort were chosen for the group's agent, so a thread
    that switched to another agent does not inherit them; its directory it
    does."""
    own: str | None = getattr(row, field) if row is not None else None
    if own or group is None:
        return own
    own_agent = row.preferred_agent if row is not None else None
    if field in ("preferred_model", "preferred_effort") and own_agent not in (
        None,
        group.preferred_agent,
    ):
        return None
    inherited: str | None = getattr(group, field)
    return inherited


async def open_conversation(
    conversations: ConversationPort,
    threads: ChannelThreadConversationRepoPort,
    binding: ChannelBinding,
    peer: ChannelPeer,
    thread_id: str = "",
    *,
    chat_kind: str | None = None,
) -> str:
    """Create a conversation from this thread's sticky settings + channel defaults
    (resolver) and make it the thread's active conversation (see "Key conversation
    identity by channel, chat and thread").

    Conversation identity is per ``(resource_uid, chat_id, thread_id)`` — a DM
    (``thread_id=""``) and each group thread open independently, so concurrent
    turns in different threads never collide on one conversation. A group
    thread with no setting of its own takes the group's defaults, which live on
    the group's ``""`` row (see "Set a group's defaults from its main chat").
    The conversation is recorded in the thread's history, which `/resume` lists
    and a web reply is mirrored back through."""
    row = await threads.get(binding.resource.uid, peer.chat_id, thread_id)
    kind = chat_kind or (row.chat_kind if row is not None else None)
    group = None
    if thread_id and kind == "group":
        group = await threads.get(binding.resource.uid, peer.chat_id, "")

    def pick(field: str) -> str | None:
        return inherited_setting(row, group, field)

    spec = resolve_conversation_spec(
        default_agent=binding.default_agent,
        default_agent_config=binding.default_agent_config,
        preferred_agent=pick("preferred_agent"),
        agent_scope=binding.agent_scope,
        preferred_model=pick("preferred_model"),
        preferred_effort=pick("preferred_effort"),
        preferred_cwd=pick("preferred_cwd"),
    )
    conv = await conversations.create_conversation(
        agent_key=spec.agent_key,
        agent_config=spec.agent_config,
        # The channel's uid, not its name: this is the return address a relayed
        # reply comes back to, and it has to keep naming the same channel after
        # the owner renames it (ADR identity-is-the-uid-inside-the-file).
        channel_uid=binding.resource.uid,
        peer_chat_id=peer.chat_id,
    )
    mark = row.parallel_mark if row is not None else None
    if mark is not None:
        # A parallel thread's conversation is titled with its mark, however it
        # was (re)opened — `/thread` itself, `/new` inside it, a deleted one
        # recreated (see "Open parallel conversations beside a direct chat"). Named
        # before its first message, so that message's words never replace it,
        # and before it becomes the thread's active one, so nothing that finds
        # it through the thread ever sees it untitled.
        await conversations.rename_conversation(str(conv.id), new_title=mark)
    await threads.record_history(binding.resource.uid, peer.chat_id, thread_id, str(conv.id), kind)
    if chat_kind and (row is None or row.chat_kind != chat_kind):
        await threads.note_chat_kind(binding.resource.uid, peer.chat_id, thread_id, chat_kind)
    await threads.set_active_conversation(binding.resource.uid, peer.chat_id, thread_id, conv.id)
    return str(conv.id)


def idle_notice(idle_hours: float) -> str:
    """The one line a chat is told when idle time rolled it into a new conversation."""
    return f"🆕 Started a new conversation after {idle_hours:g} h idle."


async def ensure_conversation(
    conversations: ConversationPort,
    threads: ChannelThreadConversationRepoPort,
    binding: ChannelBinding,
    peer: ChannelPeer,
    thread_id: str = "",
    *,
    chat_kind: str | None = None,
    idle_hours: float = 0,
    say: Callable[[str], Awaitable[None]] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
) -> str:
    """Return this thread's active conversation, opening a new one when there is
    nothing usable to continue.

    "Nothing usable" is three cases: the conversation was deleted, it was
    archived (a message to an archived conversation opens a new one and never
    revives it — spec channels "Open a new conversation when the active one is
    archived"), or the thread sat idle longer than ``idle_hours`` (spec channels
    "Open a new conversation after an idle period"; 0 never rolls over). Only
    the idle case speaks, through ``say``: the old conversation stays in the list
    and the owner should know why the agent no longer remembers it.

    ``chat_kind`` (when the caller knows it) is remembered on the thread and on
    the conversation's history row, so a reply typed on the web knows which of
    the platform's send paths reaches this thread."""
    row = await threads.get(binding.resource.uid, peer.chat_id, thread_id)
    if row is not None and row.active_conversation_id is not None:
        try:
            current = await conversations.get_conversation(row.active_conversation_id)
        except ConversationNotFound:
            current = None
        if current is not None and current.archived_at is None:
            if idle_hours > 0 and now() - current.updated_at > timedelta(hours=idle_hours):
                opened = await open_conversation(
                    conversations, threads, binding, peer, thread_id, chat_kind=chat_kind
                )
                if say is not None:
                    await say(idle_notice(idle_hours))
                return opened
            if chat_kind and row.chat_kind != chat_kind:
                await threads.note_chat_kind(
                    binding.resource.uid, peer.chat_id, thread_id, chat_kind
                )
                await threads.record_history(
                    binding.resource.uid,
                    peer.chat_id,
                    thread_id,
                    row.active_conversation_id,
                    chat_kind,
                )
            return row.active_conversation_id
    return await open_conversation(
        conversations, threads, binding, peer, thread_id, chat_kind=chat_kind
    )


def explain_conversation_error(e: CofferError) -> str:
    """Friendly chat text for a conversation-creation failure."""
    return f"⚠️ {e} [{e.code}]"
