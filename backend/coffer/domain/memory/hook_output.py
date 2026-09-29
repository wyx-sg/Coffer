"""What Coffer's memory hook prints, and how a delivered note is worded (ADR
memory-reaches-a-session-at-prompt-time-and-before-a-known-trap, items 4 and 6).

Both supported agents read one JSON shape from every event: Claude Code and
Codex take ``hookSpecificOutput.additionalContext`` as context, and both honour
``permissionDecision: "deny"`` on ``PreToolUse`` with its reason shown to the
model (Codex as "Command blocked by PreToolUse hook: <reason>"). So there is
one set of builders here, not one per agent.

**Wording.** A delivered note reads as provenance plus fact — "Coffer memory, a
note the user's agents recorded (``<file>``): the user's standing rule is: …" —
never as an instruction. An imperative note delivered before a command was
quoted back to the user as prompt injection in the eval; worded this way, none
of 72 runs flagged one.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.memory.note import TYPE_FEEDBACK, Note

#: What the guard adds after the note when it holds a command.
HELD_ONCE = (
    " (Held once by a Coffer memory trigger so you can adjust; "
    "run it again if it is still what you intend.)"
)

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


def note_reason(note: Note, path: str) -> str:
    """One note as a guard's reason or an error's context."""
    return f"Coffer memory, a note recorded for this user ({path}): {note_statement(note)}"


def context_output(event: str, text: str) -> dict[str, Any]:
    """The JSON that adds ``text`` to the session at ``event``."""
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def deny_output(event: str, reason: str) -> dict[str, Any]:
    """The JSON that stops one tool call with ``reason`` shown to the model."""
    return {
        "hookSpecificOutput": {
            "hookEventName": event,
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


__all__ = [
    "HELD_ONCE",
    "RETRIEVAL_HEADER",
    "context_output",
    "deny_output",
    "note_line",
    "note_reason",
    "note_statement",
]
