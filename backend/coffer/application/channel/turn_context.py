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

import dataclasses
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
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.domain.channel.thread_messages import ThreadMessage
from coffer.domain.channel.turn_content import ContextBlock

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
    """Reads the blocks that ground a message: its thread's slice and its quote."""

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
        *,
        conversation_thread_id: str,
    ) -> tuple[ContextBlock, ...]:
        """The blocks that ground ``msg``: its thread's slice, then the message it
        quotes — the order the turn reads them in, right above the message itself,
        so "repeat this" or "as above" points at something the agent can see.

        Each block carries the images/files its messages hold (see "Download the
        media a thread's messages carry"). A quote the platform inlined on the
        update (``msg.quoted_items``) needs no read. Either read degrading to
        nothing leaves its block out.
        """
        blocks: list[ContextBlock] = []
        if msg.quoted_items:
            blocks.append(ContextBlock(kind="quote", items=msg.quoted_items))
        if not binding.adapter.capabilities.supports_history_fetch:
            return tuple(blocks)
        fetcher = cast(ContextFetchPort, binding.adapter)
        if msg.quoted_message_id and not msg.quoted_items:
            items, quoted_atts = await fetcher.fetch_quoted(msg.quoted_message_id)
            if items or quoted_atts:
                blocks.append(
                    ContextBlock(kind="quote", items=tuple(items), media=tuple(quoted_atts))
                )
        if msg.thread_id:
            # Ground the turn in the thread's own conversation — in a DM just as much
            # as in a group: ``chat_kind`` only picks which endpoint the adapter
            # calls. Group-MAIN chatter is never read.
            thread = await self._thread(fetcher, binding, msg, conversation_thread_id)
            if thread is not None and not thread.empty:
                blocks.insert(0, thread)
        return tuple(blocks)

    async def _thread(
        self,
        fetcher: ContextFetchPort,
        binding: ChannelBinding,
        msg: InboundMessage,
        conversation_thread_id: str,
    ) -> ContextBlock | None:
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
        block: ContextBlock | None = None
        read_ok = True
        # A message that roots a fresh thread at itself (thread_id == its own id)
        # holds nothing else yet — nothing to read, only a place to mark.
        if msg.thread_id != msg.platform_message_id:
            block, read_ok = await self._slice(fetcher, binding, msg, cursor)
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
        return block

    async def _slice(
        self,
        fetcher: ContextFetchPort,
        binding: ChannelBinding,
        msg: InboundMessage,
        cursor: ThreadCursor | None,
    ) -> tuple[ContextBlock | None, bool]:
        """The folded block (with its media), and whether the read succeeded."""
        read = await fetcher.fetch_thread(msg.chat_id, msg.thread_id, chat_kind=msg.chat_kind)
        if read.failed:
            return None, False
        others = [m for m in read.messages if m.message_id != msg.platform_message_id]
        if cursor is None:
            # First turn of this conversation here: the thread's latest messages,
            # its replies included — this conversation has not seen any of them.
            picked, new_since = others, False
        else:
            # The conversation's own session holds everything up to its last turn
            # here, and its own replies; only what others posted since is news.
            picked, new_since = [], True
            for message in _since(others, cursor):
                if message.from_bot or await self._replies.find_by_message(
                    binding.resource.uid, msg.chat_id, message.message_id
                ):
                    continue
                picked.append(message)
        omitted = max(0, len(picked) - THREAD_FOLD_LIMIT)
        shown = picked[omitted:]
        items = [item for m in shown for item in _timed(m)]
        notes: list[str] = []
        if read.window_note and cursor is None:
            notes.append(read.window_note)
        if omitted and shown:
            notes.append(older_messages_note(binding, msg, omitted, shown[0].message_id))
        media: list[InboundAttachment] = []
        for message in shown:
            if message.has_media:
                media.extend(await fetcher.fetch_message_media(message))
        return (
            ContextBlock(
                kind="thread",
                items=tuple(items),
                media=tuple(media),
                new_since=new_since,
                notes=tuple(notes),
            ),
            True,
        )


def _timed(message: ThreadMessage) -> tuple[ForwardedItem, ...]:
    """A thread message's lines, the one-line message stamped with when it was
    sent. A forwarded record's leaves keep their own times: the thread message's
    is when it was forwarded, not when they were written."""
    if len(message.items) == 1 and message.items[0].sent_at is None and message.sent_at:
        return (dataclasses.replace(message.items[0], sent_at=message.sent_at),)
    return message.items
