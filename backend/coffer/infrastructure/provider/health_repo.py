"""Provider connection health, in ``derived/derived.db``.

A verdict is an observation this machine can make again, so its table is
derived (``coffer.infrastructure.persistence.derived_db``). One row per
connection, keyed by its uid: a rename is not a new connection.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.provider.health import HealthSource, HealthStatus, ProviderHealth
from coffer.infrastructure.persistence.derived_db import ProviderHealthModel


def _tz(dt: datetime) -> datetime:
    """Re-attach UTC if SQLite stripped the tzinfo on read-back."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _health(row: ProviderHealthModel) -> ProviderHealth | None:
    try:
        return ProviderHealth(
            status=HealthStatus(row.status),
            checked_at=_tz(row.checked_at),
            source=HealthSource(row.source),
            message=row.message or "",
            since=_tz(row.since),
        )
    except ValueError:
        return None


class ProviderHealthRepo:
    """Upsert, read and forget each connection's last verdict."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def upsert(self, uid: str, health: ProviderHealth) -> None:
        values = {
            "status": health.status.value,
            "checked_at": health.checked_at,
            "source": health.source.value,
            "message": health.message,
            "since": health.started,
        }
        async with self._sm() as session:
            stmt = (
                sqlite_insert(ProviderHealthModel)
                .values(resource_uid=uid, **values)
                .on_conflict_do_update(index_elements=["resource_uid"], set_=values)
            )
            await session.execute(stmt)
            await session.commit()

    async def get(self, uid: str) -> ProviderHealth | None:
        async with self._sm() as session:
            row = await session.get(ProviderHealthModel, uid)
            return _health(row) if row is not None else None

    async def list_all(self) -> dict[str, ProviderHealth]:
        async with self._sm() as session:
            rows = (await session.execute(select(ProviderHealthModel))).scalars().all()
        out: dict[str, ProviderHealth] = {}
        for row in rows:
            health = _health(row)
            if health is not None:
                out[row.resource_uid] = health
        return out

    async def forget(self, uid: str) -> None:
        async with self._sm() as session:
            await session.execute(
                delete(ProviderHealthModel).where(ProviderHealthModel.resource_uid == uid)
            )
            await session.commit()


__all__ = ["ProviderHealthRepo"]
