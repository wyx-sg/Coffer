"""What a turn is doing right now, as one status block the reader can glance at.

Spec channels "Show a turn's working state as one status line". A long turn
used to show either nothing or the one sentence the agent wrote before its
first tool — frozen there for minutes. The status block replaces that with the
three facts a person watching a phone wants: THAT it is working, for HOW LONG,
and WHAT it is doing now::

    ⏳ Working · 2m 14s · 7 steps
    💬 Checking the deploy logs
    +4 earlier
    ✅ Read · checkout.spec.ts
    ✅ Bash · rerun the 3DS test
    ⏳ Grep · retry in e2e/

The header ticks on the live surfaces' keep-alive cadence, so a long silent tool
still shows time passing. In a group a step line names only the tool: everyone
there reads it, and a tool's input can carry a command, a query or a path. Text
the agent writes BETWEEN tool calls is narration ("Let me check the logs"): it
becomes the ``💬`` line rather than the answer. The final reply keeps it, with
paragraph breaks (``ReplyText``).

Pure: no I/O, no platform schema, no clock of its own — ``now`` is handed in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from coffer.application.channel.turn_progress import _clip, _describe_tool, _progress_line

__all__ = ["LIVE_SEPARATOR", "ReplyText", "TurnStatus", "format_elapsed", "split_snapshot"]

#: The line between a live snapshot's status block and the answer growing under
#: it. A transport that renders the two differently (Telegram's rich draft puts
#: the header in a thinking block) splits on it; every other one shows it as a
#: plain rule.
LIVE_SEPARATOR = "─"

#: How many step lines a phone shows — the newest; older ones collapse into
#: one "+N earlier" line.
_VISIBLE_STEPS = 3
_NARRATION_MAX_CHARS = 80


def split_snapshot(snapshot: str) -> tuple[str, str]:
    """``(status block, answer)`` of a live snapshot; the answer is "" when the
    snapshot has none. A transport that must shorten a snapshot clips the
    answer and keeps the block, so the header never scrolls away."""
    rule = f"\n{LIVE_SEPARATOR}\n"
    if rule in snapshot:
        block, answer = snapshot.split(rule, 1)
        return block, answer
    return snapshot, ""


def format_elapsed(seconds: float) -> str:
    """``0s`` · ``45s`` · ``2m 14s`` · ``1h 02m`` — short enough for a header."""
    total = max(int(seconds), 0)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


@dataclass
class TurnStatus:
    """The running tally one turn's status block is drawn from."""

    started: float
    #: Per channel ("show steps"): off keeps the header and narration but hides
    #: the step lines — e.g. in a busy group.
    show_steps: bool = True
    #: "group" names only the tool on each step line — everyone in the group
    #: reads it, and a tool's input can carry a command, a query or a path.
    chat_kind: str = "direct"
    _lines: dict[str, str] = field(default_factory=dict)  # tool_use_id -> line
    _desc: dict[str, str] = field(default_factory=dict)  # tool_use_id -> descriptor
    failed: int = 0
    narration: str = ""

    @property
    def steps(self) -> int:
        return len(self._lines)

    def call(self, tool_use_id: str, tool_name: str, tool_input: object) -> None:
        descriptor = _describe_tool(tool_name, tool_input, chat_kind=self.chat_kind)
        self._desc[tool_use_id] = descriptor
        self._lines[tool_use_id] = _progress_line("⏳", tool_name, descriptor)

    def result(self, tool_use_id: str, tool_name: str, *, error: bool) -> None:
        # Keep the call's descriptor so the finished line still says what it did
        # ('✅ Read · wedding.json'); the result event carries no input.
        if error:
            self.failed += 1
        mark = "❌" if error else "✅"
        self._lines[tool_use_id] = _progress_line(mark, tool_name, self._desc.get(tool_use_id, ""))

    def narrate(self, text: str) -> None:
        """Show ``text`` (the agent's latest words before a tool) as the 💬 line."""
        lines = [line for line in text.strip().splitlines() if line.strip()]
        if lines:
            self.narration = _clip(lines[-1], _NARRATION_MAX_CHARS)

    def header(self, now: float) -> str:
        facts = ["⏳ Working", format_elapsed(now - self.started)]
        if self.steps:
            count = f"{self.steps} step" + ("" if self.steps == 1 else "s")
            if self.failed:
                count += f" ({self.failed} failed)"
            facts.append(count)
        return " · ".join(facts)

    def block(self, now: float) -> str:
        """The whole status block: header, narration, and the newest steps."""
        out = [self.header(now)]
        if self.narration:
            out.append(f"💬 {self.narration}")
        if self.show_steps and self._lines:
            lines = list(self._lines.values())
            hidden = len(lines) - _VISIBLE_STEPS
            if hidden > 0:
                out.append(f"+{hidden} earlier")
            out.extend(lines[-_VISIBLE_STEPS:])
        return "\n".join(out)


@dataclass
class ReplyText:
    """The reply's text, kept as the segments a tool call separates.

    Deltas inside one text block join as they came; a tool event closes the
    segment, so the next text starts a paragraph — "…check the logs." and "The
    failure is…" never run together. The current (last, still open) segment is
    the answer tail a live surface shows under the status block; a segment a
    tool call closed is narration.
    """

    _segments: list[str] = field(default_factory=list)
    _open: bool = False

    def add(self, delta: str) -> None:
        if self._open and self._segments:
            self._segments[-1] += delta
        else:
            self._segments.append(delta)
            self._open = True

    def boundary(self) -> str:
        """A tool event: close the open segment and return it ("" if none)."""
        closed = self._segments[-1] if self._open and self._segments else ""
        self._open = False
        return closed

    @property
    def tail(self) -> str:
        """Text written since the last tool event — the answer so far."""
        return self._segments[-1].strip() if self._open and self._segments else ""

    @property
    def started(self) -> bool:
        return any(s.strip() for s in self._segments)

    def full(self) -> str:
        """Everything the agent wrote, one paragraph break per tool boundary."""
        return "\n\n".join(s.strip() for s in self._segments if s.strip())
