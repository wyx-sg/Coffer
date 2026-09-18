"""The two tables a channel owns, and how they are read and written.

A channel keeps exactly two rows of its own: ``channel_peers``, which says
which chats on the platform belong to the owner, and
``channel_thread_conversations``, which says what each of those chats is in the
middle of. Both hang off ``resources.id`` — the integer surrogate key, not the
uid — because they are this machine's rows about this machine's channel, and
the FK cascade that drops them with the channel is the whole reason that column
exists (ADR resource-identity-is-an-immutable-uid).

Split from ``ports``, which describes the TRANSPORT: what an adapter must do,
what a live binding carries, what the core may ask of the chat platform. This
file describes the STORE. Two different implementers satisfy them — a Telegram
or SeaTalk adapter one, ``infrastructure.channel.persistence`` the other — and
nothing here is about a message arriving.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ChannelPeer:
    """The paired owner of a channel (one row in channel_peers)."""

    resource_id: int
    chat_id: str
    display_name: str
    paired_at: datetime
    # The paired sender's stable identity (Telegram from.id, SeaTalk
    # employee_code); the owner gate checks it when present. ``None`` on rows
    # paired before the gate gained sender awareness → chat-id-only fallback.
    sender_id: str | None = None


class ChannelPeerRepoPort(Protocol):
    """Persistence for peer bindings."""

    async def owner_peer(self, resource_id: int) -> ChannelPeer | None:
        """The channel's OWNER chat — the one a notification addressed to the
        channel rather than to a conversation belongs in.

        A channel may hold several peer rows: its DM plus every group it has
        been paired to (``UniqueConstraint("resource_id", "chat_id")``). This
        returns the earliest-paired one, which under the single-owner premise is
        the owner's DM: pairing the DM is how a channel starts working at all,
        and a group can only be added to a channel that already does.

        The order matters, not just the determinism. The predecessor of this
        method selected on ``resource_id`` with no ``ORDER BY``, so ``notify``
        could put a private message into a group chat depending on what SQLite
        happened to return first.
        """
        ...

    async def get_by_chat(self, resource_id: int, chat_id: str) -> ChannelPeer | None: ...

    async def list_by_resource(self, resource_id: int) -> list[ChannelPeer]: ...

    async def owner_sender_id(self, resource_id: int) -> str | None:
        """The first non-null ``sender_id`` paired for this channel, across
        all its peer rows (DM + any groups/threads). ``None`` when the
        channel has no peer with a known sender identity."""
        ...

    async def upsert(self, peer: ChannelPeer) -> None: ...

    async def delete_by_chat(self, resource_id: int, chat_id: str) -> None:
        """Drop one chat's pairing, leaving the channel's other chats alone.

        Un-pairing one chat, not deleting the channel — the channel's own
        deletion takes every peer with it through the FK cascade. Exists for
        the synced pairing area, where another machine's un-pair arrives as the
        deletion of one document."""
        ...


@dataclass(frozen=True)
class ChannelThreadConversation:
    """The per-thread conversation binding (one row in
    ``channel_thread_conversations``): conversation identity is keyed by
    ``(resource_id, chat_id, thread_id)`` (FR-033), not by the peer alone.

    ``thread_id=""`` is the DM (or a group's main chat); each thread in a group
    is an independent row with its own active conversation and its own sticky
    agent. Pairing/owner identity stays on ``ChannelPeer`` — this binding is the
    ONLY place the conversation a turn drives and the agent it opens with are
    recorded (``channel_peers`` carried a second, never-written copy of both
    until 0084 dropped them)."""

    resource_id: int
    chat_id: str
    thread_id: str
    active_conversation_id: str | None
    # Sticky structural choice for THIS thread: which agent new conversations
    # use. ``None`` means fall back to the channel default.
    preferred_agent: str | None
    updated_at: datetime


class ChannelThreadConversationRepoPort(Protocol):
    """Persistence for per-thread conversation bindings (FR-033).

    The source of truth for driving a turn: which conversation a
    ``(resource_id, chat_id, thread_id)`` resolves to, and the sticky agent it
    opens with. Two threads of one group therefore never collide on a single
    conversation (the "a turn is already running" error)."""

    async def get(
        self, resource_id: int, chat_id: str, thread_id: str
    ) -> ChannelThreadConversation | None: ...

    async def set_active_conversation(
        self, resource_id: int, chat_id: str, thread_id: str, conversation_id: str | None
    ) -> None:
        """Upsert the thread's active conversation, leaving ``preferred_agent``
        untouched (creating the row if this thread has none yet)."""
        ...

    async def set_preferred_agent(
        self, resource_id: int, chat_id: str, thread_id: str, preferred_agent: str | None
    ) -> None:
        """Upsert the thread's sticky agent, leaving ``active_conversation_id``
        untouched (creating the row if this thread has none yet)."""
        ...
