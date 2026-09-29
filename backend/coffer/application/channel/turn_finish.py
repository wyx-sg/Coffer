"""The end of a turn: the reply delivered, and the outcome it ended with.

Split out of ``turn_render`` (at its size budget). One pass turns what the agent
wrote into what the chat receives: ``MEDIA:`` sentinels uploaded, the error /
stop / limit notice appended, the live surface closed with the body (or the body
sent when there is no surface), and the compact summary of a turn that did not
end normally.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from coffer.application.channel.ports import ChannelAdapter
from coffer.application.channel.turn_media import deliver_media
from coffer.application.channel.turn_surface import TurnSurface
from coffer.domain.chat.events import TurnError

__all__ = ["TurnEnd", "TurnOutcome", "deliver_reply", "summary_line"]

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
    normally (see "Summarise only a turn that did not end normally")."""
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
) -> str:
    """Deliver the finished reply; return the body as delivered (mention-free).

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
        # surface still has to be closed.
        await surface.close("")
        return ""
    else:
        body = text or "(the agent returned no text)"
        if end.stop_reason == "max_iterations":
            body += "\n\n⚠️ Stopped at the tool-iteration limit."
    leftover = await surface.close(mention(body))
    if leftover:
        await send(leftover)
    return body
