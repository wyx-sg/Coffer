"""Grounding an inbound turn in what surrounds it: its thread and the message it quotes.

Both reads go through the adapter's ``ContextFetchPort`` and only on a transport
that declares ``supports_history_fetch`` — a platform that inlines a quote on the
update itself (Telegram's ``reply_to_message``) has already folded it into the
message text, and one with no history API has no thread to read.

A thread is folded in a bounded slice, never whole (spec channels "Ground a
thread turn in a bounded slice of the thread"): the conversation the turn runs
in already holds what earlier turns there were given, so a conversation's first
turn in a thread gets the thread's latest messages and every later turn only
what was posted since. Older messages stay one tool call away
(``coffer__channel_read_thread``, :mod:`thread_tool`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import cast

from coffer.application.channel.conversation_ops import ConversationPort, predict_conversation
from coffer.application.channel.ports import ChannelBinding, ContextFetchPort
from coffer.application.channel.store_ports import (
    PENDING_CONVERSATION,
    ChannelThreadConversationRepoPort,
    ReplyLedgerPort,
    ThreadCursor,
    ThreadCursorPort,
)
from coffer.domain.channel.envelopes import InboundAttachment, InboundMessage
from coffer.domain.channel.rich_content import ForwardedItem, flatten_context, quote_prefix
from coffer.domain.channel.thread_messages import ThreadMessage
from coffer.domain.chat.attachment import Attachment

__all__ = [
    "READ_THREAD_TOOL",
    "THREAD_FOLD_LIMIT",
    "ThreadContextFolder",
    "older_messages_note",
]

#: The most thread messages one turn folds in; the rest are named in a note.
THREAD_FOLD_LIMIT = 20

#: The built-in tool an agent reads the omitted messages with.
READ_THREAD_TOOL = "coffer__channel_read_thread"

#: A cursor taken for a conversation the turn was about to open, which that turn
#: never claimed (its conversation failed to open), stops counting after this —
#: the next conversation must not start mid-thread on a stale mark.
PENDING_TTL = timedelta(minutes=10)

_SEED_TITLE = "Thread messages"
_NEW_TITLE = "New thread messages since your last turn in this thread"


def older_messages_note(
    binding: ChannelBinding, msg: InboundMessage, omitted: int, before: str
) -> str:
    """The one line that says older messages exist and how to read them."""
    noun = "message" if omitted == 1 else "messages"
    return (
        f"{omitted} earlier {noun} in this thread are not shown. To read them, call "
        f'{READ_THREAD_TOOL} with channel "{binding.resource.uid}", chat_id '
        f'"{msg.chat_id}", chat_kind "{msg.chat_kind}", thread_id "{msg.thread_id}" '
        f'and before "{before}".'
    )


def _since(messages: Sequence[ThreadMessage], cursor: ThreadCursor) -> list[ThreadMessage]:
    """The messages after the cursor's: by id while the platform still returns
    that message, else by the time it was sent."""
    for index, message in enumerate(messages):
        if message.message_id == cursor.last_message_id:
            return list(messages[index + 1 :])
    return [m for m in messages if m.sent_at is not None and m.sent_at > cursor.last_message_at]


class ThreadContextFolder:
    """Folds a message's quote and its thread's slice into the turn text."""

    def __init__(
        self,
        *,
        threads: ChannelThreadConversationRepoPort,
        conversations: ConversationPort,
        cursors: ThreadCursorPort,
        replies: ReplyLedgerPort,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._threads = threads
        self._conversations = conversations
        self._cursors = cursors
        self._replies = replies
        self._now = now

    async def fold(
        self,
        binding: ChannelBinding,
        msg: InboundMessage,
        text: str,
        attachments: tuple[Attachment, ...],
        *,
        conversation_thread_id: str,
    ) -> tuple[str, tuple[Attachment, ...]]:
        """Return ``text`` and ``attachments`` with the thread and the quote folded in.

        The turn reads, top to bottom: the thread's slice, the quoted message as
        ``> sender: …`` lines, then the message itself — so "repeat this" or "as
        above" points at something the agent can actually see. Every image/file
        those messages carry is appended to ``attachments`` (see "Download the
        media a thread's messages carry"). Either read degrading to nothing
        leaves the turn as it was.
        """
        if not binding.adapter.capabilities.supports_history_fetch:
            return text, attachments
        fetcher = cast(ContextFetchPort, binding.adapter)
        fetched: list[InboundAttachment] = []
        if msg.quoted_message_id:
            # The quote is the reference the message leans on, so it sits right above it.
            items, quoted_atts = await fetcher.fetch_quoted(msg.quoted_message_id)
            quote = "".join(quote_prefix(it.sender, it.text) for it in items)
            text = f"{quote}{text}".rstrip("\n") if quote else text
            fetched.extend(quoted_atts)
        if msg.thread_id:
            # Ground the turn in the thread's own conversation — in a DM just as much
            # as in a group: ``chat_kind`` only picks which endpoint the adapter
            # calls. Group-MAIN chatter is never read.
            ctx, thread_atts = await self._thread(fetcher, binding, msg, conversation_thread_id)
            if ctx:
                text = f"{ctx}\n\n{text}" if text else ctx
            fetched[:0] = thread_atts
        return text, attachments + tuple(
            Attachment(path=a.path, mime=a.mime, filename=a.filename) for a in fetched
        )

    async def _thread(
        self,
        fetcher: ContextFetchPort,
        binding: ChannelBinding,
        msg: InboundMessage,
        conversation_thread_id: str,
    ) -> tuple[str, list[InboundAttachment]]:
        uid = binding.resource.uid
        conversation = await predict_conversation(
            self._conversations,
            self._threads,
            uid,
            msg.chat_id,
            conversation_thread_id,
            idle_hours=binding.new_conversation_after_idle_hours,
            now=self._now,
        )
        key = conversation or PENDING_CONVERSATION
        cursor = await self._cursors.get(uid, msg.chat_id, msg.thread_id, key)
        stale = cursor is not None and self._now() - cursor.updated_at > PENDING_TTL
        if key == PENDING_CONVERSATION and stale:
            cursor = None
        media: list[InboundAttachment] = []
        block, read_ok = "", True
        # A message that roots a fresh thread at itself (thread_id == its own id)
        # holds nothing else yet — nothing to read, only a place to mark.
        if msg.thread_id != msg.platform_message_id:
            block, media, read_ok = await self._slice(fetcher, binding, msg, cursor)
        if read_ok:
            now = self._now()
            await self._cursors.put(
                ThreadCursor(
                    resource_uid=uid,
                    chat_id=msg.chat_id,
                    thread_id=msg.thread_id,
                    conversation_id=key,
                    last_message_id=msg.platform_message_id,
                    last_message_at=msg.timestamp,
                    updated_at=now,
                )
            )
        return block, media

    async def _slice(
        self,
        fetcher: ContextFetchPort,
        binding: ChannelBinding,
        msg: InboundMessage,
        cursor: ThreadCursor | None,
    ) -> tuple[str, list[InboundAttachment], bool]:
        """The folded block, its media, and whether the read succeeded."""
        read = await fetcher.fetch_thread(msg.chat_id, msg.thread_id, chat_kind=msg.chat_kind)
        if read.failed:
            return "", [], False
        others = [m for m in read.messages if m.message_id != msg.platform_message_id]
        if cursor is None:
            # First turn of this conversation here: the thread's latest messages,
            # its replies included — this conversation has not seen any of them.
            picked, title = others, _SEED_TITLE
        else:
            # The conversation's own session holds everything up to its last turn
            # here, and its own replies; only what others posted since is news.
            picked, title = [], _NEW_TITLE
            for message in _since(others, cursor):
                if message.from_bot or await self._replies.find_by_message(
                    binding.resource.uid, msg.chat_id, message.message_id
                ):
                    continue
                picked.append(message)
        omitted = max(0, len(picked) - THREAD_FOLD_LIMIT)
        shown = picked[omitted:]
        items: list[ForwardedItem] = [item for m in shown for item in m.items]
        if read.window_note and cursor is None:
            items.append(ForwardedItem(sender="note", text=read.window_note))
        if omitted and shown:
            note = older_messages_note(binding, msg, omitted, shown[0].message_id)
            items.append(ForwardedItem(sender="note", text=note))
        media: list[InboundAttachment] = []
        for message in shown:
            if message.has_media:
                media.extend(await fetcher.fetch_message_media(message))
        return flatten_context(items, title=title), media, True
