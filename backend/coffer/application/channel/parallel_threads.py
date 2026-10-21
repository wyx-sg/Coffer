"""Parallel conversations beside a direct chat: `/thread` and `/close`, the
`/status` lines listing them, and the one rule that decides which conversation
a direct-chat thread belongs to.

A direct chat is one conversation. The owner opens further ones beside it with
`/thread`, each a thread of the direct chat numbered per chat and shown
everywhere by its mark ``🧵#N title`` (spec channels "Open parallel
conversations beside a direct chat"); `/status` in the direct chat lists the
open ones. `/close` inside one closes it, and so does the idle sweep
(``thread_sweep``); a closed thread keeps its number and its conversation, a
message sent in it is answered with :data:`CLOSED_NOTICE` and runs nothing, and
`/resume` inside it reopens it (``resume_switch``).

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from coffer.application.channel.command_text import agent_display, settings_in_effect
from coffer.application.channel.conversation_ops import (
    explain_conversation_error,
    open_conversation,
)
from coffer.application.channel.ephemeral import safe_send
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import (
    ChannelThreadConversation,
    ChannelThreadConversationRepoPort,
    parallel_mark,
)
from coffer.domain.channel.commands import command_name
from coffer.domain.channel.envelopes import InboundMessage
from coffer.domain.channel.errors import ParallelThreadUnavailable
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = [
    "CLOSED_NOTICE",
    "DEFAULT_TITLE",
    "THREAD_BODY",
    "ThreadRoute",
    "answer_closed",
    "cmd_close",
    "cmd_thread",
    "conversation_thread_of",
    "route_thread",
    "thread_lines",
]

_logger = logging.getLogger(__name__)

#: The title a `/thread` with none gets.
DEFAULT_TITLE = "Task"
#: A title longer than this is cut: it names the thread in a topic name, a
#: conversation title and a `/status` line, none of which wants a paragraph.
_TITLE_MAX = 60
#: How many threads `/status` lists; the count above the list stays exact.
_LIST_MAX = 20
#: What follows the mark on the thread's root message or first topic message.
THREAD_BODY = "A parallel conversation with its own context. Reply in this thread to talk in it."
#: What a message sent in a closed parallel thread is answered with.
CLOSED_NOTICE = (
    "🔒 This thread is closed. Send /resume here to reopen it, "
    "or /thread in the chat to open a new one."
)
#: The commands that still run in a closed thread: they report, take a reply
#: back, open a new thread, or — `/resume` — reopen this one. Every other
#: message there, the commands that would open a conversation in it (`/new`,
#: `/model`, `/dir`) included, gets :data:`CLOSED_NOTICE`.
_CLOSED_THREAD_COMMANDS = frozenset({"status", "help", "del", "stop", "close", "thread", "resume"})


class _Place(Protocol):
    """Where an inbound event happened — a message, a card tap, a stop."""

    @property
    def chat_id(self) -> str: ...
    @property
    def chat_kind(self) -> str: ...
    @property
    def thread_id(self) -> str: ...


@dataclass(frozen=True)
class ThreadRoute:
    """Which conversation thread a message keys to, and whether that is a
    closed parallel thread (answered with :data:`CLOSED_NOTICE`, never a turn)."""

    conversation_thread_id: str
    closed: bool = False


async def route_thread(
    threads: ChannelThreadConversationRepoPort, binding: ChannelBinding, place: _Place
) -> ThreadRoute:
    """Which of the chat's conversations a message in ``place.thread_id`` belongs to
    (see "Key conversation identity by channel, chat and thread").

    A group thread is its own. A direct-chat thread is its own when `/thread`
    opened it, or when the transport's direct-chat threads only exist because
    someone created one (Telegram's private-chat topics). Every other direct-chat
    thread is a casual reply and keys to the direct chat's ``""`` conversation —
    it is still answered inside that thread, which is ``thread_id``'s job. A
    closed parallel thread keeps keying to itself, so nothing said there ever
    lands in the direct chat's own conversation.
    """
    thread_id = place.thread_id
    if not thread_id or place.chat_kind == "group":
        return ThreadRoute(thread_id)
    row = await threads.get(binding.resource.uid, place.chat_id, thread_id)
    if row is not None and row.parallel_closed:
        return ThreadRoute(thread_id, closed=True)
    if not binding.adapter.capabilities.direct_threads_are_replies:
        return ThreadRoute(thread_id)
    return ThreadRoute(thread_id if row is not None and row.parallel_ordinal is not None else "")


async def conversation_thread_of(
    threads: ChannelThreadConversationRepoPort, binding: ChannelBinding, place: _Place
) -> str:
    """:func:`route_thread`'s conversation thread alone."""
    return (await route_thread(threads, binding, place)).conversation_thread_id


async def answer_closed(
    binding: ChannelBinding, msg: InboundMessage, text: str, has_attachments: bool
) -> bool:
    """Answer a message sent in a closed parallel thread with
    :data:`CLOSED_NOTICE`, inside that thread; ``True`` when it was answered and
    must run nothing. A command that still works there is let through."""
    name = None if has_attachments else command_name(text)
    if name in _CLOSED_THREAD_COMMANDS:
        return False
    await safe_send(
        binding, msg.chat_id, CLOSED_NOTICE, thread_id=msg.thread_id, chat_kind=msg.chat_kind
    )
    return True


async def cmd_thread(ctx: CommandContext, text: str) -> None:
    """`/thread [title]`: open a parallel conversation beside the direct chat."""
    failure = await _open_thread(ctx, _title(text))
    if failure:
        await ctx.say(failure)


def _title(text: str) -> str:
    """The title typed after `/thread`, whitespace collapsed and cut to size."""
    title = " ".join(text.split()[1:])
    if len(title) > _TITLE_MAX:
        title = title[: _TITLE_MAX - 1].rstrip() + "…"
    return title or DEFAULT_TITLE


async def _open_thread(ctx: CommandContext, title: str) -> str:
    """Open parallel thread ``🧵#N title``; return what to answer, or "" when the
    thread itself is the answer (its root message or topic is in the chat)."""
    binding, peer = ctx.binding, ctx.peer
    threads = ctx.commands._threads
    ordinal = await threads.next_parallel_ordinal(binding.resource.uid, peer.chat_id)
    mark = parallel_mark(ordinal, title)
    # Where a direct-chat thread hangs from a message, the owner's own `/thread`
    # message is the root and the mark answers inside it. A tap on a `/thread`
    # button has no typed message, and a `/thread` sent inside a thread is
    # itself a reply (a thread cannot root another): both open a root message.
    anchor = ""
    if binding.adapter.capabilities.direct_threads_are_replies and not ctx.thread_id:
        anchor = ctx.command_message_id
    try:
        new_thread = await binding.adapter.open_thread(
            peer.chat_id, mark, THREAD_BODY, anchor_message_id=anchor
        )
    except ParallelThreadUnavailable as e:
        return str(e)
    except Exception:
        _logger.warning(
            "channel.thread.open_failed", extra={"channel": binding.resource.name}, exc_info=True
        )
        return "⚠️ Could not open a thread — try /thread again."
    await threads.open_parallel(binding.resource.uid, peer.chat_id, new_thread, ordinal, title)
    try:
        # Titled with the mark by ``open_conversation`` itself, since the row now
        # carries the ordinal.
        await open_conversation(
            ctx.commands._conversations, threads, binding, peer, new_thread, chat_kind=ctx.chat_kind
        )
    except CofferError as e:
        return explain_conversation_error(e)
    return ""


async def cmd_close(ctx: CommandContext, _text: str = "") -> None:
    """`/close` inside a parallel thread: close it. Its conversation and history
    stay; a running turn or queued messages are never dropped by it — the owner
    stops or settles them first."""
    threads = ctx.commands._threads
    row = None
    if ctx.conversation_thread_id:
        row = await threads.get(ctx.resource_uid, ctx.chat_id, ctx.conversation_thread_id)
    if row is None or row.parallel_mark is None:
        await ctx.say("Use /close inside a parallel thread.")
        return
    if row.parallel_closed:
        await ctx.say(f"{row.parallel_mark} is already closed.")
        return
    bound = row.active_conversation_id
    running = ctx.session is not None and ctx.session.running_conversation_id is not None
    if running:
        await ctx.say("A turn is running here — send /stop first, then /close.")
        return
    if bound is not None and ctx.commands._turns.pending(bound):
        await ctx.say("Messages are still queued here — let them run or discard them, then /close.")
        return
    await threads.close_parallel(ctx.resource_uid, ctx.chat_id, row.thread_id)
    await ctx.say(f"🔒 Closed {row.parallel_mark}. Send /thread in the chat to open a new one.")


async def thread_lines(ctx: CommandContext) -> list[str]:
    """The `/status` line for a direct chat's open parallel threads — their
    count, then each one's mark, agent and state, newest first:
    ``Parallel threads (2): 🧵#3 title · Codex · running; 🧵#2 title · Claude Code · idle``
    — at most 20 named, with the rest counted. Empty when the chat has none open;
    a closed thread is never listed or counted."""
    rows = await ctx.commands._threads.list_parallel(ctx.resource_uid, ctx.chat_id)
    if not rows:
        return []
    named = [await _thread_entry(ctx, row) for row in rows[:_LIST_MAX]]
    if len(rows) > _LIST_MAX:
        named.append(f"+{len(rows) - _LIST_MAX} more")
    return [f"Parallel threads ({len(rows)}): " + "; ".join(named)]


async def _thread_entry(ctx: CommandContext, row: ChannelThreadConversation) -> str:
    commands = ctx.commands
    running = commands.running_in(ctx.binding.resource.uid, ctx.chat_id, row.thread_id)
    bound = row.active_conversation_id
    waiting = len(commands._turns.pending(bound)) if bound is not None else 0
    held = commands._turns.held(bound) if bound is not None else 0
    if running is not None:
        state = "running"
    elif held:
        state = f"{held} on hold"
    elif waiting:
        state = f"{waiting} waiting"
    else:
        state = "idle"
    settings = await settings_in_effect(
        commands, ctx.binding, ctx.peer, row.thread_id, chat_kind=ctx.chat_kind
    )
    agent = agent_display(commands._agents, settings.agent)
    return f"{row.parallel_mark} · {agent} · {state}"
