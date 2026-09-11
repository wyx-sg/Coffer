"""Pure SeaTalk inbound/outbound parsing and formatting helpers.

No I/O — only stdlib and ``coffer.domain.channel``. Split out of
``seatalk.py`` (mirroring ``telegram_parse.py``) so the adapter module holds
only the transport/lifecycle/I-O surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from coffer.domain.channel.envelopes import ChoiceButton
from coffer.domain.channel.rich_content import ForwardedItem, flatten_forwarded

__all__ = [
    "collect_forwarded_items",
    "flatten_combined_forwarded",
    "interactive_card",
    "mentions_others",
    "message_to_item",
    "split_to_byte_limit",
    "strip_group_mentions",
]


def mentions_others(mentioned_list: Sequence[Any] | None) -> bool:
    """Whether a group message @mentions a user OTHER than the bot (FR-035).

    ``new_mentioned_message_received_from_group_chat`` only fires when the bot
    IS mentioned, so the bot already occupies one slot in ``mentioned_list``;
    more than one distinct username therefore means a non-bot user was also
    @mentioned.
    """
    return (
        len(
            {
                m["username"]
                for m in mentioned_list or []
                if isinstance(m, dict) and m.get("username")
            }
        )
        > 1
    )


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
    into text. A nested ``combined_forwarded_chat_history`` entry collapses
    to the ``[forwarded chat record]`` stand-in here; callers that want the
    nested leaves flattened use :func:`flatten_combined_forwarded`, which
    recurses before falling back to this single-line mapping.
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
        # A short stand-in — recursion into the nested history is handled by
        # ``collect_forwarded_items`` before this fallback is ever reached.
        text = "[forwarded chat record]"
    return ForwardedItem(sender=sender, text=text)


def collect_forwarded_items(content: Sequence[Any]) -> list[ForwardedItem]:
    """Flatten a forwarded-record ``content`` list to leaf items, recursing
    into every nested ``combined_forwarded_chat_history`` entry.

    Forwarding a chat record wraps the real messages one level deeper: the
    top-level ``content`` is a single entry whose ``tag`` is itself
    ``combined_forwarded_chat_history`` and whose own nested content holds
    the leaf text/image/file messages. Recursing yields those leaves with
    their real per-message senders instead of the ``[forwarded chat record]``
    placeholder the whole record would otherwise collapse to.
    """
    items: list[ForwardedItem] = []
    for entry in content:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("tag", "")) == "combined_forwarded_chat_history":
            nested = (entry.get("combined_forwarded_chat_history") or {}).get("content") or []
            items.extend(collect_forwarded_items(nested))
        else:
            items.append(message_to_item(entry))
    return items


def flatten_combined_forwarded(message: dict[str, Any]) -> str:
    """Flatten a top-level ``combined_forwarded_chat_history`` message body
    into the ``[Forwarded chat record]`` text block.

    Shared by both inbound paths that can receive a forwarded record as the
    whole message — the 1:1 DM (``message_from_bot_subscriber``) and the
    group @mention (``new_mentioned_message_received_from_group_chat``)
    events — so a forwarded record dropped into a group is not silently
    lost the way an empty ``plain_text`` would make it. Recurses into the
    nested wrapping SeaTalk adds when a record is forwarded (see
    :func:`collect_forwarded_items`).
    """
    content = (message.get("combined_forwarded_chat_history") or {}).get("content") or []
    return flatten_forwarded(collect_forwarded_items(content))


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


def interactive_card(
    text: str, buttons: Sequence[ChoiceButton], *, title: str = ""
) -> dict[str, Any]:
    """A SeaTalk ``interactive_message`` card: a markdown body + callback buttons
    each carrying our custom ``value``. A tap returns the value in an
    ``interactive_message_click`` event.

    **Buttons are elements, not a sibling of them.** Every entry in ``elements``
    is a ``{element_type, <element_type>: {...}}`` pair, buttons included. This
    helper previously emitted a ``buttons`` array alongside ``elements``, a shape
    inferred while the API docs were login-gated; the platform would have
    rendered no buttons (or refused the card outright), which is why a selection
    card never worked. Verified against SeaTalk's published card format
    2026-09-09.

    A ``title`` renders as SeaTalk's own title element above the body, which is
    what makes a card scannable at a glance in a busy chat — without it the
    subject has to be crammed into the first line of the description, competing
    with the content. Omitted when empty rather than sent blank.

    ``format: 1`` selects SeaTalk's markdown for the description body."""
    elements: list[dict[str, Any]] = []
    if title:
        elements.append({"element_type": "title", "title": {"text": title}})
    elements.append({"element_type": "description", "description": {"format": 1, "text": text}})
    elements.extend(
        {
            "element_type": "button",
            "button": {"button_type": "callback", "text": b.label, "value": b.value},
        }
        for b in buttons
    )
    return {"tag": "interactive_message", "interactive_message": {"elements": elements}}
