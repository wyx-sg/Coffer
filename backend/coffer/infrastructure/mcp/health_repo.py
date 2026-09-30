"""MCP server-health persistence, in ``derived/derived.db``.

A health check is an observation this machine can make again, so its table
is derived (``coffer.infrastructure.persistence.derived_db``). One row per
mcp_server, keyed by the server's uid: a rename is not a new server.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.infrastructure.persistence.derived_db import MCPServerHealthModel

# Write-side type alias for health status values.
HealthStatus = Literal["healthy", "failing"]


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


__all__ = ["HealthStatus", "MCPServerHealthModel", "MCPServerHealthRepo"]
