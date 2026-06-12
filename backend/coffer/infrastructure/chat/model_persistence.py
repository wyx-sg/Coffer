"""SQLAlchemy ORM model and repo for chat model configs.

Table: ``chat_models``.
Implements the ``ChatModelRepo`` Protocol defined in
``coffer.application.chat.model_service``.

``set_default`` atomically clears all ``is_default`` flags and sets the target's.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import TIMESTAMP, Integer, String, Text, UniqueConstraint, select, update
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.chat.model import ModelConfig, ProviderType
from coffer.domain.errors import ModelNotFound, ModelRejected
from coffer.infrastructure.persistence.base import Base

# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------


class ChatModelModel(Base):
    """Row in the ``chat_models`` table."""

    __tablename__ = "chat_models"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    credential_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("display_name", name="uq_chat_models_display_name"),)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tz(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# ChatModelRepo
# ---------------------------------------------------------------------------


class ChatModelRepo:
    """SQLAlchemy implementation of the ``ChatModelRepo`` Protocol."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    def _to_domain(self, row: ChatModelModel) -> ModelConfig:
        return ModelConfig(
            id=row.id,
            display_name=row.display_name,
            provider=ProviderType(row.provider),
            model=row.model,
            credential_ref=row.credential_ref,
            base_url=row.base_url,
            is_default=bool(row.is_default),
            created_at=_tz(row.created_at),
            updated_at=_tz(row.updated_at),
        )

    async def create(self, model: ModelConfig) -> ModelConfig:
        async with self._sm() as session:
            row = ChatModelModel(
                id=model.id,
                display_name=model.display_name,
                provider=model.provider,
                model=model.model,
                credential_ref=model.credential_ref,
                base_url=model.base_url,
                is_default=1 if model.is_default else 0,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                # The only unique constraint is on display_name; surface it as
                # a domain rejection (-> 400) rather than a raw 500.
                raise ModelRejected(
                    reason="duplicate_name",
                    message=f"a model named {model.display_name!r} already exists",
                ) from exc
            await session.refresh(row)
            return self._to_domain(row)

    async def get(self, model_id: str) -> ModelConfig | None:
        async with self._sm() as session:
            stmt = select(ChatModelModel).where(ChatModelModel.id == model_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            return self._to_domain(row) if row else None

    async def list(self) -> list[ModelConfig]:
        async with self._sm() as session:
            stmt = select(ChatModelModel)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def update(self, model: ModelConfig) -> ModelConfig:
        async with self._sm() as session:
            stmt = (
                update(ChatModelModel)
                .where(ChatModelModel.id == model.id)
                .values(
                    display_name=model.display_name,
                    provider=model.provider,
                    model=model.model,
                    credential_ref=model.credential_ref,
                    base_url=model.base_url,
                    is_default=1 if model.is_default else 0,
                    updated_at=model.updated_at,
                )
                .returning(ChatModelModel)
            )
            try:
                row = (await session.execute(stmt)).scalar_one_or_none()
                if row is None:
                    raise ModelNotFound(model.id)
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                # Same duplicate-name mapping as create(): the unique
                # constraint is the authoritative gate (-> 400, not 500).
                raise ModelRejected(
                    reason="duplicate_name",
                    message=f"a model named {model.display_name!r} already exists",
                ) from exc
            return self._to_domain(row)

    async def delete(self, model_id: str) -> None:
        async with self._sm() as session:
            stmt = sa_delete(ChatModelModel).where(ChatModelModel.id == model_id)
            await session.execute(stmt)
            await session.commit()

    async def get_default(self) -> ModelConfig | None:
        async with self._sm() as session:
            stmt = select(ChatModelModel).where(ChatModelModel.is_default == 1)
            row = (await session.execute(stmt)).scalar_one_or_none()
            return self._to_domain(row) if row else None

    async def set_default(self, model_id: str) -> None:
        """Atomically clear all ``is_default`` flags and set the target's.

        Uses two UPDATE statements within a single transaction to guarantee
        the single-default invariant.
        """
        now = datetime.now(tz=UTC)
        async with self._sm() as session:
            # Clear only the current default (at most one row) so unrelated
            # models keep their ``updated_at``.
            clear_stmt = (
                update(ChatModelModel)
                .where(ChatModelModel.is_default == 1)
                .values(is_default=0, updated_at=now)
            )
            await session.execute(clear_stmt)
            # Then set the target.
            set_stmt = (
                update(ChatModelModel)
                .where(ChatModelModel.id == model_id)
                .values(is_default=1, updated_at=now)
            )
            await session.execute(set_stmt)
            await session.commit()


__all__ = [
    "ChatModelModel",
    "ChatModelRepo",
]
