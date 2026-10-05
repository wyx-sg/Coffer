"""The "Stopping…" message a ``/stop`` sent, kept so the turn's end can rewrite it.

Where the platform can edit a plain message (``capabilities.edits_text``) the
chat shows one line that changes from "⏹ Stopping “title”…" to "⏹ Stopped
“title” after 12s." rather than two; elsewhere the note still carries what the
stopped line names (the conversation, the messages left on hold). The note lives
only as long as the running turn it belongs to.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["StopNotice", "forget", "remember", "take"]


@dataclass(frozen=True)
class StopNotice:
    chat_id: str
    #: The "Stopping…" message to rewrite; "" where the platform cannot edit it.
    message_id: str
    chat_kind: str
    #: The stopped conversation's title, as the chat knows it.
    title: str = ""
    #: Messages queued behind the turn, held by the interrupt's pause.
    held: int = 0


_PENDING: dict[str, StopNotice] = {}


def remember(conversation_id: str, notice: StopNotice) -> None:
    _PENDING[conversation_id] = notice


def take(conversation_id: str) -> StopNotice | None:
    """The notice for this conversation's turn, removed — each is used once."""
    return _PENDING.pop(conversation_id, None)


def forget(conversation_id: str) -> None:
    _PENDING.pop(conversation_id, None)
