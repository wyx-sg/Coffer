"""Grounding an inbound turn in what surrounds it: its thread and the message it quotes.

Both reads go through the adapter's ``ContextFetchPort`` and only on a transport
that declares ``supports_history_fetch`` — a platform that inlines a quote on the
update itself (Telegram's ``reply_to_message``) has already folded it into the
message text, and one with no history API has no thread to read.
"""

from __future__ import annotations

from typing import cast

from coffer.application.channel.ports import ChannelBinding, ContextFetchPort
from coffer.domain.channel.envelopes import InboundAttachment, InboundMessage
from coffer.domain.channel.rich_content import flatten_context, quote_prefix
from coffer.domain.chat.attachment import Attachment


async def fold_turn_context(
    binding: ChannelBinding,
    msg: InboundMessage,
    text: str,
    attachments: tuple[Attachment, ...],
) -> tuple[str, tuple[Attachment, ...]]:
    """Return ``text`` and ``attachments`` with the thread and the quote folded in.

    The turn reads, top to bottom: the thread's messages, the quoted message as
    ``> sender: …`` lines, then the message itself — so "repeat this" or "as
    above" points at something the agent can actually see. Every image/file those
    messages carry is appended to ``attachments`` (see "Download the media a
    thread's messages carry"), so a picture reaches a vision agent, not a dead
    auth-gated link. Either read degrading to nothing leaves the turn as it was.
    """
    if not binding.adapter.capabilities.supports_history_fetch:
        return text, attachments
    fetcher = cast(ContextFetchPort, binding.adapter)
    fetched: list[InboundAttachment] = []
    if msg.quoted_message_id:
        # The quote is the reference the message leans on, so it sits right above it.
        items, quoted_atts = await fetcher.fetch_quoted(msg.quoted_message_id)
        quote = "".join(quote_prefix(it.sender, it.text) for it in items)
        text = f"{quote}{text}".rstrip("\n") if quote else text
        fetched.extend(quoted_atts)
    if msg.thread_id and msg.thread_id != msg.platform_message_id:
        # Ground the turn in the thread's own conversation — in a DM just as much as
        # in a group: a thread is a thread, and SeaTalk exposes a DM thread endpoint
        # too (app v3.62.1+), so ``chat_kind`` only picks which one the adapter
        # calls. What stays group-only is what is NOT fetched: reading all
        # group-MAIN chatter is undesirable and that permission is not granted
        # anyway, so only the thread a message actually landed in is ever read. A
        # message that roots a fresh thread at itself (thread_id == this message's
        # id) holds nothing else yet — skip the fetch rather than echo it back into
        # its own context.
        items, thread_atts = await fetcher.fetch_thread(
            msg.chat_id, msg.thread_id, chat_kind=msg.chat_kind
        )
        ctx = flatten_context(items, title="Thread messages")
        if ctx:
            text = f"{ctx}\n\n{text}" if text else ctx
        fetched[:0] = thread_atts
    return text, attachments + tuple(
        Attachment(path=a.path, mime=a.mime, filename=a.filename) for a in fetched
    )
