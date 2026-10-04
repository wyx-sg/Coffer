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

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.conversation import Conversation
from coffer.domain.pagination import Page, decode_cursor, paginate, position_of, time_and_id

_TAG = "chat_conversations"


@dataclass(frozen=True)
class Narrowing:
    """The listing's source and agent filters, empty meaning every one: ``sources``
    holds ``coffer`` (Coffer's own UI) and channel uids, ``agents`` agent keys."""

    sources: tuple[str, ...] = ()
    agents: tuple[str, ...] = ()

    @classmethod
    def of(cls, sources: Iterable[str] = (), agents: Iterable[str] = ()) -> Narrowing:
        """Sorted and de-duplicated, so the same filters always make the same cursor."""
        return cls(tuple(sorted(set(sources))), tuple(sorted(set(agents))))

    @classmethod
    def parse(cls, sources: str | None, agents: str | None) -> Narrowing:
        """From comma-separated lists (the HTTP query); blank tokens are dropped."""
        return cls.of(_tokens(sources), _tokens(agents))


EVERY = Narrowing()


def _tokens(csv: str | None) -> list[str]:
    return [t for t in (p.strip() for p in (csv or "").split(",")) if t]


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
        contains: str | None = None,
        narrow: Narrowing = EVERY,
    ) -> list[Conversation]:
        """Conversations newest activity first, the id breaking ties; active
        when ``archived`` is False. ``after`` (a row's ``(updated_at, id)``) and
        ``limit`` cut one page of that order; without them, the whole listing.
        ``contains`` keeps the rows whose title or any message's text holds it
        (case-insensitive); ``narrow`` keeps those of its sources and agents."""
        ...

    async def count(
        self, *, archived: bool = False, contains: str | None = None, narrow: Narrowing = EVERY
    ) -> int:
        """How many conversations ``list`` would return without ``after``/``limit``."""
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
    repo: ConversationRepo,
    *,
    archived: bool,
    limit: int,
    cursor: str | None,
    q: str | None = None,
    narrow: Narrowing = EVERY,
) -> Page[Conversation]:
    """One page of the active (or archived) listing, continued by ``cursor``.

    The cursor is bound to which listing it came from: one issued for the
    active threads sent to the archived listing is ``CursorInvalid``, and so is
    one issued for another ``q`` (the title-and-messages search) or ``narrow``.
    """
    q = q.strip() if q else None
    q = q or None
    filters: dict[str, object] = {"archived": archived}
    if q is not None:
        filters["q"] = q.casefold()
    if narrow.sources:
        filters["sources"] = list(narrow.sources)
    if narrow.agents:
        filters["agents"] = list(narrow.agents)
    after = time_and_id(decode_cursor(cursor, list_tag=_TAG, filters=filters), str)
    rows = await repo.list(
        archived=archived, limit=limit + 1, after=after, contains=q, narrow=narrow
    )
    return paginate(
        rows,
        limit,
        list_tag=_TAG,
        filters=filters,
        key=lambda c: position_of(c.updated_at, c.id),
    )
