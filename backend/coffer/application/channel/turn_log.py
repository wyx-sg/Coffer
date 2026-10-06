"""A turn's live text as a log that only ever grows (spec channels/seatalk
"Stream the reply under SeaTalk's streaming contract").

The status block (``turn_status``) is redrawn in place: its clock ticks, its
step lines shift up, narration moves into the ``💬`` line. That suits a surface
that swaps its text silently (a Telegram edit or draft). It does not suit
SeaTalk's stream: the client types an update out when it only APPENDS to what
is shown, and clears the message and types it all out again from the top when
anything earlier changed. Redrawn in place, a long turn's message vanished and
re-typed itself every ten seconds.

So a transport that declares ``live_text_append_only`` gets this log instead::

    ⏳ Working
    Let me check the deploy logs.

    The failure is in the retry path…

No clock (a ticking one is the redraw) and no step lines (a reader does not
follow them): only what the agent writes, left where it was written, with a
paragraph break wherever a tool call came between. Every snapshot therefore
starts with the previous one. The one exception is length: past ``budget``
UTF-8 bytes the oldest part is cut away — in one large step, down to half the
budget, so the message is re-typed rarely rather than on every update.

Pure: no I/O, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["LOG_HEADER", "TurnLog"]

LOG_HEADER = "⏳ Working"
_CUT_MARK = "…"


@dataclass
class TurnLog:
    """One turn's append-only live text."""

    budget: int
    _body: str = ""
    #: Whether the next text continues the open paragraph.
    _open: bool = False
    #: Where the shown part of ``_body`` starts once the oldest part was cut.
    _offset: int = 0

    def text(self, delta: str) -> None:
        """Agent text: continues the open paragraph, or starts a new one."""
        if self._open:
            self._body += delta
            return
        if not delta.strip():
            return  # never open a paragraph with whitespace alone
        # Trailing whitespace is never shown (a snapshot is stripped), so
        # trimming it before the break changes nothing already on screen.
        body = self._body.rstrip()
        self._body = (f"{body}\n\n" if body else "") + delta.lstrip("\n")
        self._open = True

    def boundary(self) -> None:
        """A tool event: the next text starts a new paragraph."""
        self._open = False

    def render(self) -> str:
        """The snapshot: the header, then the log (its newest part once long)."""
        snapshot = self._shown()
        if len(snapshot.encode()) > self.budget:
            self._cut()
            snapshot = self._shown()
        return snapshot

    def _shown(self) -> str:
        shown = self._body[self._offset :]
        if not shown.strip():
            return LOG_HEADER
        head = f"{LOG_HEADER}\n{_CUT_MARK}" if self._offset else LOG_HEADER
        return f"{head}\n{shown}".rstrip()

    def _cut(self) -> None:
        """Drop the oldest part so the shown log fits in half the budget,
        starting at a line where one is near."""
        data = self._body.encode()
        tail = data[max(len(data) - self.budget // 2, 0) :].decode("utf-8", errors="ignore")
        newline = tail.find("\n")
        if 0 <= newline < len(tail) // 2:
            tail = tail[newline + 1 :]
        self._offset = len(self._body) - len(tail)
