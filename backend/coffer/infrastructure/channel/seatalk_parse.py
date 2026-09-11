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
    "CARD_BUTTONS_PER_GROUP",
    "CARD_BUTTON_GROUPS_MAX",
    "CARD_DESCRIPTION_MAX_CHARS",
    "CARD_TITLE_MAX_CHARS",
    "collect_forwarded_items",
    "dedup_key",
    "flatten_combined_forwarded",
    "interactive_card",
    "mentions_others",
    "message_to_item",
    "split_to_byte_limit",
    "strip_group_mentions",
]

#: Per-card element ceilings, read from SeaTalk's published card docs
#: (``open.seatalk.io/docs/interactive-msg_build-a-card``, 2026-09-11). The card
#: is refused whole when any of them is exceeded, so the two length caps are
#: enforced by truncation here rather than left to chance: a body long enough to
#: break the card is the one case where the user most needs the card to arrive.
#:
#: The full set, for the elements Coffer emits: ``title`` ≤3 per card, text
#: 1-120 characters; ``description`` ≤5 per card, text 1-1000 characters;
#: ``button`` ≤5 per card (callback and redirect counted together);
#: ``button_group`` ≤3 per card, each holding 1-3 buttons rendered on one line;
#: ``image`` ≤3 per card.
CARD_TITLE_MAX_CHARS = 120
CARD_DESCRIPTION_MAX_CHARS = 1000

#: Buttons per ``button_group`` row, and the rows a card may hold. Grouping is
#: what lifts the practical button ceiling above five: 3 rows x 3 buttons is nine
#: tappable choices, where nine bare ``button`` elements would be refused.
#:
#: Nothing here enforces the row count, because the only honest way to enforce it
#: is to drop choices the caller asked for — worse than a refused card, which the
#: command handler already falls back from to a plain-text list. The invariant
#: lives at the caller instead: ``selection_cards.MAX_CARD_BUTTONS`` (6) paginates
#: every list down to two rows, well under the three allowed. A future caller that
#: hands over more than nine buttons gets a refused card and that fallback — the
#: derived ceiling is written down here so the arithmetic is checkable.
CARD_BUTTONS_PER_GROUP = 3
CARD_BUTTON_GROUPS_MAX = 3


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


def _clamp(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` characters, the last one spent on an ellipsis
    so a truncated field reads as truncated rather than as a sentence that
    simply stops."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


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

    **The element ceilings are documented, not guessed** (read 2026-09-11 from
    ``open.seatalk.io/docs/interactive-msg_build-a-card``): ≤3 ``title`` of
    1-120 characters, ≤5 ``description`` of 1-1000 characters, ≤5 bare
    ``button``, ≤3 ``button_group`` of 1-3 buttons each, ≤3 ``image``. Exceeding
    any of them costs the whole card, so this helper truncates the two text
    fields and emits buttons as ``button_group`` rows instead of bare buttons —
    the rows are what make more than five choices legal at all, and they render
    on one line each, which reads better than a column of full-width buttons.
    Buttons inside a row are BARE button objects, not ``element_type`` pairs.

    No ``default``/language-code wrapper: multi-language card content is a Send
    Service Notice API feature, and a bot card sent in that shape is refused.

    A ``title`` renders as SeaTalk's own title element above the body, which is
    what makes a card scannable at a glance in a busy chat — without it the
    subject has to be crammed into the first line of the description, competing
    with the content. Omitted when empty rather than sent blank.

    ``format: 1`` selects SeaTalk's markdown for the description body."""
    elements: list[dict[str, Any]] = []
    if title:
        elements.append(
            {"element_type": "title", "title": {"text": _clamp(title, CARD_TITLE_MAX_CHARS)}}
        )
    elements.append(
        {
            "element_type": "description",
            "description": {"format": 1, "text": _clamp(text, CARD_DESCRIPTION_MAX_CHARS)},
        }
    )
    elements.extend(
        {
            "element_type": "button_group",
            "button_group": [
                {"button_type": "callback", "text": b.label, "value": b.value} for b in row
            ],
        }
        for row in (
            buttons[start : start + CARD_BUTTONS_PER_GROUP]
            for start in range(0, len(buttons), CARD_BUTTONS_PER_GROUP)
        )
    )
    return {"tag": "interactive_message", "interactive_message": {"elements": elements}}


def dedup_key(envelope: dict[str, Any], event: dict[str, Any]) -> str:
    """The event's unique id for FR-039 de-dup: the top-level ``event_id``, else
    the message id (on ``message`` for messages, top-level for a card click)."""
    event_id = str(envelope.get("event_id") or "")
    if event_id:
        return event_id
    message = event.get("message")
    if isinstance(message, dict):
        message_id = str(message.get("message_id") or "")
        if message_id:
            return message_id
    return str(event.get("message_id") or "")
