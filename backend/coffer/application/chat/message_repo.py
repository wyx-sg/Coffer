"""The persistence port for ``chat_messages`` rows (the ``MessageRepo`` Protocol)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from coffer.domain.chat.message import ContentBlock, Message


class MessageRepo(Protocol):
    """Persistence port for ``chat_messages`` rows."""

    async def append(self, message: Message) -> Message: ...

    async def finalize(
        self,
        message_id: str,
        *,
        content: list[ContentBlock],
        status: str,
        model_id: str | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        finished_at: datetime | None = None,
    ) -> None:
        """Update an existing (streaming) message with its final content/status
        and the time the reply ended."""
        ...

    async def save_partial(self, message_id: str, *, content: list[ContentBlock]) -> None:
        """Overwrite a still-``streaming`` row's content (a mid-turn flush); a row
        already finalised is left untouched."""
        ...

    async def delete_message(self, message_id: str) -> None:
        """Delete a single message by id."""
        ...

    async def list_by_conversation(
        self, conversation_id: str, *, limit: int | None = None
    ) -> list[Message]:
        """Return messages ordered by ``seq`` ascending; ``limit`` keeps only
        the most recent N (still oldest-first)."""
        ...

    async def latest_with_text(
        self, conversation_ids: Sequence[str], *, depth: int
    ) -> dict[str, list[Message]]:
        """Up to ``depth`` of each conversation's newest messages that carry a
        text block, newest first, in ONE read; a conversation with none is
        absent."""
        ...

    async def next_seq(self, conversation_id: str) -> int:
        """Return the next sequence number for the given conversation."""
        ...

    async def delete_by_conversation(self, conversation_id: str) -> None: ...

    async def sweep_streaming(self, *, before: datetime | None = None) -> int:
        """Flip ``status='streaming'`` rows to ``'failed'``.

        Called once at startup to recover from a prior crash. With ``before`` only
        rows created earlier than that instant are flipped, so a turn that began
        after the daemon came up is never mistaken for a leftover. Returns the
        number of rows updated.
        """
        ...
