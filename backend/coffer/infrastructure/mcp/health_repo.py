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
    """Persisted health state written by the per-server "test connection" route.

    One row per mcp_server, keyed by the server's **uid** (migration 0097). It
    was keyed by the name, which made a rename look like a brand-new server that
    had never been tested — the old row stayed behind as a permanent orphan
    nothing would ever overwrite, and the status page went blank for a server
    that was working a second earlier.
    """

    __tablename__ = "mcp_server_health"

    resource_uid: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


def _tz(dt: datetime) -> datetime:
    """Re-attach UTC if SQLite stripped the tzinfo on read-back."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class MCPServerHealthRepo:
    """Upsert and query persisted upstream health state."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def upsert(self, resource_uid: str, status: HealthStatus, checked_at: datetime) -> None:
        """Insert or update the health record for the given server uid."""
        async with self._sm() as session:
            stmt = (
                sqlite_insert(MCPServerHealthModel)
                .values(resource_uid=resource_uid, status=status, checked_at=checked_at)
                .on_conflict_do_update(
                    index_elements=["resource_uid"],
                    set_={"status": status, "checked_at": checked_at},
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def get(self, resource_uid: str) -> tuple[HealthStatus, datetime] | None:
        """Return (status, checked_at) or None if no record exists."""
        async with self._sm() as session:
            stmt = select(MCPServerHealthModel).where(
                MCPServerHealthModel.resource_uid == resource_uid
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return row.status, _tz(row.checked_at)

    async def list_all(self) -> list[tuple[str, HealthStatus]]:
        """Return all (resource_uid, status) pairs currently persisted."""
        async with self._sm() as session:
            stmt = select(MCPServerHealthModel)
            rows = (await session.execute(stmt)).scalars().all()
            return [(r.resource_uid, r.status) for r in rows]
