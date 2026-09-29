"""The end of a turn: the reply delivered, and the outcome it ended with.

Split out of ``turn_render`` (at its size budget). One pass turns what the agent
wrote into what the chat receives: ``MEDIA:`` sentinels uploaded, the error /
stop / limit notice appended, the live surface closed with the body (or the body
sent when there is no surface), and the compact summary of a turn that did not
end normally.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from coffer.application.channel.details_card import details_buttons, save_details
from coffer.application.channel.needs_you import Question, extract_question, question_buttons
from coffer.application.channel.ports import ChannelAdapter
from coffer.application.channel.reply_shape import ReplyFile, shape_reply, split_details
from coffer.application.channel.turn_media import deliver_media, send_reply_files
from coffer.application.channel.turn_status import format_elapsed
from coffer.application.channel.turn_surface import TurnSurface
from coffer.domain.channel.envelopes import ChoiceButton
from coffer.domain.chat.events import TurnError

__all__ = [
    "Delivered",
    "SendCard",
    "TurnEnd",
    "TurnOutcome",
    "deliver_reply",
    "first_line",
    "ping_line",
    "summary_line",
]

#: How much of the answer's first line a completion ping quotes.
_PING_LINE_MAX_CHARS = 120
#: Markup a first line is read through: a mention tag Coffer put there, a
#: heading/list/quote marker, and the emphasis and code characters around words.
_MENTION_MARKUP = re.compile(r"<mention-tag[^>]*/>|\[([^\]]*)\]\(tg://user\?id=\d+\)")
_LINE_MARKER = re.compile(r"^\s*(?:#{1,6}\s+|[-*+]\s+|>\s*|\d+[.)]\s+)")
_EMPHASIS = re.compile(r"[*_`~]+")

#: How a turn ended, in the words the reactions and the ping use. ``waiting``
#: is a clean end on a question for the owner (see "Turn a question for the
#: owner into buttons").
TurnOutcome = Literal["done", "failed", "stopped", "waiting"]


class SendCard(Protocol):
    """Sends one message with buttons (a card, where the transport has them)
    into the turn's chat and thread."""

    async def __call__(
        self, text: str, buttons: Sequence[ChoiceButton], *, title: str = ""
    ) -> None: ...


@dataclass(frozen=True)
class Delivered:
    """What the finished reply turned out to be."""

    #: The body as delivered, mention-free ("" for a files-only reply).
    body: str = ""
    #: Its head went out by finishing the live surface in place.
    in_place: bool = False
    #: The question the agent ended on, if any.
    question: Question | None = None
    #: That question went out as its own message with buttons — a new message,
    #: which notifies by itself.
    question_sent: bool = False


@dataclass(frozen=True)
class TurnEnd:
    """How a turn ended, as the events said."""

    stop_reason: str
    error: TurnError | None
    tool_count: int
    duration: float
    tokens: int | None

    @property
    def clean(self) -> bool:
        return self.error is None and self.stop_reason == "end_turn"

    @property
    def outcome(self) -> TurnOutcome:
        if self.error is not None or self.stop_reason == "max_iterations":
            return "failed"
        if self.stop_reason == "interrupted":
            return "stopped"
        return "done"


def summary_line(end: TurnEnd) -> str:
    """``⚠️ failed · 7 tools · 42.1s · 18000 tok`` — for a turn that did not end
    normally (see "Summarise a turn that did not end normally")."""
    facts = [
        f"{end.tool_count} tool" + ("" if end.tool_count == 1 else "s"),
        f"{end.duration:.1f}s",
    ]
    if end.tokens is not None:
        facts.append(f"{end.tokens} tok")
    detail = " · ".join(facts)
    if end.error is not None:
        return f"⚠️ failed · {detail}"
    if end.stop_reason == "interrupted":
        return f"⏹ stopped · {detail}"
    if end.stop_reason == "max_iterations":
        return f"⚠️ tool-limit · {detail}"
    return f"✅ done · {detail}"


def first_line(body: str) -> str:
    """The answer's first line as plain words, for a ping or a card title."""
    for raw in body.splitlines():
        line = _MENTION_MARKUP.sub("", raw)
        line = _EMPHASIS.sub("", _LINE_MARKER.sub("", line)).strip()
        if line and not line.startswith("```"):
            if len(line) > _PING_LINE_MAX_CHARS:
                line = line[: _PING_LINE_MAX_CHARS - 1].rstrip() + "…"
            return line
    return ""


def ping_line(end: TurnEnd, body: str, question: Question | None = None) -> str:
    """The one line a long turn ends with where its answer does not notify (see
    "Ping the asker when a long turn ends"): ``✅ Done · 4m 12s — <first line>``.

    A turn that did not end normally carries the summary's facts — tool count
    and tokens — because the ping stands in for the summary there."""
    elapsed = format_elapsed(end.duration)
    if question is not None and end.clean:
        return f"❓ Needs you · {elapsed} — {question.text}"
    if end.outcome == "done":
        line = first_line(body)
        return f"✅ Done · {elapsed} — {line}" if line else f"✅ Done · {elapsed}"
    facts = [elapsed, f"{end.tool_count} tool" + ("" if end.tool_count == 1 else "s")]
    if end.tokens is not None:
        facts.append(f"{end.tokens} tok")
    detail = " · ".join(facts)
    if end.error is not None:
        return f"⚠️ Failed · {detail} — {end.error.message}"
    if end.stop_reason == "max_iterations":
        return f"⚠️ Tool limit · {detail}"
    return f"⏹ Stopped · {detail}"


async def deliver_reply(
    *,
    adapter: ChannelAdapter,
    chat_id: str,
    thread_id: str,
    chat_kind: str,
    surface: TurnSurface,
    send: Callable[[str], Awaitable[None]],
    mention: Callable[[str], str],
    text: str,
    end: TurnEnd,
    send_card: SendCard | None = None,
) -> Delivered:
    """Deliver the finished reply and say what it turned out to be.

    A clean reply ending on a ``NEEDS YOU:`` line loses the line; its question
    follows the answer as its own message with one button per option, or stays
    in the reply as ``❓ …`` where there are no buttons.

    The @mention is added HERE, to the body, exactly once: whichever of the
    surface or the ordinary send delivers the head carries it, and the overflow
    a stream hands back does not repeat it.
    """
    media_sent = 0
    files: tuple[ReplyFile, ...] = ()
    if text:
        text, media_sent = await deliver_media(
            adapter, chat_id, text, thread_id=thread_id, chat_kind=chat_kind
        )
        # What this chat cannot show becomes bullets and files (see "Shape a
        # reply for what the chat can show").
        caps = adapter.capabilities
        shaped = shape_reply(
            text,
            renders_tables=caps.renders_tables,
            max_inline_code_lines=caps.max_inline_code_lines,
            attach=caps.supports_media,
        )
        text, files = shaped.body, shaped.files
    question: Question | None = None
    if end.clean:
        text, question = extract_question(text)
    buttons = (
        question_buttons(question)
        if question is not None and send_card is not None and adapter.capabilities.supports_buttons
        else []
    )
    if question is not None and not buttons:
        # No buttons to tap: the question stays in the reply, marked.
        text = f"{text}\n\n❓ {question.text}".strip()
        if question.options:
            text += " (" + " / ".join(question.options) + ")"
    details = ""
    caps = adapter.capabilities
    if end.clean and send_card is not None and caps.supports_buttons and not caps.collapses_details:
        # A transport that cannot collapse a details section but has cards moves
        # it behind a summary card (see "Offer a reply's details behind a
        # summary card").
        head, details = split_details(text)
        if details and head:
            text = head
        else:
            details = ""
    if end.error is not None:
        # What the agent streamed before failing is still the user's — a stalled
        # or dropped turn often has most of an answer in it.
        notice = f"⚠️ {end.error.message} [{end.error.code}]"
        body = f"{text}\n\n{notice}" if text else notice
    elif end.stop_reason == "interrupted":
        body = f"{text}\n\n⏹ Stopped." if text else "⏹ Stopped."
    elif not text and media_sent:
        # The uploaded file(s) are the reply — no placeholder text, but the live
        # surface still has to be closed. One that persists as a message must
        # not be left showing the working status, so it says what it did.
        done = f"📎 Sent {media_sent} file" + ("" if media_sent == 1 else "s") + "."
        await surface.close(done if surface.persisted else "")
        return Delivered()
    else:
        body = text or "(the agent returned no text)"
        if end.stop_reason == "max_iterations":
            body += "\n\n⚠️ Stopped at the tool-iteration limit."
    was_open = surface.is_open
    mentioned = mention(body)
    leftover = await surface.close(mentioned)
    if leftover:
        await send(leftover)
    await send_reply_files(adapter, chat_id, files, thread_id=thread_id, chat_kind=chat_kind)
    if details and send_card is not None:
        await _send_details_card(send_card, send, text, details)
    sent = False
    if question is not None and buttons and send_card is not None:
        try:
            await send_card(f"❓ {question.text}", buttons)
            sent = True
        except Exception:
            await send(f"❓ {question.text}")
    return Delivered(body, was_open and leftover != mentioned, question, sent)


async def _send_details_card(
    send_card: SendCard, send: Callable[[str], Awaitable[None]], head: str, details: str
) -> None:
    """The outcome as the card's title, how long the details are, and the two
    buttons that fetch them. A card the platform refuses leaves the details
    as an ordinary message instead — they are never lost."""
    lines = len([line for line in details.splitlines() if line.strip()])
    try:
        details_id = save_details(f"## Details\n\n{details}")
        await send_card(
            f"{lines} more line" + ("" if lines == 1 else "s") + " of details.",
            details_buttons(details_id),
            title=first_line(head) or "Details",
        )
    except Exception:
        await send(f"**Details**\n\n{details}")
