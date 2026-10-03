"""The "Stopping…" message a ``/stop`` sent, kept so the turn's end can rewrite it.

Where the platform can edit a plain message (``capabilities.edits_text``) the
chat shows one line that changes from "⏹ Stopping…" to "⏹ Stopped after 12s."
rather than two. The note lives only as long as the running turn it belongs to.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["StopNotice", "forget", "remember", "take"]


@dataclass(frozen=True)
class StopNotice:
    chat_id: str
    message_id: str
    chat_kind: str


_PENDING: dict[str, StopNotice] = {}


def remember(conversation_id: str, notice: StopNotice) -> None:
    _PENDING[conversation_id] = notice


def take(conversation_id: str) -> StopNotice | None:
    """The notice for this conversation's turn, removed — each is used once."""
    return _PENDING.pop(conversation_id, None)


def forget(conversation_id: str) -> None:
    _PENDING.pop(conversation_id, None)
