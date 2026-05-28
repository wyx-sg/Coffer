"""MCP server-health persistence: model + repo.

Extracted from ``persistence.py`` to keep that module under the 400-line
guideline. ``persistence.py`` re-exports the public names so existing
imports continue to work.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import TIMESTAMP, String, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base

# Write-side type alias for health status values.
HealthStatus = Literal["healthy", "failing"]


class MCPServerHealthModel(Base):
    """Persisted health state written by POST /{name}/test."""

    __tablename__ = "mcp_server_health"

    resource_name: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


def _tz(dt: datetime) -> datetime:
    """Re-attach UTC if SQLite stripped the tzinfo on read-back."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class MCPServerHealthRepo:
    """Upsert and query persisted upstream health state."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def upsert(self, resource_name: str, status: HealthStatus, checked_at: datetime) -> None:
        """Insert or update the health record for the given resource_name."""
        async with self._sm() as session:
            stmt = (
                sqlite_insert(MCPServerHealthModel)
                .values(resource_name=resource_name, status=status, checked_at=checked_at)
                .on_conflict_do_update(
                    index_elements=["resource_name"],
                    set_={"status": status, "checked_at": checked_at},
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def get(self, resource_name: str) -> tuple[HealthStatus, datetime] | None:
        """Return (status, checked_at) or None if no record exists."""
        async with self._sm() as session:
            stmt = select(MCPServerHealthModel).where(
                MCPServerHealthModel.resource_name == resource_name
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return row.status, _tz(row.checked_at)

    async def list_all(self) -> list[tuple[str, HealthStatus]]:
        """Return all (resource_name, status) pairs currently persisted."""
        async with self._sm() as session:
            stmt = select(MCPServerHealthModel)
            rows = (await session.execute(stmt)).scalars().all()
            return [(r.resource_name, r.status) for r in rows]
