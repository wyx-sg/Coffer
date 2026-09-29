"""The outbound text path: markdown in, delivered Telegram message out.

Split out of ``telegram.py`` (which is at its size cap) so the adapter keeps
the port methods while the wire details — chunking, the inline keyboard riding
the final chunk, the plain-text retry when the platform rejects formatting, and
the reply/thread routing parameters — live here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from coffer.application.channel.reply_shape import split_details
from coffer.domain.channel.envelopes import ChoiceButton, EphemeralTarget, SentMessage
from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel.render import chunk_text, markdown_to_telegram_html
from coffer.infrastructure.channel.telegram_features import Feature
from coffer.infrastructure.channel.telegram_media import inline_keyboard, routing_params
from coffer.infrastructure.channel.telegram_rich import RICH_MESSAGE_LIMIT, send_rich_text

__all__ = ["continuation", "routing_params", "send_text_chunks"]

Call = Callable[..., Awaitable[Any]]

#: What one ordinary ``sendMessage`` may carry, used when a rich send falls back
#: mid-reply and the remainder must be re-cut to the smaller budget.
_PLAIN_LIMIT = 4000
#: Room kept in a details chunk for the tags that wrap it.
_WRAP_ROOM = 80
_DETAILS_OPEN = "<details><summary>Details</summary>"
_DETAILS_CLOSE = "</details>"


def continuation(index: int, total: int) -> str:
    """``(2/3)\n`` heading every piece after the first of a reply cut into
    several (spec channels "Shape a reply for what the chat can show"), so a busy
    group can follow it; "" for the first piece and for a reply in one piece."""
    return f"({index + 1}/{total})\n" if index > 0 and total > 1 else ""


def _rich_markdown(markdown: str) -> str:
    """``## Details`` becomes a collapsed ``<details>`` block — the rich
    format's own disclosure element, which holds lists, tables and code (an
    expandable quotation holds inline text only)."""
    head, details = split_details(markdown)
    if not details:
        return markdown
    return f"{head}\n\n{_DETAILS_OPEN}\n\n{details}\n\n{_DETAILS_CLOSE}"


async def send_text_chunks(
    call: Call,
    chat_id: str,
    markdown: str,
    *,
    limit: int,
    buttons: Sequence[ChoiceButton] | None = None,
    title: str = "",
    thread_id: str = "",
    reply_to_message_id: str = "",
    channel: str = "",
    rich: Feature | None = None,
    ephemeral: EphemeralTarget | None = None,
    ephemeral_feature: Feature | None = None,
) -> SentMessage:
    """Send ``markdown`` as one or more messages; return the last one's handle.

    Where the platform has rich messages the agent's markdown goes out
    as markdown. Otherwise — or the moment the platform refuses — the text is
    rendered to the HTML subset and chunked to the plain limit instead, so the
    reply always arrives even when the formatting cannot.
    """
    if ephemeral is not None and ephemeral_feature is not None and ephemeral_feature.available:
        # "Keep non-answer chatter private in a group": show this to one member of the group only.
        # Never allowed to cost the answer — a platform that refuses falls through to the ordinary
        # send below, which is exactly the noise Coffer already made.
        sent = await _send_ephemeral(
            call,
            chat_id,
            markdown,
            limit=limit,
            buttons=buttons,
            title=title,
            thread_id=thread_id,
            channel=channel,
            ephemeral=ephemeral,
            feature=ephemeral_feature,
        )
        if sent is not None:
            return sent
    if rich is not None and rich.available:
        sent = await _send_rich_chunks(
            call,
            chat_id,
            markdown,
            buttons=buttons,
            title=title,
            thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
            channel=channel,
            rich=rich,
        )
        if sent is not None:
            return sent
    return await _send_plain_chunks(
        call,
        chat_id,
        markdown,
        limit=limit,
        buttons=buttons,
        title=title,
        thread_id=thread_id,
        reply_to_message_id=reply_to_message_id,
    )


async def _send_ephemeral(
    call: Call,
    chat_id: str,
    markdown: str,
    *,
    limit: int,
    buttons: Sequence[ChoiceButton] | None,
    title: str,
    thread_id: str,
    channel: str,
    ephemeral: EphemeralTarget,
    feature: Feature,
) -> SentMessage | None:
    """One message only that member's client shows, or ``None`` to fall back.

    Deliberately a single un-chunked message rendered in the HTML subset: a
    private answer is a command's reply, which is short, and the platform only
    accepts this within a brief window of the interaction that prompted it —
    spending that window on several round trips would lose the race.
    """
    parameters: dict[str, Any] = {"receiver_user_id": int(ephemeral.receiver_id)}
    if ephemeral.callback_id:
        parameters["callback_query_id"] = ephemeral.callback_id
    extra: dict[str, Any] = {}
    if ephemeral.ephemeral_message_id:
        extra["reply_parameters"] = {
            "ephemeral_message_id": int(ephemeral.ephemeral_message_id),
            "allow_sending_without_reply": True,
        }
    if thread_id:
        extra["message_thread_id"] = int(thread_id)
    if buttons:
        extra["reply_markup"] = inline_keyboard(buttons)
    body = f"**{title}**\n{markdown}" if title and buttons else markdown
    try:
        sent = await call(
            "sendMessage",
            chat_id=chat_id,
            text=markdown_to_telegram_html(body[:limit]),
            parse_mode="HTML",
            ephemeral_message_parameters=parameters,
            **extra,
        )
    except ChannelSendFailed as e:
        feature.note_failure(channel, e)
        if e.api_rejected:
            return None
        raise
    return SentMessage(message_id=str((sent or {}).get("message_id", "")))


async def _send_rich_chunks(
    call: Call,
    chat_id: str,
    markdown: str,
    *,
    buttons: Sequence[ChoiceButton] | None,
    title: str,
    thread_id: str,
    reply_to_message_id: str,
    channel: str,
    rich: Feature,
) -> SentMessage | None:
    """Deliver as rich messages, or ``None`` when nothing was sent and the
    caller must take the plain path.

    A refusal on the FIRST piece means the platform cannot do this at all —
    nothing has been delivered, so the caller starts over on the plain path. A
    refusal on a LATER piece is different: part of the reply is already in the
    chat, so the remainder is finished here on the plain path rather than being
    sent twice.
    """
    pieces = list(chunk_text(_rich_markdown(markdown), RICH_MESSAGE_LIMIT))
    last: SentMessage | None = None
    for i, piece in enumerate(pieces):
        sent = await send_rich_text(
            call,
            chat_id,
            continuation(i, len(pieces)) + piece,
            channel=channel,
            feature=rich,
            buttons=buttons if i == len(pieces) - 1 else None,
            title=title if i == 0 else "",
            thread_id=thread_id,
            reply_to_message_id=reply_to_message_id if i == 0 else "",
            silent=i > 0,
        )
        if sent is None:
            if last is None:
                return None
            rest = "\n\n".join(pieces[i:])
            rest = rest.replace(_DETAILS_OPEN, "## Details").replace(_DETAILS_CLOSE, "")
            return await _send_plain_chunks(
                call,
                chat_id,
                rest,
                limit=_PLAIN_LIMIT,
                buttons=buttons,
                title="",
                thread_id=thread_id,
                reply_to_message_id="",
                silent=True,
            )
        last = sent
    return last if last is not None else SentMessage(message_id="")


async def _send_plain_chunks(
    call: Call,
    chat_id: str,
    markdown: str,
    *,
    limit: int,
    buttons: Sequence[ChoiceButton] | None,
    title: str,
    thread_id: str,
    reply_to_message_id: str,
    silent: bool = False,
) -> SentMessage:
    """The pre-rich path: markdown rendered to Telegram's HTML subset.

    Only the first chunk notifies; the rest go silently (``silent`` makes the
    first one silent too, for a remainder whose head was already delivered).

    Telegram has no card title element here — an inline keyboard hangs off an
    ordinary message — so ``title`` becomes the body's first line in bold
    rather than being dropped: the same information in the platform's shape.
    """
    if title and buttons:
        markdown = f"**{title}**\n{markdown}"
    # ``## Details`` goes out as expandable quotations — the HTML subset's
    # collapsed block — each chunk of it its own.
    head, details = split_details(markdown)
    chunks = [(c, False) for c in chunk_text(head, limit)]
    chunks += [(c, True) for c in chunk_text(details, limit - _WRAP_ROOM)]
    last: SentMessage | None = None
    for i, (chunk, collapsed) in enumerate(chunks):
        # The inline keyboard rides on the final chunk so it sits under the
        # whole (possibly chunked) message. The reply pointer rides on the
        # FIRST: that is the one answering the user's message.
        keyboard = buttons if (buttons and i == len(chunks) - 1) else None
        last = await _send_chunk(
            call,
            chat_id,
            chunk,
            keyboard,
            thread_id=thread_id,
            reply_to_message_id=reply_to_message_id if i == 0 else "",
            silent=silent or i > 0,
            prefix=continuation(i, len(chunks)),
            collapsed=collapsed,
        )
    return last if last is not None else SentMessage(message_id="")


async def _send_chunk(
    call: Call,
    chat_id: str,
    chunk: str,
    buttons: Sequence[ChoiceButton] | None,
    *,
    thread_id: str,
    reply_to_message_id: str,
    silent: bool = False,
    prefix: str = "",
    collapsed: bool = False,
) -> SentMessage:
    markup = inline_keyboard(buttons) if buttons else None
    html = markdown_to_telegram_html(chunk)
    if collapsed:
        html = f"<b>Details</b>\n<blockquote expandable>{html}</blockquote>"
    extra = routing_params(thread_id, reply_to_message_id)
    if markup is not None:
        extra["reply_markup"] = markup
    if silent:
        extra["disable_notification"] = True
    try:
        sent = await call(
            "sendMessage",
            chat_id=chat_id,
            text=prefix + html,
            parse_mode="HTML",
            **extra,
        )
    except ChannelSendFailed as e:
        # Retry as plain text only when the platform rejected formatting (400 =
        # bad entities). A transport error may mean the send got through
        # already — retrying would duplicate; a 429 needs backoff, not an
        # instant resend.
        if not (e.api_rejected and e.status == 400):
            raise
        sent = await call("sendMessage", chat_id=chat_id, text=prefix + chunk, **extra)
    return SentMessage(message_id=str(sent.get("message_id", "")))
