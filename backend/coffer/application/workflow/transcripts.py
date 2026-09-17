"""What the run's earlier tasks said, as the next task reads it (FR-029, FR-030).

A run has no conversation of its own. Every conversation belongs to one task,
so the shared context a node opens with is **the transcripts of the tasks that
ran before it** — and a redirection the developer typed inside one task's
conversation reaches every later task because it is part of that transcript
(SC-004), not because anything copied it to a second place.

Three shapes live here rather than in ``ports`` or ``context_composer``,
because three modules need them and none of the three owns them: the composer
renders them, ``context_budget`` measures and summarises them, and
``compaction`` reuses the message shape for one conversation's own turns.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

__all__ = [
    "TaskTranscript",
    "TaskTranscriptsPort",
    "TranscriptMessage",
    "quote_message",
    "render_messages",
    "render_transcript",
    "transcript_title",
]


@dataclass(frozen=True)
class TranscriptMessage:
    """One message of one task's conversation, as it will be quoted.

    ``role`` is free text on purpose — it is rendered, never branched on, and
    the chat layer's own vocabulary is behind a fence this module does not
    cross.
    """

    role: str
    text: str
    at: datetime | None = None


@dataclass(frozen=True)
class TaskTranscript:
    """One earlier task's whole conversation, attributed to it.

    ``node_key`` and ``attempt`` are carried rather than derived because the
    context *names* what it summarised or omitted (FR-047), and "the coding
    node's second attempt" is the only name a developer can act on.
    """

    node_key: str
    attempt: int
    messages: tuple[TranscriptMessage, ...] = field(default_factory=tuple)
    #: The task's display name, when the caller has one. Falls back to the key.
    name: str | None = None


class TaskTranscriptsPort(Protocol):
    """The conversations of the run's earlier tasks, oldest first.

    A seam out of this kind — a task's conversation is an ordinary conversation
    on the chat platform — so the composition root satisfies it and nothing
    here imports the chat layer.

    ``before_attempt_id`` is the attempt now opening: everything the run has
    said *up to* it is shared context, and the attempt's own conversation is
    not (it is where the reader already is). Bounding by the attempt rather
    than by a timestamp is what keeps a retry honest — the new attempt reads
    the failed one's transcript, because what went wrong is the most useful
    thing anyone said.
    """

    async def transcripts(
        self, run_id: str, before_attempt_id: str
    ) -> Sequence[TaskTranscript]: ...


def transcript_title(transcript: TaskTranscript) -> str:
    """How one task is named in a heading, a summary, or an omission notice."""
    label = transcript.name or transcript.node_key
    return f"`{transcript.node_key}` attempt {transcript.attempt} — {label}"


def quote_message(message: TranscriptMessage) -> str:
    stamp = ""
    if message.at is not None:
        stamp = f" _{message.at.astimezone(UTC).strftime('%Y-%m-%d %H:%M:%S')}Z_"
    body = message.text.strip().replace("\n", "\n  ")
    return f"- **{message.role}**{stamp}: {body}"


def render_transcript(transcript: TaskTranscript) -> str:
    """One task's transcript in full, under its own sub-heading."""
    lines = [f"### {transcript_title(transcript)}", ""]
    if not transcript.messages:
        lines.append("_Nothing was said in this task's conversation._")
    else:
        lines.extend(quote_message(message) for message in transcript.messages)
    return "\n".join(lines)


def render_messages(messages: Sequence[TranscriptMessage]) -> str:
    """A bare run of messages — what a compaction hands to the summariser."""
    return "\n".join(quote_message(message) for message in messages)
