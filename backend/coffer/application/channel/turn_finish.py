"""The end of a turn: the reply delivered, and the outcome it ended with.

Split out of ``turn_render`` (at its size budget). One pass turns what the agent
wrote into what the chat receives: ``MEDIA:`` sentinels uploaded, the error /
stop / limit notice appended, the live surface closed (or none to close) and the
body sent as new messages, and the compact summary of a turn that did not end
normally.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from coffer.application.channel.ports import ChannelAdapter
from coffer.application.channel.reply_shape import ReplyFile, shape_reply
from coffer.application.channel.reply_tracking import ReplyTracker
from coffer.application.channel.turn_media import deliver_media, send_reply_files
from coffer.application.channel.turn_status import format_elapsed
from coffer.application.channel.turn_surface import TurnSurface
from coffer.domain.channel.envelopes import ChoiceButton, SentMessage
from coffer.domain.chat.events import SESSION_IN_USE, TurnError

__all__ = [
    "SendCard",
    "TurnEnd",
    "TurnOutcome",
    "deliver_reply",
    "failure_line",
    "stopped_line",
]

#: How a turn ended, in the words the reactions use.
TurnOutcome = Literal["done", "failed", "stopped"]


class SendCard(Protocol):
    """Sends one message with buttons (a card, where the transport has them)
    into the turn's chat and thread."""

    async def __call__(
        self, text: str, buttons: Sequence[ChoiceButton], *, title: str = ""
    ) -> SentMessage | None:
        """The sent message's handle, which a later rewrite needs; ``None``
        when nothing went out."""
        ...


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
        if self.error is not None:
            return "failed"
        if self.stop_reason == "interrupted":
            return "stopped"
        return "done"


def failure_line(message: str) -> str:
    """``⚠️ <what happened>. Send it again to retry.`` — the reason in plain words,
    never the internal error code."""
    reason = message.strip().rstrip(".") or "Something went wrong"
    return f"⚠️ {reason}. Send it again to retry."


def stopped_line(duration: float, *, title: str = "", tool_count: int = 0, held: int = 0) -> str:
    """``⏹ Stopped “Fix login” after 12s · 3 tools.`` — what was stopped, that it
    did stop, and, when messages were queued behind it, that they wait."""
    what = f" “{title}”" if title else ""
    line = f"⏹ Stopped{what} after {format_elapsed(duration)}"
    if tool_count:
        line += f" · {tool_count} tool" + ("" if tool_count == 1 else "s")
    line += "."
    if held:
        noun = "message is" if held == 1 else "messages are"
        line += f"\n⏸ {held} queued {noun} on hold — send anything to continue."
    return line


async def deliver_reply(
    *,
    tracker: ReplyTracker | None = None,
    **kwargs: Any,
) -> None:
    """Deliver the finished reply (see ``_deliver_reply``) and file what it was
    delivered as, so the owner can withdraw it (spec channels "Withdraw a bot reply
    on the owner's command")."""
    try:
        await _deliver_reply(tracker=tracker, **kwargs)
    finally:
        if tracker is not None:
            await tracker.commit()


async def _deliver_reply(
    *,
    tracker: ReplyTracker | None,
    adapter: ChannelAdapter,
    chat_id: str,
    thread_id: str,
    chat_kind: str,
    surface: TurnSurface,
    send: Callable[[str], Awaitable[None]],
    mention: Callable[[str], str],
    text: str,
    end: TurnEnd,
    stop_noted: bool = False,
    stop_line: str | None = None,
) -> None:
    """Deliver the finished reply.

    ``stop_noted``: the "Stopping…" message was already rewritten into the
    stop result, so the reply does not repeat it. ``stop_line``: that result,
    naming what was stopped, when a ``/stop`` asked for it.

    The @mention is added HERE, to the body, exactly once. A live surface is
    scaffolding: closing it hands the body back, and the body goes out as new
    messages, so the mention is in the message that creates the reply.
    """
    media_sent = 0
    files: tuple[ReplyFile, ...] = ()
    if text:
        text, media_sent = await deliver_media(
            adapter,
            chat_id,
            text,
            thread_id=thread_id,
            chat_kind=chat_kind,
            on_sent=tracker.note_file if tracker is not None else None,
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
    if end.error is not None:
        # What the agent streamed before failing is still the user's — a stalled
        # or dropped turn often has most of an answer in it.
        # A refusal is said as it is: nothing failed and nothing is worth retrying.
        notice = (
            end.error.message
            if end.error.code == SESSION_IN_USE
            else failure_line(end.error.message)
        )
        body = f"{text}\n\n{notice}" if text else notice
    elif end.stop_reason == "interrupted":
        notice = stop_line or stopped_line(end.duration, tool_count=end.tool_count)
        if stop_noted and not text:
            await surface.close("")
            return
        body = text if stop_noted else f"{text}\n\n{notice}" if text else notice
    elif not text and media_sent:
        # The uploaded file(s) are the reply — no placeholder text, but the live
        # surface still has to be closed.
        await surface.close("")
        return
    else:
        body = text or "(the agent returned no text)"
    mentioned = mention(body)
    leftover = await surface.close(mentioned)
    if leftover:
        if tracker is not None:
            await tracker.send(leftover)
        else:
            await send(leftover)
    await send_reply_files(
        adapter,
        chat_id,
        files,
        thread_id=thread_id,
        chat_kind=chat_kind,
        on_sent=tracker.note_file if tracker is not None else None,
    )
