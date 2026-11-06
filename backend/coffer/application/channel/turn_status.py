"""Which of a turn's text is the answer.

Spec channels "Send only the answer, once the turn is done". Text the agent
writes BETWEEN tool calls is narration ("Let me check the logs"); the reply
carries only what it wrote after its last tool call (``ReplyText.answer``), and
never a message the agent itself marked as narration.

Pure: no I/O, no platform schema, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["ReplyText", "format_elapsed"]


def format_elapsed(seconds: float) -> str:
    """``0s`` · ``45s`` · ``2m 14s`` · ``1h 02m`` — short enough for a stopped line."""
    total = max(int(seconds), 0)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


@dataclass
class _Message:
    """One message of the agent's: its text, and whether the agent marked it as
    narration (``commentary``). ``closed`` once the agent said it ended."""

    text: str = ""
    commentary: bool = False
    closed: bool = False


def _joined(messages: list[_Message], *, commentary: bool = False) -> str:
    """The messages' text as paragraphs, narration left out unless asked for."""
    parts = [m.text.strip() for m in messages if commentary or not m.commentary]
    return "\n\n".join(p for p in parts if p)


@dataclass
class ReplyText:
    """The reply's text, kept as the segments a tool call separates.

    A segment is every message the agent wrote between two tool events; deltas
    inside one message join as they came, and messages within a segment join as
    paragraphs. The current (last, still open) segment is the answer so far; a
    segment a tool call closed is narration, which the final reply never carries
    (spec channels "Send only the answer, once the turn is done"). A message
    the agent itself marked as narration (``MessageEnd.commentary``) is left out
    of the answer wherever it stands.
    """

    _segments: list[list[_Message]] = field(default_factory=list)
    _open: bool = False

    def add(self, delta: str) -> None:
        if not (self._open and self._segments):
            self._segments.append([])
            self._open = True
        segment = self._segments[-1]
        if not segment or segment[-1].closed:
            segment.append(_Message())
        segment[-1].text += delta

    def end_message(self, *, commentary: bool) -> str:
        """The agent finished a message: close it and, when it was narration,
        return its text ("" otherwise)."""
        if not (self._open and self._segments and self._segments[-1]):
            return ""
        message = self._segments[-1][-1]
        if message.closed:
            return ""
        message.closed = True
        message.commentary = commentary
        return message.text if commentary else ""

    def boundary(self) -> str:
        """A tool event: close the open segment and return its text ("" if none)."""
        closed = (
            _joined(self._segments[-1], commentary=True) if self._open and self._segments else ""
        )
        self._open = False
        return closed

    @property
    def tail(self) -> str:
        """Answer text written since the last tool event — the answer so far."""
        return _joined(self._segments[-1]) if self._open and self._segments else ""

    @property
    def started(self) -> bool:
        return any(_joined(segment, commentary=True) for segment in self._segments)

    def answer(self) -> str:
        """The final reply: the answer text written after the last tool call. A
        turn that wrote nothing after its last tool falls back to the last
        segment that has any, so a reply is never lost to a trailing tool call;
        a turn that wrote nothing but narration replies with its last words."""
        for segment in reversed(self._segments):
            text = _joined(segment)
            if text:
                return text
        for segment in reversed(self._segments):
            text = _joined(segment, commentary=True)
            if text:
                return text
        return ""
