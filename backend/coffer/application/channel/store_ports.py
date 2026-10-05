"""The two tables a channel owns, and how they are read and written.

A channel keeps two kinds of state of its own: its pairings (which chats on the
platform belong to the owner), a vault document per channel
(``state/channel-peers/<channel name>.json``) because the pairing is the
person's and travels; and ``channel_thread_conversations``, what each of those
chats is in the middle of, history in ``runs.db``. Both name the channel by its
uid (ADR identity-is-the-uid-inside-the-file).

Split from ``ports``, which describes the TRANSPORT: what an adapter must do,
what a live binding carries, what the core may ask of the chat platform. This
file describes the STORE. Two different implementers satisfy them — a Telegram
or SeaTalk adapter one, ``infrastructure.channel.persistence`` the other — and
nothing here is about a message arriving.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class ChannelPeer:
    """One paired chat of a channel (one row in channel_peers): a person's direct
    chat, or a group one of the channel's people addressed the bot in."""

    resource_uid: str
    chat_id: str
    display_name: str
    paired_at: datetime
    # The paired sender's stable identity (Telegram from.id, SeaTalk
    # employee_code); every gate compares it. Pairing refuses a message that
    # carries none, and a group row inherits its addresser's.
    sender_id: str = ""


class ChannelPeerRepoPort(Protocol):
    """Persistence for peer bindings."""

    async def owner_peer(self, resource_uid: str) -> ChannelPeer | None:
        """The channel's OWNER chat — the one a notification addressed to the
        channel rather than to a conversation belongs in.

        A channel may hold several peers: its DM plus every group it has
        been paired to (one per chat). This
        returns the earliest-paired one, which is the first
        paired person's DM: pairing a DM is how a channel starts working at all,
        and a group can only be added to a channel that already does.

        The order matters, not just the determinism: an answer that depended on
        storage order could put a private message into a group chat.
        """
        ...

    async def get_by_chat(self, resource_uid: str, chat_id: str) -> ChannelPeer | None: ...

    async def list_by_resource(self, resource_uid: str) -> list[ChannelPeer]: ...

    async def sender_ids(self, resource_uid: str) -> frozenset[str]:
        """Every paired person's ``sender_id`` across the channel's peer rows
        (DMs, groups and threads). Empty when nobody is paired — the only state
        in which a group @mention cannot be a turn for anyone."""
        ...

    async def upsert(self, peer: ChannelPeer) -> None: ...

    async def upsert_replacing(self, peer: ChannelPeer, unpair: Sequence[str]) -> None:
        """``upsert(peer)`` and un-pair each chat in ``unpair``, as ONE write.

        A change of owner must never be half-applied: saving the new owner and
        dropping the previous one's chats either both happen or neither does,
        so a failure between them cannot leave the channel with no owner."""
        ...

    async def delete_by_sender(self, resource_uid: str, sender_id: str) -> list[str]:
        """Un-pair a person: every row carrying ``sender_id`` (their DM and the
        groups they brought the bot into), as ONE write. Returns the chats dropped
        — empty when the person was not paired."""
        ...

    async def delete_by_chat(self, resource_uid: str, chat_id: str) -> None:
        """Drop one chat's pairing, leaving the channel's other chats alone.

        Un-pairing one chat, not deleting the channel — the channel's own
        deletion takes its pairing document with it in the same commit."""
        ...


@dataclass(frozen=True)
class ChannelThreadConversation:
    """The per-thread conversation binding (one row in
    ``channel_thread_conversations``): conversation identity is keyed by
    ``(resource_uid, chat_id, thread_id)`` (see "Key conversation identity by channel,
    chat and thread"), not by the peer alone.

    ``thread_id=""`` is the DM (or a group's main chat); each thread in a group
    is an independent row with its own active conversation and its own sticky
    agent. Pairing/owner identity stays on ``ChannelPeer`` — this binding is the
    ONLY place the conversation a turn drives and the agent it opens with are
    recorded (``channel_peers`` carried a second, never-written copy of both
    until 0084 dropped them)."""

    resource_uid: str
    chat_id: str
    thread_id: str
    active_conversation_id: str | None
    # Sticky structural choice for THIS thread: which agent new conversations
    # use. ``None`` means fall back to the channel default.
    preferred_agent: str | None
    updated_at: datetime
    # Set only on a parallel thread `/thread` opened (see "Open parallel
    # conversations in a direct chat"): its number within the chat and the title
    # its mark ``🧵#N title`` is built from. ``None`` on every other row.
    parallel_ordinal: int | None = None
    parallel_title: str | None = None
    #: "direct" or "group" — which of the platform's send paths reaches this
    #: thread. ``None`` on a row written before it was recorded; set again by
    #: the next message that arrives there.
    chat_kind: str | None = None
    #: The thread's other sticky settings (spec channels "Keep a chat's agent, model
    #: and directory across its conversations"): the model and the
    #: working directory a fresh conversation here opens with. ``None`` means
    #: the agent's own default (model) or the channel's (directory).
    preferred_model: str | None = None
    preferred_cwd: str | None = None

    @property
    def parallel_mark(self) -> str | None:
        """``🧵#N title`` — the one string shown wherever a parallel thread is."""
        if self.parallel_ordinal is None:
            return None
        return parallel_mark(self.parallel_ordinal, self.parallel_title or "")


class _Keep:
    """The "leave this setting as it is" marker for ``set_preferences``."""

    def __repr__(self) -> str:
        return "KEEP"


#: Passed for a setting ``set_preferences`` must not touch (``None`` clears it).
KEEP: Any = _Keep()


@dataclass(frozen=True)
class ChannelThreadLocation:
    """Where a conversation a channel opened lives: the chat and thread that
    opened it, and which send path reaches them (one ``channel_thread_history``
    row)."""

    resource_uid: str
    chat_id: str
    thread_id: str
    chat_kind: str | None
    opened_at: datetime


def parallel_mark(ordinal: int, title: str) -> str:
    """The mark of parallel thread ``ordinal`` titled ``title``."""
    return f"🧵#{ordinal} {title}".rstrip()


class ChannelThreadConversationRepoPort(Protocol):
    """Persistence for per-thread conversation bindings (see "Key conversation identity
    by channel, chat and thread").

    The source of truth for driving a turn: which conversation a
    ``(resource_uid, chat_id, thread_id)`` resolves to, and the sticky agent it
    opens with. Two threads of one group therefore never collide on a single
    conversation (the "a turn is already running" error)."""

    async def get(
        self, resource_uid: str, chat_id: str, thread_id: str
    ) -> ChannelThreadConversation | None: ...

    async def set_active_conversation(
        self, resource_uid: str, chat_id: str, thread_id: str, conversation_id: str | None
    ) -> None:
        """Upsert the thread's active conversation, leaving ``preferred_agent``
        untouched (creating the row if this thread has none yet)."""
        ...

    async def set_preferred_agent(
        self, resource_uid: str, chat_id: str, thread_id: str, preferred_agent: str | None
    ) -> None:
        """Upsert the thread's sticky agent, leaving ``active_conversation_id``
        untouched (creating the row if this thread has none yet)."""
        ...

    async def set_preferences(
        self,
        resource_uid: str,
        chat_id: str,
        thread_id: str,
        *,
        agent: str | None = KEEP,
        model: str | None = KEEP,
        cwd: str | None = KEEP,
    ) -> None:
        """Upsert the thread's sticky settings: each one passed is written
        (``None`` clears it), each left at ``KEEP`` is untouched."""
        ...

    async def note_chat_kind(
        self, resource_uid: str, chat_id: str, thread_id: str, chat_kind: str
    ) -> None:
        """Record which send path reaches this thread (upserting the row)."""
        ...

    async def record_history(
        self,
        resource_uid: str,
        chat_id: str,
        thread_id: str,
        conversation_id: str,
        chat_kind: str | None,
    ) -> None:
        """Remember that ``conversation_id`` was opened for this thread (spec
        channels "Resume an earlier conversation from chat"). Idempotent."""
        ...

    async def history(
        self, resource_uid: str, chat_id: str, thread_id: str, *, limit: int = 20
    ) -> list[str]:
        """The conversations this thread opened, newest first."""
        ...

    async def locate(self, conversation_id: str) -> ChannelThreadLocation | None:
        """Which chat and thread opened ``conversation_id``, or ``None`` when no
        channel did."""
        ...

    async def locate_many(
        self, conversation_ids: Sequence[str]
    ) -> dict[str, tuple[ChannelThreadLocation, ChannelThreadConversation | None]]:
        """``locate`` for many conversations in ONE read, each paired with its
        thread's row (``None`` when the thread keeps none) — what the
        Conversations list's source badges are built from. A conversation no
        channel opened is absent."""
        ...

    async def next_parallel_ordinal(self, resource_uid: str, chat_id: str) -> int:
        """The number the chat's next parallel thread gets: ``max + 1`` over the
        chat's rows, so a number is never reused after a conversation is replaced
        (see "Open parallel conversations beside a direct chat"). Read before the
        thread exists, because the thread's root message carries its mark."""
        ...

    async def open_parallel(
        self, resource_uid: str, chat_id: str, thread_id: str, ordinal: int, title: str
    ) -> None:
        """Record ``thread_id`` as parallel thread ``ordinal`` of this chat
        (upserting the row, leaving its conversation and agent untouched)."""
        ...

    async def list_parallel(
        self, resource_uid: str, chat_id: str
    ) -> list[ChannelThreadConversation]:
        """The chat's parallel threads, newest (highest ordinal) first."""
        ...


@dataclass(frozen=True)
class ReplyRecord:
    """One bot reply and every platform message it was delivered as (one
    ``channel_replies`` row): a long answer is cut into parts, the files it
    carried and a details card are messages of their own, and withdrawing the
    reply takes all of them (spec channels "Withdraw a bot reply on the owner's
    command")."""

    reply_id: str
    resource_uid: str
    chat_id: str
    thread_id: str
    chat_kind: str
    message_ids: tuple[str, ...]
    sent_at: datetime


class ReplyLedgerPort(Protocol):
    """What the channel remembers about its replies, for as long as a platform
    lets one be taken back. Names no content: ids and times only."""

    async def add(self, record: ReplyRecord) -> None: ...

    async def get(self, reply_id: str) -> ReplyRecord | None: ...

    async def find_by_message(
        self, resource_uid: str, chat_id: str, message_id: str
    ) -> ReplyRecord | None:
        """The reply one of whose messages is ``message_id`` (any part)."""
        ...

    async def latest(
        self, resource_uid: str, chat_id: str, thread_id: str | None
    ) -> ReplyRecord | None:
        """The most recently sent reply in the chat; ``thread_id`` narrows it to
        one thread, ``None`` takes the whole chat."""
        ...

    async def remove(self, reply_id: str) -> None: ...

    async def prune(self, before: datetime) -> int:
        """Forget replies sent before ``before`` (past every platform's window);
        returns how many."""
        ...

    async def delete_for_channel(self, resource_uid: str) -> None: ...
