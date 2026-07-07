"""Pure Telegram inbound parsing: group detection, @mention/reply addressing,
and forwarded/quoted-reply context framing.

No I/O — only stdlib and ``rich_content``. The Bot API cannot fetch chat
history, so unlike SeaTalk's thread-fetch path, this only ever interprets
what already arrived on the update itself.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.channel.rich_content import ForwardedItem, flatten_forwarded, quote_prefix

__all__ = ["addressed_and_text", "is_group", "prepend_context"]


def is_group(message: dict[str, Any]) -> bool:
    """A group or supergroup chat — not a private DM or a channel post."""
    chat = message.get("chat") or {}
    return chat.get("type") in ("group", "supergroup")


def _reply_is_from_bot(
    message: dict[str, Any], *, bot_id: int | None, bot_username: str | None
) -> bool:
    reply = message.get("reply_to_message")
    if not isinstance(reply, dict):
        return False
    sender = reply.get("from")
    if not isinstance(sender, dict) or not sender.get("is_bot"):
        return False
    if bot_id is not None and sender.get("id") == bot_id:
        return True
    return bool(bot_username) and str(sender.get("username") or "") == bot_username


def _mention_span(
    message: dict[str, Any], text: str, *, bot_id: int | None, bot_username: str | None
) -> tuple[int, int] | None:
    """The ``(offset, length)`` of the entity naming the bot, if any.

    Offsets are consulted against ``text`` as plain Python code-point indices
    (Telegram's own offsets are UTF-16 code units; this is a known, accepted
    simplification for non-surrogate-pair text).
    """
    entities = message.get("entities") or []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        offset, length = ent.get("offset"), ent.get("length")
        if not isinstance(offset, int) or not isinstance(length, int):
            continue
        etype = ent.get("type")
        if etype == "text_mention":
            user = ent.get("user")
            if bot_id is not None and isinstance(user, dict) and user.get("id") == bot_id:
                return offset, length
        elif etype == "mention" and bot_username:
            token = text[offset : offset + length]
            if token.casefold() == f"@{bot_username}".casefold():
                return offset, length
    return None


def addressed_and_text(
    message: dict[str, Any],
    text: str,
    *,
    bot_id: int | None,
    bot_username: str | None,
) -> tuple[bool, str]:
    """Whether a group message addresses the bot, and ``text`` with a matched
    ``@mention`` span stripped (a reply-to-bot leaves the text untouched —
    there is no mention token to remove)."""
    if _reply_is_from_bot(message, bot_id=bot_id, bot_username=bot_username):
        return True, text
    span = _mention_span(message, text, bot_id=bot_id, bot_username=bot_username)
    if span is not None:
        return True, _strip_span(text, *span)
    return False, text


def _strip_span(text: str, offset: int, length: int) -> str:
    """Remove ``text[offset:offset+length]``, collapsing the single space
    seam it can leave behind (e.g. ``"hey @bot run"`` → ``"hey run"``, not
    ``"hey  run"``)."""
    before, after = text[:offset], text[offset + length :]
    if before.endswith(" ") and after.startswith(" "):
        after = after[1:]
    return (before + after).strip()


def _forward_sender_name(message: dict[str, Any]) -> str:
    """Best-effort display name for a forwarded message's original sender,
    across both the modern ``forward_origin`` shape and the legacy
    ``forward_from`` / ``forward_sender_name`` fields it replaced."""
    origin = message.get("forward_origin")
    if isinstance(origin, dict):
        otype = origin.get("type")
        if otype == "user":
            user = origin.get("sender_user") or {}
            return str(user.get("first_name") or user.get("username") or "")
        if otype == "hidden_user":
            return str(origin.get("sender_user_name") or "")
        if otype == "chat":
            chat = origin.get("sender_chat") or {}
            return str(chat.get("title") or "")
        if otype == "channel":
            chat = origin.get("chat") or {}
            return str(chat.get("title") or "")
    forward_from = message.get("forward_from")
    if isinstance(forward_from, dict):
        return str(forward_from.get("first_name") or forward_from.get("username") or "")
    return str(message.get("forward_sender_name") or "")


def _is_forwarded(message: dict[str, Any]) -> bool:
    return bool(
        message.get("forward_origin")
        or message.get("forward_from")
        or message.get("forward_sender_name")
    )


def prepend_context(message: dict[str, Any], text: str) -> str:
    """Fold forwarded-record framing and/or a quoted-reply line into ``text``,
    mirroring how SeaTalk's adapter builds the same context for a turn prompt."""
    body = text
    if _is_forwarded(message):
        body = flatten_forwarded([ForwardedItem(sender=_forward_sender_name(message), text=body)])
    reply = message.get("reply_to_message")
    if isinstance(reply, dict):
        reply_text = reply.get("text") or reply.get("caption")
        if reply_text:
            sender = reply.get("from") or {}
            sender_name = str(sender.get("first_name") or sender.get("username") or "")
            body = f"{quote_prefix(sender_name, str(reply_text))}{body}"
    return body.strip()
