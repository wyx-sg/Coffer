"""The conversation persistence port, and cursor pages of its listings (spec
chat "List conversations by latest activity", spec resource-framework "Page
growing lists by an opaque cursor").

The order is newest activity first with the conversation id as the tie-break,
and a page is the rows strictly after the previous page's last
``(updated_at, id)``. A conversation whose activity is bumped while a reader
pages therefore moves to the head, which the reader has already passed, rather
than appearing a second time further down.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.conversation import Conversation
from coffer.domain.pagination import Page, decode_cursor, paginate, position_of, time_and_id

_TAG = "chat_conversations"


class ConversationRepo(Protocol):
    """Persistence port for ``Conversation`` rows."""

    async def create(self, conversation: Conversation) -> Conversation: ...

    async def get(self, conversation_id: str) -> Conversation | None: ...

    async def list(
        self,
        *,
        archived: bool = False,
        limit: int | None = None,
        after: tuple[datetime, str] | None = None,
    ) -> list[Conversation]:
        """Conversations newest activity first, the id breaking ties; active
        when ``archived`` is False. ``after`` (a row's ``(updated_at, id)``) and
        ``limit`` cut one page of that order; without them, the whole listing."""
        ...

    async def rename(self, conversation_id: str, new_title: str) -> Conversation: ...

    async def touch(self, conversation_id: str, updated_at: datetime) -> None:
        """Bump ``updated_at`` for the given conversation."""
        ...

    async def get_agent_config(self, conversation_id: str) -> AgentConfig:
        """Typed provider-owned per-conversation state (empty when unset)."""
        ...

    async def set_agent_config(self, conversation_id: str, config: AgentConfig) -> None:
        """Replace the typed provider-owned per-conversation state."""
        ...

    async def set_archived(
        self, conversation_id: str, archived_at: datetime | None
    ) -> Conversation: ...

    async def delete(self, conversation_id: str) -> None: ...


async def page_conversations(
    repo: ConversationRepo, *, archived: bool, limit: int, cursor: str | None
) -> Page[Conversation]:
    """One page of the active (or archived) listing, continued by ``cursor``.

    The cursor is bound to which listing it came from: one issued for the
    active threads sent to the archived listing is ``CursorInvalid``.
    """
    filters = {"archived": archived}
    after = time_and_id(decode_cursor(cursor, list_tag=_TAG, filters=filters), str)
    rows = await repo.list(archived=archived, limit=limit + 1, after=after)
    return paginate(
        rows,
        limit,
        list_tag=_TAG,
        filters=filters,
        key=lambda c: position_of(c.updated_at, c.id),
    )
