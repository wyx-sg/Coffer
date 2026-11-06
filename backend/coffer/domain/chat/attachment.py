"""A user-supplied attachment referenced by local path (spec channels).

The bytes live on disk — downloaded from a channel into
``~/.coffer/content/channel-media`` — never inline in the chat DB. Every agent
adapter hands the agent the path, and the agent opens the file with its own
tools, whatever it is. See the channel-attachments ADR.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from coffer.domain.turn_markers import ATTACHMENTS, ATTACHMENTS_END, block

#: What an attachment with no ``source`` came from.
USER_SOURCE = "the user's message"


@dataclass(frozen=True)
class Attachment:
    """One file handed to an agent for a turn — a path plus how to read it."""

    path: str  # absolute local path to the bytes
    mime: str  # e.g. "image/jpeg", "application/pdf", "audio/ogg"
    filename: str  # best-effort original name, for display / the agent's benefit
    #: Its ``#n`` in the turn, which the turn text points at ("→ attachment #2");
    #: 0 when unnumbered.
    number: int = 0
    #: Where in the turn it came from, as a phrase: ``the user's message 2/2``,
    #: ``the forwarded record``, ``the quoted message``, ``a thread message``.
    #: ``""`` reads as the user's own message.
    source: str = ""

    @property
    def is_image(self) -> bool:
        return self.mime.startswith("image/")

    @property
    def unreadable_kind(self) -> str:
        """``voice`` / ``video`` for media no agent reads directly, else ``""``."""
        if self.mime.startswith("audio/"):
            return "voice"
        if self.mime.startswith("video/"):
            return "video"
        return ""


def attachment_label(att: Attachment) -> str:
    """``#2 from the user's message 2/2: report.pdf`` — how every agent adapter
    names one attachment, so the turn text's ``→ attachment #2`` resolves."""
    source = att.source or USER_SOURCE
    number = f"#{att.number} " if att.number else ""
    # A platform-supplied name: one line, so it cannot open a line of its own.
    name = " ".join("".join(" " if ch < " " else ch for ch in att.filename).split())
    return f"{number}from {source}: {name or 'file'}"


def attachment_line(att: Attachment, *, readable: bool = True) -> str:
    """One line of the turn's ``[Attachments]`` block (spec channels "Hand inbound
    attachments to the turn as references"). Voice and video say plainly that the
    model cannot read them; a file that is gone says it could not be read."""
    label = attachment_label(att)
    if not readable:
        return f"{label} — could not be read (the file is no longer on disk)"
    kind = att.unreadable_kind
    if kind:
        return f"{label} — {kind}; the model cannot read it directly; file at {att.path}"
    if att.is_image:
        return f"{label} (image, saved at {att.path})"
    return f"{label} (saved at {att.path})"


def attachments_block(lines: Sequence[str]) -> str:
    """The ``[Attachments]`` block around ``lines``; ``""`` when there are none."""
    return block(ATTACHMENTS, ATTACHMENTS_END, list(lines)) if lines else ""


def attachment_note(attachments: Sequence[Attachment]) -> str:
    """A short stand-in for a message that carries files and no text, so its
    ``[User message]`` block is not blank — ``(sent an image → attachment #2)``.
    Used for a channel's uncaptioned photo."""
    kind = "image" if all(a.is_image for a in attachments) else "file"
    if len(attachments) == 1:
        what = f"an {kind}" if kind == "image" else f"a {kind}"
    else:
        what = f"{len(attachments)} {kind}s"
    numbers = [f"#{a.number}" for a in attachments if a.number]
    if numbers and len(numbers) == len(attachments):
        noun = "attachment" if len(numbers) == 1 else "attachments"
        return f"(sent {what} → {noun} {', '.join(numbers)})"
    return f"(sent {what}: {', '.join(a.filename for a in attachments)})"


__all__ = [
    "USER_SOURCE",
    "Attachment",
    "attachment_label",
    "attachment_line",
    "attachment_note",
    "attachments_block",
]
