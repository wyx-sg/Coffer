"""Shared helpers for the live agent adapters (spec 008).

Small, dependency-free pieces the SDK-backed (:mod:`claude_sdk_agent`) and
app-server-backed (:mod:`codex_agent`) adapters both need:

- :class:`ParseState` — mutable state threaded through a turn's output parsing
  (the discovered session id, in-flight tool names, token counts, and whether a
  terminal event has been emitted yet).
- :data:`SessionSink` — the callback an adapter calls to persist a newly
  discovered upstream session id back onto the conversation, so the next turn
  can ``--resume`` it.
- :func:`last_user_text` — the prompt for a turn: the text of the most recent
  user message in the history.

These were extracted from the now-deleted ``cli_agent`` module when the legacy
CLI adapters were retired (ADR-031 §4); the live adapters are the only callers.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from coffer.domain.chat.message import Message, Role, TextBlock

#: Persist a discovered upstream session id back onto the conversation.
SessionSink = Callable[[str], Awaitable[None]]


@dataclass
class ParseState:
    """Mutable state threaded through an adapter's per-turn output parsing."""

    session_id: str | None = None
    tool_names: dict[str, str] = field(default_factory=dict)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    terminal_emitted: bool = False


def last_user_text(history: Sequence[Message]) -> str:
    """The text of the most recent user message — the prompt for this turn."""
    for msg in reversed(history):
        if msg.role is Role.USER:
            return "".join(b.text for b in msg.content if isinstance(b, TextBlock)).strip()
    return ""


__all__ = ["ParseState", "SessionSink", "last_user_text"]
