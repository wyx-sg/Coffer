"""Parallel conversations in a direct chat: `/thread`, `/threads`, and the one
rule that decides which conversation a direct-chat thread belongs to.

A direct chat is one conversation. The owner opens further ones beside it with
`/thread`, each a thread of the direct chat numbered per chat and shown
everywhere by its mark ``🧵#N title`` (see "Open parallel conversations in a
direct chat"). `/status` lives here too, because inside a parallel thread it
names the mark. Split out of ``commands.py`` for that file's size budget, in the
same shape as ``model_switch``: free functions taking the owning
``ChannelCommands`` as their first argument.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from coffer.application.channel.agent_routing import effective_agent
from coffer.application.channel.conversation_ops import (
    explain_conversation_error,
    open_conversation,
)
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import (
    ChannelPeer,
    ChannelThreadConversation,
    ChannelThreadConversationRepoPort,
    parallel_mark,
)
from coffer.domain.channel.errors import ParallelThreadUnavailable
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.commands import ChannelCommands, SafeSend

__all__ = [
    "DEFAULT_TITLE",
    "GROUP_ANSWER",
    "NO_PARALLEL_THREADS",
    "THREAD_BODY",
    "dispatch",
    "resolve_conversation_thread_id",
]

_logger = logging.getLogger(__name__)

#: The title a `/thread` with none gets.
DEFAULT_TITLE = "Task"
#: A title longer than this is cut: it names the thread in a topic name, a
#: conversation title and a `/threads` line, none of which wants a paragraph.
_TITLE_MAX = 60
#: How many threads `/threads` lists; the count above the list stays exact.
_LIST_MAX = 20
#: What follows the mark on the thread's root message or first topic message.
THREAD_BODY = "A parallel conversation with its own context. Reply in this thread to talk in it."
#: `/thread` in a group, where there is nothing to open.
GROUP_ANSWER = "Every group thread is already its own conversation — just start a thread."
#: `/threads` in a chat that has none.
NO_PARALLEL_THREADS = "No parallel conversations — open one with /thread [title]."


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
    row = await threads.get(binding.resource.id, chat_id, thread_id)
    return thread_id if row is not None and row.parallel_ordinal is not None else ""


async def dispatch(
    commands: ChannelCommands,
    command: str,
    binding: ChannelBinding,
    peer: ChannelPeer,
    text: str,
    session: Any,
    send: SafeSend,
    *,
    chat_kind: str,
    thread_id: str,
    conversation_thread_id: str,
) -> None:
    """Answer `/status`, `/thread` or `/threads`."""

    async def say(answer: str) -> None:
        await send(binding, peer.chat_id, answer, chat_kind=chat_kind, thread_id=thread_id)

    if command == "/status":
        await say(await _status(commands, binding, peer, session, conversation_thread_id))
    elif command == "/thread":
        if chat_kind == "group":
            await say(GROUP_ANSWER)
            return
        failure = await _open_thread(commands, binding, peer, _title(text))
        if failure:
            await say(failure)
    else:
        await say(await _list_threads(commands, binding, peer))


async def _status(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    session: Any,
    conversation_thread_id: str,
) -> str:
    row = await commands._threads.get(binding.resource.id, peer.chat_id, conversation_thread_id)
    bound = row.active_conversation_id if row is not None else None
    agent = effective_agent(binding, row.preferred_agent if row is not None else None)
    running = session.running_conversation_id is not None
    # The queue is the conversation's own (spec chat "Queue messages sent during
    # a turn") — the same one the web's pending chips show.
    queued = len(commands._turns.pending(bound)) if bound is not None else 0
    lines = [
        f"Conversation: {bound or 'none yet'}",
        f"Agent: {agent}",
        f"Turn running: {'yes' if running else 'no'}",
        f"Queued: {queued}",
    ]
    mark = row.parallel_mark if row is not None else None
    return "\n".join([mark, *lines] if mark else lines)


def _title(text: str) -> str:
    """The title typed after `/thread`, whitespace collapsed and cut to size."""
    title = " ".join(text.split()[1:])
    if len(title) > _TITLE_MAX:
        title = title[: _TITLE_MAX - 1].rstrip() + "…"
    return title or DEFAULT_TITLE


async def _open_thread(
    commands: ChannelCommands, binding: ChannelBinding, peer: ChannelPeer, title: str
) -> str:
    """Open parallel thread ``🧵#N title``; return what to answer, or "" when the
    thread itself is the answer (its root message or topic is in the chat)."""
    threads = commands._threads
    ordinal = await threads.next_parallel_ordinal(binding.resource.id, peer.chat_id)
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
    await threads.open_parallel(binding.resource.id, peer.chat_id, new_thread, ordinal, title)
    try:
        # Titled with the mark by ``open_conversation`` itself, since the row now
        # carries the ordinal.
        await open_conversation(commands._conversations, threads, binding, peer, new_thread)
    except CofferError as e:
        return explain_conversation_error(e)
    return ""


async def _list_threads(
    commands: ChannelCommands, binding: ChannelBinding, peer: ChannelPeer
) -> str:
    rows = await commands._threads.list_parallel(binding.resource.id, peer.chat_id)
    if not rows:
        return NO_PARALLEL_THREADS
    noun = "conversation" if len(rows) == 1 else "conversations"
    lines = [f"{len(rows)} parallel {noun}:"]
    lines += [_thread_line(commands, binding, peer, row) for row in rows[:_LIST_MAX]]
    return "\n".join(lines)


def _thread_line(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    row: ChannelThreadConversation,
) -> str:
    agent = effective_agent(binding, row.preferred_agent)
    running = commands.running_in(binding.resource.name, peer.chat_id, row.thread_id)
    bound = row.active_conversation_id
    waiting = len(commands._turns.pending(bound)) if bound is not None else 0
    if running is not None:
        state = "running"
    elif waiting:
        state = f"{waiting} waiting"
    else:
        state = "idle"
    return f"{row.parallel_mark} — {agent} — {state}"
