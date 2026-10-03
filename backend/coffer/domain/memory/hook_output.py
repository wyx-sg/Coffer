"""What Coffer's memory hook prints, and how a delivered note is worded .

Both supported agents read one JSON shape from every event: Claude Code and
Codex take ``hookSpecificOutput.additionalContext`` as context. So there is
one builder here, not one per agent.

**Wording.** A delivered note reads as provenance plus fact — "Coffer memory, a
note the user's agents recorded (``<file>``): the user's standing rule is: …" —
never as an instruction. An imperative note delivered before a command was
quoted back to the user as prompt injection in the eval; worded this way, none
of 72 runs flagged one.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.memory.note import TYPE_FEEDBACK, Note

#: The line above a prompt's retrieved notes.
RETRIEVAL_HEADER = (
    "Coffer memory: notes recorded for this user that may apply to this request. "
    "Each line is the user's standing rule or a fact they recorded; open the note "
    "if it applies."
)


def note_statement(note: Note) -> str:
    """The note's substance as one sentence: a standing rule for a ``feedback``
    note, a recorded fact for everything else."""
    title = note.title.strip() or note.slug
    description = " ".join(note.description.split())
    fact = f"{title} — {description}" if description else title
    if note.type == TYPE_FEEDBACK:
        return f"the user's standing rule is: {fact}"
    return f"a fact they recorded: {fact}"


def note_line(note: Note, path: str) -> str:
    """One retrieved note, as a prompt's delivery lists it."""
    return f"- ({path}) {note_statement(note)}"


def context_output(event: str, text: str) -> dict[str, Any]:
    """The JSON that adds ``text`` to the session at ``event``."""
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


__all__ = [
    "RETRIEVAL_HEADER",
    "context_output",
    "note_line",
    "note_statement",
]
