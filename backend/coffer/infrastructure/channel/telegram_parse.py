"""Pure Telegram inbound parsing: group detection, @mention/reply addressing,
and forwarded/quoted-reply context framing.

No I/O — only stdlib and ``rich_content``. The Bot API cannot fetch chat
history, so unlike SeaTalk's thread-fetch path, this only ever interprets
what already arrived on the update itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from coffer.domain.channel.envelopes import InboundAttachment, InboundMessage
from coffer.domain.channel.rich_content import ForwardedItem, flatten_forwarded, quote_prefix

__all__ = ["addressed_and_text", "build_inbound_message", "is_group", "prepend_context"]


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


def _mentions_other(
    message: dict[str, Any], text: str, *, bot_id: int | None, bot_username: str | None
) -> bool:
    """Whether any @mention/text_mention entity names a user OTHER than the bot
    (FR-035): a ``mention`` entity whose token isn't ``@<bot_username>``, or a
    ``text_mention`` whose ``user.id`` isn't ``bot_id``."""
    entities = message.get("entities") or []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        etype = ent.get("type")
        if etype == "text_mention":
            user = ent.get("user")
            if not (isinstance(user, dict) and bot_id is not None and user.get("id") == bot_id):
                return True
        elif etype == "mention":
            offset, length = ent.get("offset"), ent.get("length")
            if not isinstance(offset, int) or not isinstance(length, int):
                continue
            token = text[offset : offset + length]
            if not (bot_username and token.casefold() == f"@{bot_username}".casefold()):
                return True
    return False


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


def build_inbound_message(
    message: dict[str, Any],
    attachments: tuple[InboundAttachment, ...],
    *,
    channel: str,
    bot_id: int | None,
    bot_username: str | None,
) -> InboundMessage:
    """Normalize a Telegram message dict into an ``InboundMessage``.

    ``attachments`` are passed in already-downloaded (the caller owns the
    network) so this stays pure — it lets an album flush reuse the exact same
    text/addressing/routing derivation as a single message (FR-038)."""
    group = is_group(message)
    # A media message carries its text in ``caption``, not ``text``.
    raw_text = str(message.get("text") or message.get("caption") or "")
    addressed, raw = (True, raw_text)
    mentions_other = False
    if group:
        addressed, raw = addressed_and_text(
            message, raw_text, bot_id=bot_id, bot_username=bot_username
        )
        mentions_other = _mentions_other(
            message, raw_text, bot_id=bot_id, bot_username=bot_username
        )
    text = prepend_context(message, raw)
    sender = message.get("from") or {}
    return InboundMessage(
        channel=channel,
        chat_id=str(message.get("chat", {}).get("id", "")),
        sender_display=str(sender.get("first_name") or sender.get("username") or ""),
        text=text,
        platform_message_id=str(message.get("message_id", "")),
        timestamp=datetime.fromtimestamp(int(message.get("date", 0)), tz=UTC),
        sender_id=str(sender.get("id") or ""),
        chat_kind="group" if group else "direct",
        addressed=addressed,
        mentions_others=mentions_other,
        thread_id=str(message.get("message_thread_id") or ""),
        attachments=attachments,
    )
