"""The attention items ignored on this machine.

One row per ignored key (``application.attention.attention_key``). The table
is machine-local like the rest of the database: the vault's sync carries
resources, not this, so an agent ignored on one Mac is still asked about on
another. Implements ``application.attention.IgnoreStore``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import TIMESTAMP, String, delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class AttentionIgnoreModel(Base):
    __tablename__ = "attention_ignores"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    ignored_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class SqlAlchemyAttentionIgnoreRepo:
    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def keys(self) -> set[str]:
        async with self._sm() as session:
            rows = (await session.execute(select(AttentionIgnoreModel.key))).scalars()
            return set(rows)

    async def add(self, key: str) -> bool:
        async with self._sm() as session:
            if await session.get(AttentionIgnoreModel, key) is not None:
                return False
            session.add(AttentionIgnoreModel(key=key, ignored_at=datetime.now(tz=UTC)))
            await session.commit()
            return True

    async def remove(self, key: str) -> bool:
        async with self._sm() as session:
            result = await session.execute(
                delete(AttentionIgnoreModel).where(AttentionIgnoreModel.key == key)
            )
            await session.commit()
            return bool(result.rowcount)


__all__ = ["AttentionIgnoreModel", "SqlAlchemyAttentionIgnoreRepo"]
