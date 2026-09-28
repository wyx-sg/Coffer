"""Opening a parallel thread on Telegram: a private-chat topic.

Bot API 9.4 lets a bot create forum topics in a private chat, once its owner
has turned on Threaded Mode for it in BotFather. A topic is where a parallel
conversation lives (spec channels/telegram "Open a parallel thread as a
private-chat topic"): ``createForumTopic`` names it with the mark and hands back
its ``message_thread_id``, which every message in it then carries inbound.

Split out of ``telegram.py`` for that file's size budget.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from coffer.domain.channel.envelopes import SentMessage
from coffer.domain.channel.errors import ChannelSendFailed, ParallelThreadUnavailable

__all__ = ["TOPICS_OFF", "open_private_topic"]

#: What `/thread` answers when the platform refuses to create the topic — the
#: one lever the owner has.
TOPICS_OFF = (
    "Telegram topics are off for this bot — turn on Threaded Mode for it in BotFather, "
    "then try /thread again."
)

#: Telegram's cap on a topic name.
_NAME_MAX = 128


async def open_private_topic(
    call: Callable[..., Awaitable[Any]],
    send_text: Callable[..., Awaitable[SentMessage]],
    chat_id: str,
    mark: str,
    body: str,
) -> str:
    """Create a topic named ``mark`` in private chat ``chat_id``, post the mark
    and ``body`` into it, and return its thread id."""
    try:
        topic = await call("createForumTopic", chat_id=chat_id, name=mark[:_NAME_MAX])
    except ChannelSendFailed as e:
        # A 400 is the platform saying this chat cannot have topics — in a
        # private chat, that the bot's Threaded Mode is off. Anything else (a
        # timeout, a rate limit) is not the owner's setting and surfaces as is.
        if e.api_rejected and e.status == 400:
            raise ParallelThreadUnavailable(TOPICS_OFF) from e
        raise
    thread_id = str((topic or {}).get("message_thread_id") or "")
    if not thread_id:
        raise RuntimeError("createForumTopic returned no message_thread_id")
    await send_text(chat_id, f"{mark}\n{body}", thread_id=thread_id)
    return thread_id
