"""Render what one channel turn carries into the text the agent reads, with every
part in its own marked block and every file numbered.

A turn is one or more inbound messages (a burst, spec channels "Take a burst of
messages as one turn"). Each :class:`MessageContent` holds the person's own words
and files and the blocks of other people's messages that came with it — the
thread's slice, the quoted message, a forwarded record. :func:`render_turn` lays
them out in one order:

``[Message origin]`` → per message: thread → quote → forwarded record → the
person's own message (``[User message i/N]`` when N > 1)

and numbers every file across the whole turn in that order, so a line of a
forwarded record reads ``[image] → attachment #1`` and the agent adapter's
``[Attachments]`` block lists ``#1 from the forwarded record: …``. Every block
opens with a heading and closes with an end line (:mod:`coffer.domain.turn_markers`),
and every untrusted line passes through the forgery guard.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from coffer.domain.channel.envelopes import InboundAttachment
from coffer.domain.channel.rich_content import ForwardedItem, one_line
from coffer.domain.chat.attachment import Attachment, attachment_note
from coffer.domain.turn_markers import (
    FORWARDED,
    FORWARDED_END,
    QUOTED,
    QUOTED_END,
    THREAD,
    THREAD_END,
    THREAD_NEW,
    USER,
    USER_END,
    block,
    neutralise,
    when,
)

__all__ = [
    "BlockKind",
    "ContextBlock",
    "MessageContent",
    "render_turn",
]

BlockKind = Literal["thread", "quote", "forwarded"]

#: How an attachment from each block names where it came from.
_SOURCE: dict[BlockKind, str] = {
    "thread": "a thread message",
    "quote": "the quoted message",
    "forwarded": "the forwarded record",
}

#: Continuation lines of a multi-line forwarded or thread item.
_INDENT = "    "


@dataclass(frozen=True)
class ContextBlock:
    """Other people's messages that came with one inbound message."""

    kind: BlockKind
    items: tuple[ForwardedItem, ...] = ()
    #: The files those messages carry, already downloaded.
    media: tuple[InboundAttachment, ...] = ()
    #: A thread block holding only what was posted since this conversation's
    #: last turn in the thread.
    new_since: bool = False
    #: Coffer's own lines about the block (what a thread read cannot show).
    notes: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.items and not self.media and not self.notes


@dataclass(frozen=True)
class MessageContent:
    """One inbound message's part of a turn, before anything is numbered."""

    #: The person's own words.
    text: str = ""
    #: The person's own files.
    media: tuple[InboundAttachment, ...] = ()
    #: Thread, quote and forwarded record, in that order.
    blocks: tuple[ContextBlock, ...] = ()
    #: The sender id of the person the bot serves, to mark their own lines.
    owner_id: str = ""

    @property
    def own(self) -> bool:
        return bool(self.text or self.media)

    @property
    def empty(self) -> bool:
        return not self.own and all(b.empty for b in self.blocks)


def render_turn(
    origin: str, messages: Sequence[MessageContent]
) -> tuple[str, tuple[Attachment, ...]]:
    """The turn text and its numbered attachments (see the module docstring)."""
    own_total = sum(1 for m in messages if m.own)
    sections = [origin] if origin else []
    attachments: list[Attachment] = []
    own_index = 0
    for message in messages:
        for ctx in message.blocks:
            if ctx.empty:
                continue
            numbered = _number(ctx.media, _SOURCE[ctx.kind], attachments)
            sections.append(_render_block(ctx, numbered, message.owner_id))
        if message.own:
            own_index += 1
            tag = f" {own_index}/{own_total}" if own_total > 1 else ""
            own = _number(message.media, f"the user's message{tag}", attachments)
            lines = [neutralise(message.text)] if message.text else []
            if own:
                lines.append(attachment_note([att for _, att in own]))
            sections.append(block(f"{USER}{tag}", USER_END, lines))
    return "\n\n".join(sections), tuple(attachments)


def _number(
    media: Sequence[InboundAttachment], source: str, into: list[Attachment]
) -> list[tuple[str, Attachment]]:
    """Give each file the turn's next ``#n``; ``(ref, attachment)`` pairs."""
    out: list[tuple[str, Attachment]] = []
    for item in media:
        att = Attachment(
            path=item.path,
            mime=item.mime,
            filename=item.filename,
            number=len(into) + 1,
            source=source,
        )
        into.append(att)
        out.append((item.ref, att))
    return out


def _render_block(ctx: ContextBlock, numbered: list[tuple[str, Attachment]], owner_id: str) -> str:
    by_ref: dict[str, list[int]] = {}
    for ref, att in numbered:
        if ref:
            by_ref.setdefault(ref, []).append(att.number)
    quote = ctx.kind == "quote"
    lines: list[str] = []
    for item in ctx.items:
        lines.extend(_item_lines(item, by_ref, owner_id, quote=quote))
    # Files no line pointed at still belong to this block.
    unlinked = [n for numbers in by_ref.values() for n in numbers]
    unlinked += [att.number for ref, att in numbered if not ref]
    if unlinked:
        noun = "attachment" if len(unlinked) == 1 else "attachments"
        listed = ", ".join(f"#{n}" for n in sorted(unlinked))
        lines.append(f"{'> ' if quote else ''}files these messages carry → {noun} {listed}")
    lines.extend(f"note: {note}" for note in ctx.notes)
    if ctx.kind == "thread":
        return block(THREAD_NEW if ctx.new_since else THREAD, THREAD_END, lines)
    if quote:
        return block(QUOTED, QUOTED_END, lines)
    return block(FORWARDED, FORWARDED_END, lines)


def _item_lines(
    item: ForwardedItem, by_ref: dict[str, list[int]], owner_id: str, *, quote: bool
) -> list[str]:
    """One item as ``sender[ (owner)][ · time]: body`` — continuation lines
    indented (a quote keeps its ``> `` on every line instead), each neutralised."""
    who = one_line(item.sender) or "unknown"
    if owner_id and item.sender_id == owner_id:
        who += " (owner)"
    sent = when(item.sent_at)
    if sent:
        who += f" · {sent}"
    body = item.text
    numbers = by_ref.get(item.media_ref) if item.media_ref else None
    if numbers:
        body = f"{item.media_label or '[file]'} → attachment #{numbers.pop(0)}"
    first, *rest = body.split("\n")
    if quote:
        return [neutralise(f"> {who}: {first}"), *(neutralise(f"> {line}") for line in rest)]
    return [neutralise(f"{who}: {first}"), *(neutralise(f"{_INDENT}{line}") for line in rest)]
