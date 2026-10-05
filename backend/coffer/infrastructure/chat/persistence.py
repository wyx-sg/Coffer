"""SQLAlchemy repo for the conversation index (table ``conversations``).

Implements the ``ConversationRepo`` Protocol defined in
``coffer.application.chat.conversation_repo``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import (
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.chat.conversation_repo import EVERY, Narrowing
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.errors import ConversationNotFound
from coffer.infrastructure.chat.conversation_filter import listing_filter
from coffer.infrastructure.chat.persistence_models import ConversationModel
from coffer.infrastructure.persistence.keyset import newest_first_after


def _tz(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _parse_config(raw: str | None) -> AgentConfig:
    """The stored ``agent_config`` JSON (an empty ``AgentConfig`` when unset or malformed)."""
    if not raw:
        return AgentConfig()
    try:
        parsed = json.loads(raw)
    except ValueError:
        return AgentConfig()
    return AgentConfig.from_json(parsed) if isinstance(parsed, dict) else AgentConfig()


# ---------------------------------------------------------------------------
# ConversationRepo
# ---------------------------------------------------------------------------


class ConversationRepo:
    """SQLAlchemy implementation of the ``ConversationRepo`` Protocol."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    def _to_domain(self, row: ConversationModel) -> Conversation:
        return Conversation(
            id=row.id,
            agent_key=row.agent_key,
            title=row.title,
            created_at=_tz(row.created_at),
            updated_at=_tz(row.updated_at),
            channel_uid=row.channel_uid,
            peer_chat_id=row.peer_chat_id,
            agent_config=_parse_config(row.agent_config),
        )

    async def create(self, conversation: Conversation) -> Conversation:
        async with self._sm() as session:
            row = ConversationModel(
                id=conversation.id,
                agent_key=conversation.agent_key,
                title=conversation.title,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                channel_uid=conversation.channel_uid,
                peer_chat_id=conversation.peer_chat_id,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_domain(row)

    async def get(self, conversation_id: str) -> Conversation | None:
        async with self._sm() as session:
            stmt = select(ConversationModel).where(ConversationModel.id == conversation_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            return self._to_domain(row) if row else None

    async def list(
        self,
        *,
        limit: int | None = None,
        after: tuple[datetime, str] | None = None,
        contains: str | None = None,
        narrow: Narrowing = EVERY,
    ) -> list[Conversation]:
        """Channel conversations newest activity first with the id breaking ties.
        ``after`` (the previous page's last
        ``(updated_at, id)``) and ``limit`` cut one page of that order; without
        them the whole listing comes back.
        """
        async with self._sm() as session:
            stmt = select(ConversationModel).order_by(
                ConversationModel.updated_at.desc(), ConversationModel.id.desc()
            )
            stmt = listing_filter(stmt, contains=contains, narrow=narrow)
            if after is not None:
                stmt = stmt.where(
                    newest_first_after(ConversationModel.updated_at, ConversationModel.id, after)
                )
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def by_session_ids(self, session_ids: Sequence[str]) -> Sequence[Conversation]:
        wanted = set(session_ids)
        if not wanted:
            return []
        # The id sits inside the JSON text of ``agent_config``: narrow by substring
        # in SQL, then confirm the parsed field, so an id that merely appears in
        # another field never matches. (Session ids are ``[A-Za-z0-9-]``, so they
        # carry no LIKE wildcard.)
        async with self._sm() as session:
            stmt = select(ConversationModel).where(
                or_(*(ConversationModel.agent_config.contains(sid) for sid in wanted))
            )
            rows = (await session.execute(stmt)).scalars().all()
        found = [self._to_domain(r) for r in rows]
        return [c for c in found if c.agent_config.session_id in wanted]

    async def rename(self, conversation_id: str, new_title: str) -> Conversation:
        async with self._sm() as session:
            stmt = (
                update(ConversationModel)
                .where(ConversationModel.id == conversation_id)
                .values(title=new_title)
                .returning(ConversationModel)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ConversationNotFound(conversation_id)
            await session.commit()
            return self._to_domain(row)

    async def touch(self, conversation_id: str, updated_at: datetime) -> None:
        """Bump ``updated_at`` for the given conversation."""
        async with self._sm() as session:
            stmt = (
                update(ConversationModel)
                .where(ConversationModel.id == conversation_id)
                .values(updated_at=updated_at)
            )
            await session.execute(stmt)
            await session.commit()

    async def get_agent_config(self, conversation_id: str) -> AgentConfig:
        """Read the typed provider config (an empty ``AgentConfig`` when unset)."""
        async with self._sm() as session:
            row = await session.get(ConversationModel, conversation_id)
            if row is None:
                raise ConversationNotFound(conversation_id)
            return _parse_config(row.agent_config)

    async def set_agent_config(self, conversation_id: str, config: AgentConfig) -> None:
        """Replace the typed provider config for a conversation."""
        async with self._sm() as session:
            stmt = (
                update(ConversationModel)
                .where(ConversationModel.id == conversation_id)
                .values(agent_config=json.dumps(config.to_json()))
            )
            result = await session.execute(stmt)
            if result.rowcount == 0:
                raise ConversationNotFound(conversation_id)
            await session.commit()

    async def delete(self, conversation_id: str) -> None:
        async with self._sm() as session:
            stmt = sa_delete(ConversationModel).where(ConversationModel.id == conversation_id)
            await session.execute(stmt)
            await session.commit()


__all__ = ["ConversationModel", "ConversationRepo"]
