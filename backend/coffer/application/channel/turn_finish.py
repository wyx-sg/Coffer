"""The end of a turn: the reply delivered, and the outcome it ended with.

Split out of ``turn_render`` (at its size budget). One pass turns what the agent
wrote into what the chat receives: ``MEDIA:`` sentinels uploaded, the error /
stop / limit notice appended, the live surface closed with the body (or the body
sent when there is no surface), and the compact summary of a turn that did not
end normally.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from coffer.application.channel.ports import ChannelAdapter
from coffer.application.channel.turn_media import deliver_media
from coffer.application.channel.turn_status import format_elapsed
from coffer.application.channel.turn_surface import TurnSurface
from coffer.domain.chat.events import TurnError

__all__ = [
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

#: How a turn ended, in the words the reactions and the ping use.
TurnOutcome = Literal["done", "failed", "stopped"]


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


def ping_line(end: TurnEnd, body: str) -> str:
    """The one line a long turn ends with where its answer does not notify (see
    "Ping the asker when a long turn ends"): ``✅ Done · 4m 12s — <first line>``.

    A turn that did not end normally carries the summary's facts — tool count
    and tokens — because the ping stands in for the summary there."""
    elapsed = format_elapsed(end.duration)
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
) -> tuple[str, bool]:
    """Deliver the finished reply; return the body as delivered (mention-free)
    and whether its head went out by closing the live surface in place.

    The @mention is added HERE, to the body, exactly once: whichever of the
    surface or the ordinary send delivers the head carries it, and the overflow
    a stream hands back does not repeat it.
    """
    media_sent = 0
    if text:
        text, media_sent = await deliver_media(
            adapter, chat_id, text, thread_id=thread_id, chat_kind=chat_kind
        )
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
        return "", False
    else:
        body = text or "(the agent returned no text)"
        if end.stop_reason == "max_iterations":
            body += "\n\n⚠️ Stopped at the tool-iteration limit."
    was_open = surface.is_open
    mentioned = mention(body)
    leftover = await surface.close(mentioned)
    if leftover:
        await send(leftover)
    return body, was_open and leftover != mentioned
