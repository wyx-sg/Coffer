"""Pure SeaTalk inbound/outbound parsing and formatting helpers.

No I/O — only stdlib and ``coffer.domain.channel``. Split out of
``seatalk.py`` (mirroring ``telegram_parse.py``) so the adapter module holds
only the transport/lifecycle/I-O surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from coffer.domain.channel.envelopes import ChoiceButton
from coffer.domain.channel.rich_content import ForwardedItem

__all__ = [
    "interactive_card",
    "message_to_item",
    "split_to_byte_limit",
    "strip_group_mentions",
]


def split_to_byte_limit(chunk: str, byte_limit: int) -> list[str]:
    """Split a chunk further until each piece fits the UTF-8 byte cap.

    chunk_text counts characters, but CJK text is 3 bytes per character in
    UTF-8 — a 3500-character chunk can be ~10 KB. Halve at character
    boundaries until every piece encodes under the limit.
    """
    if len(chunk.encode("utf-8")) <= byte_limit:
        return [chunk]
    mid = len(chunk) // 2
    return split_to_byte_limit(chunk[:mid], byte_limit) + split_to_byte_limit(
        chunk[mid:], byte_limit
    )


def message_to_item(msg: dict[str, Any]) -> ForwardedItem:
    """Map one SeaTalk thread message dict to a :class:`ForwardedItem`.

    Used by ``fetch_thread`` and the group-forwarded-record renderer —
    one mapping for every place SeaTalk hands us a message dict to flatten
    into text.
    """
    sender = str((msg.get("sender") or {}).get("email") or "unknown")
    tag = str(msg.get("tag", ""))
    text = f"[{tag}]"
    if tag == "text":
        # Group history/thread messages use "plain_text"; single-chat
        # messages (elsewhere in this adapter) use "content" — support both.
        body = msg.get("text") or {}
        text = str(body.get("plain_text") or body.get("content") or "")
    elif tag == "image":
        text = f"[image] {(msg.get('image') or {}).get('content', '')}"
    elif tag == "file":
        text = f"[file] {(msg.get('file') or {}).get('filename', '')}"
    elif tag == "combined_forwarded_chat_history":
        # A short stand-in — we do not recurse into the nested history here.
        text = "[forwarded chat record]"
    return ForwardedItem(sender=sender, text=text)


def strip_group_mentions(plain_text: str, mentioned_list: Sequence[Any] | None) -> str:
    """Remove every ``@username`` mention token SeaTalk lists for a group
    message, and trim the result.

    ``new_mentioned_message_received_from_group_chat`` only fires when the
    bot is @mentioned, so the mention token(s) are always present in
    ``plain_text`` and always worth stripping before it becomes the turn's
    prompt text.
    """
    text = plain_text
    for mention in mentioned_list or []:
        if isinstance(mention, dict):
            username = str(mention.get("username", ""))
            if username:
                text = text.replace(f"@{username}", "")
    return text.strip()


def interactive_card(text: str, buttons: Sequence[ChoiceButton]) -> dict[str, Any]:
    """A SeaTalk ``interactive_message`` card: a markdown body + callback buttons
    each carrying our custom ``value`` (research.md). A tap returns the value in
    an ``interactive_message_click`` event.

    research.md pins only ``tag="interactive_message"``, ``button_type="callback"``
    and the custom ``value``; the ``elements``/``description`` body nesting and
    the button ``text`` field are inferred (the live API docs are login-gated and
    unreachable from this machine). If SeaTalk rejects the payload, adjust this
    one helper — the rest of the card pipeline is shape-agnostic."""
    return {
        "tag": "interactive_message",
        "interactive_message": {
            "elements": [
                {"element_type": "description", "description": {"format": 1, "text": text}},
            ],
            "buttons": [
                {"button_type": "callback", "text": b.label, "value": b.value} for b in buttons
            ],
        },
    }
