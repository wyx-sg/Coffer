"""One conversation's messages, as compaction reads and rewrites them.

What is left here is deliberately small. This module once also carried a run's
EARLIER tasks from one conversation into the next one's opening message; that
is gone, because a task now opens with an index of what the run produced rather
than with anybody else's conversation (``task_index``). What remains is the
shape of a single conversation's own turns, which ``compaction`` needs in order
to replace the oldest of them with a summary that stays in the conversation
(spec workflow "Compact a long node conversation into a summary").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

__all__ = [
    "TranscriptMessage",
    "quote_message",
    "render_messages",
]


@dataclass(frozen=True)
class TranscriptMessage:
    """One message of one conversation, as it will be quoted.

    ``role`` is free text on purpose — it is rendered, never branched on, and
    the chat layer's own vocabulary is behind a fence this module does not
    cross.
    """

    role: str
    text: str
    at: datetime | None = None


def quote_message(message: TranscriptMessage) -> str:
    stamp = ""
    if message.at is not None:
        stamp = f" _{message.at.astimezone(UTC).strftime('%Y-%m-%d %H:%M:%S')}Z_"
    body = message.text.strip().replace("\n", "\n  ")
    return f"- **{message.role}**{stamp}: {body}"


def render_messages(messages: Sequence[TranscriptMessage]) -> str:
    """A bare run of messages — what a compaction hands to the summariser."""
    return "\n".join(quote_message(message) for message in messages)
