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

__all__ = ["SEATALK_MENTION_TEMPLATE", "send_text_pieces"]

#: FR-070: how SeaTalk spells an @mention inside message content, read from the
#: "Send Message to Group Chat" formatted-text sample:
#: ``"Kindly note there's **no meeting** today <mention-tag
#: target=\"seatalk://user?id=0\"/>."`` The tag is self-closing and carries no
#: visible text of its own — the client renders the mentioned person's name — so
#: Coffer needs only an id to build one, never a display name.
#:
#: WHICH id: the ``seatalk_id``, NOT the ``employee_code``. This is an
#: INFERENCE, and the evidence is worth naming because nothing states it
#: outright: "Event: New Mentioned Message From Group Chat" maps each entry of
#: ``mentioned_list`` as ``{username, seatalk_id}``, and documents "Mention all"
#: as ``seatalk_id: "0"`` — the very ``0`` the send sample above targets. The
#: inbound id space and the outbound one therefore line up. It also happens to
#: be the only id that survives the cross-organisation case: the same event doc
#: warns that a sender's ``employee_code`` and ``email`` arrive EMPTY when they
#: are not in the bot's organisation, while ``seatalk_id`` is always present.
#:
#: It is MARKDOWN — it reaches the reader as a name only in a ``format: 1``
#: message. In a ``format: 2`` (plain) one it shows as this literal string, so
#: only sends that render rich may carry it (see ``TurnRenderer._with_mention``).
SEATALK_MENTION_TEMPLATE = '<mention-tag target="seatalk://user?id={user_id}"/>'

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
