"""Parallel conversations beside a direct chat: `/thread`, the `/status` lines
listing them, and the one rule that decides which conversation a direct-chat
thread belongs to.

A direct chat is one conversation. The owner opens further ones beside it with
`/thread`, each a thread of the direct chat numbered per chat and shown
everywhere by its mark ``🧵#N title`` (spec channels "Open parallel
conversations beside a direct chat"); `/status` in the direct chat lists them.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from coffer.application.channel.conversation_ops import (
    explain_conversation_error,
    open_conversation,
)
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import (
    ChannelThreadConversation,
    ChannelThreadConversationRepoPort,
    parallel_mark,
)
from coffer.domain.channel.errors import ParallelThreadUnavailable
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = [
    "DEFAULT_TITLE",
    "GROUP_ANSWER",
    "THREAD_BODY",
    "cmd_thread",
    "resolve_conversation_thread_id",
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
#: `/thread` in a group, where there is nothing to open.
GROUP_ANSWER = "Every group thread is already its own conversation — just start a thread."


async def resolve_conversation_thread_id(
    threads: ChannelThreadConversationRepoPort,
    binding: ChannelBinding,
    chat_id: str,
    *,
    chat_kind: str,
    thread_id: str,
) -> str:
    """Which of the chat's conversations a message in ``thread_id`` belongs to
    (see "Key conversation identity by channel, chat and thread").

    A group thread is its own. A direct-chat thread is its own when `/thread`
    opened it, or when the transport's direct-chat threads only exist because
    someone created one (Telegram's private-chat topics). Every other direct-chat
    thread is a casual reply and keys to the direct chat's ``""`` conversation —
    it is still answered inside that thread, which is ``thread_id``'s job.
    """
    if not thread_id or chat_kind == "group":
        return thread_id
    if not binding.adapter.capabilities.direct_threads_are_replies:
        return thread_id
    row = await threads.get(binding.resource.uid, chat_id, thread_id)
    return thread_id if row is not None and row.parallel_ordinal is not None else ""


async def cmd_thread(ctx: CommandContext, text: str) -> None:
    """`/thread [title]`: open a parallel conversation beside the direct chat."""
    if ctx.chat_kind == "group":
        await ctx.say(GROUP_ANSWER)
        return
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
    try:
        new_thread = await binding.adapter.open_thread(peer.chat_id, mark, THREAD_BODY)
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


async def thread_lines(ctx: CommandContext) -> list[str]:
    """The `/status` line for a direct chat's parallel threads:
    ``Parallel threads: 🧵#2 title (idle) · 🧵#3 title (running)`` — at most 20
    named, with the rest counted. Empty when the chat has none."""
    rows = await ctx.commands._threads.list_parallel(ctx.resource_uid, ctx.chat_id)
    if not rows:
        return []
    named = [await _thread_entry(ctx, row) for row in rows[:_LIST_MAX]]
    if len(rows) > _LIST_MAX:
        named.append(f"+{len(rows) - _LIST_MAX} more")
    return ["Parallel threads: " + " · ".join(named)]


async def _thread_entry(ctx: CommandContext, row: ChannelThreadConversation) -> str:
    commands = ctx.commands
    running = commands.running_in(ctx.binding.resource.name, ctx.chat_id, row.thread_id)
    bound = row.active_conversation_id
    waiting = len(commands._turns.pending(bound)) if bound is not None else 0
    if running is not None:
        state = "running"
    elif waiting:
        state = f"{waiting} waiting"
    else:
        state = "idle"
    return f"{row.parallel_mark} ({state})"
