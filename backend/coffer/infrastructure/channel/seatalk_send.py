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

__all__ = [
    "SEATALK_MENTION_EMAIL_TEMPLATE",
    "SEATALK_MENTION_TEMPLATE",
    "card_blocks",
    "numbered",
    "rendered_pieces",
    "send_text_pieces",
]

#: "Mention the asker in a group answer": how SeaTalk spells an @mention inside message content,
#: read from the "Send Message to Group Chat" formatted-text sample: ``"Kindly note there's **no
#: meeting** today <mention-tag target=\"seatalk://user?id=0\"/>."`` The tag is self-closing and
#: carries no visible text of its own — the client renders the mentioned person's name — so Coffer
#: needs only an id to build one, never a display name.
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
#: every snapshot that carries it goes out as ``format: 1`` (see
#: ``turn_text.with_mention`` and ``SeaTalkLiveText``).
SEATALK_MENTION_TEMPLATE = '<mention-tag target="seatalk://user?id={user_id}"/>'

#: The SECOND documented mention form, from the same "Send a Message with
#: Formats" page, which lists three targets — by email, by SeaTalk id, and
#: ``id=0`` for every member of the group (that last one only notifies when the
#: group's "Notify all members with @All" setting is on, so Coffer never sends it).
#:
#: A FALLBACK, never the default: ``seatalk_id`` is always present on the inbound
#: group-@mention event, while the docs warn ``email`` and ``employee_code`` come
#: back EMPTY for a sender outside the bot's organisation — exactly the case the
#: id survives. ``{user_id}`` stands in for the address so both templates
#: substitute identically.
#:
#: An address carries characters SeaTalk's markdown escaper would otherwise
#: mangle (``first_last@example.com`` is ordinary, and ``_`` is one of the four
#: markers it escapes), which is why ``render.py`` lifts mention tags out of that
#: pass rather than trusting a tag to be marker-free.
SEATALK_MENTION_EMAIL_TEMPLATE = '<mention-tag target="seatalk://user?email={user_id}"/>'

#: ``(chat_id, message, thread_id, chat_kind) -> platform result`` — the
#: adapter's own group/single-chat router.
Send = Callable[[str, dict[str, Any], str, str], Awaitable[Any]]


def rendered_pieces(markdown: str, char_limit: int, byte_limit: int) -> list[str]:
    """``markdown`` as the SeaTalk messages it will take: chunked on paragraph
    (never inside a fence), rendered, then byte-split — render before the byte
    split so escaping cannot push a piece past the platform's byte cap."""
    return [
        piece
        for chunk in chunk_text(markdown, char_limit)
        for piece in split_to_byte_limit(markdown_to_seatalk(chunk), byte_limit)
    ]


#: A card's description blocks: one is 1000 characters at most, a card holds five.
_CARD_BLOCK_CHARS = 1000
_CARD_BLOCKS = 4


def card_blocks(markdown: str) -> list[list[str]]:
    """``markdown`` rendered and cut into the description blocks of one or more
    cards — each block within SeaTalk's 1000 characters, at most ``_CARD_BLOCKS``
    to a card, a reply that does not fit one card running on into the next.

    Cut on paragraph and never inside a fence (``chunk_text``) BEFORE rendering,
    with room left for the escaping rendering adds; a block that still renders
    past the cap is cut by length, which beats a refused card."""
    blocks: list[str] = []
    for chunk in chunk_text(markdown, _CARD_BLOCK_CHARS - 200):
        rendered = markdown_to_seatalk(chunk)
        blocks.extend(
            rendered[i : i + _CARD_BLOCK_CHARS] for i in range(0, len(rendered), _CARD_BLOCK_CHARS)
        )
    blocks = blocks or [""]
    return [blocks[i : i + _CARD_BLOCKS] for i in range(0, len(blocks), _CARD_BLOCKS)]


def numbered(piece: str, index: int, total: int) -> str:
    """Head every piece after the first of a reply cut into several with
    ``(2/3)`` (spec channels "Shape a reply for what the chat can show")."""
    return f"({index + 1}/{total})\n{piece}" if index > 0 and total > 1 else piece


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
        # A card is the one SeaTalk message the bot can rewrite afterwards, so a reply
        # that must stay withdrawable goes out as cards. A selection prompt is short
        # and is one card; a long reply runs on into further cards, the buttons on the
        # last. (A card description renders SeaTalk markdown but NOT tables.)
        cards = card_blocks(markdown)
        ids: list[str] = []
        for i, blocks in enumerate(cards):
            head = numbered(blocks[0], i, len(cards))
            result = await send(
                chat_id,
                interactive_card(
                    head,
                    buttons if i == len(cards) - 1 else (),
                    title=title if i == 0 else "",
                    more=blocks[1:],
                ),
                thread_id,
                chat_kind,
            )
            ids.append(str(result.get("message_id", "")))
        return SentMessage(ids[-1], tuple(ids))
    last = ""
    sent_ids: list[str] = []
    pieces = rendered_pieces(markdown, char_limit, byte_limit)
    for i, piece in enumerate(pieces):
        result = await send(
            chat_id,
            {"tag": "text", "text": {"format": 1, "content": numbered(piece, i, len(pieces))}},
            thread_id,
            chat_kind,
        )
        last = str(result.get("message_id", ""))
        sent_ids.append(last)
    return SentMessage(message_id=last, message_ids=tuple(sent_ids))
