"""The SeaTalk outbound text path: markdown in, delivered message(s) out.

Split out of ``seatalk.py`` (at its size cap) the same way ``telegram_send.py``
was split out of ``telegram.py``: the adapter keeps the port method, the wire
shaping — card vs text, markdown rendering, the two-stage chunk-then-byte-split
— lives here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from coffer.domain.channel.envelopes import ChoiceButton, SentMessage
from coffer.infrastructure.channel.render import chunk_text, markdown_to_seatalk
from coffer.infrastructure.channel.seatalk_parse import interactive_card, split_to_byte_limit

__all__ = ["send_text_pieces"]

#: ``(chat_id, message, thread_id, chat_kind) -> platform result`` — the
#: adapter's own group/single-chat router.
Send = Callable[[str, dict[str, Any], str, str], Awaitable[Any]]


async def send_text_pieces(
    send: Send,
    chat_id: str,
    markdown: str,
    *,
    char_limit: int,
    byte_limit: int,
    buttons: Sequence[ChoiceButton] | None = None,
    title: str = "",
    thread_id: str = "",
    chat_kind: str = "direct",
) -> SentMessage:
    """Deliver ``markdown`` as a card (when ``buttons`` are given) or as one or
    more text messages; return the last delivered message's handle."""
    if buttons:
        # Selection prompts are short — one interactive card, no chunking.
        # (A card description renders SeaTalk markdown but NOT tables.)
        result = await send(
            chat_id,
            interactive_card(markdown_to_seatalk(markdown), buttons, title=title),
            thread_id,
            chat_kind,
        )
        return SentMessage(message_id=str(result.get("message_id", "")))
    last = ""
    for chunk in chunk_text(markdown, char_limit):
        # Render before the byte split so escaping cannot push a piece past the
        # platform's byte cap.
        for piece in split_to_byte_limit(markdown_to_seatalk(chunk), byte_limit):
            result = await send(
                chat_id,
                {"tag": "text", "text": {"format": 1, "content": piece}},
                thread_id,
                chat_kind,
            )
            last = str(result.get("message_id", ""))
    return SentMessage(message_id=last)
