"""The typing heartbeat a turn keeps up while it runs.

Spec channels "Send only the answer, once the turn is done": nothing is posted
while a turn runs; the chat shows only that the bot is typing, and the finished
reply is one new message.
"""

from __future__ import annotations

import asyncio
import contextlib

from coffer.application.channel.ports import ChannelAdapter

__all__ = ["typing_heartbeat"]


async def typing_heartbeat(
    adapter: ChannelAdapter, chat_id: str, thread_id: str, chat_kind: str, seconds: float
) -> None:
    """Re-send the typing indicator every ``seconds`` until cancelled; the
    first one went out on receipt.

    Best-effort: a failed heartbeat never breaks the turn."""
    while True:
        await asyncio.sleep(seconds)
        with contextlib.suppress(Exception):
            await adapter.send_typing(chat_id, thread_id=thread_id, chat_kind=chat_kind)
