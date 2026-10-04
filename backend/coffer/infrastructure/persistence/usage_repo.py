"""SQLAlchemy adapters of the usage ports (``application.usage.ports``).

:class:`SqlAlchemyUsageRepo` writes a spool file's rows and their daily rollup
in ONE transaction: each detail row is inserted with ``ON CONFLICT(source,
dedupe_key) DO NOTHING``, and only a row that was actually inserted is added to
``usage_daily`` (itself an upsert on the grouping key). A replayed file
therefore changes nothing — the property the ingest relies on to delete a file
only after its commit.

SQLite hands ``TIMESTAMP`` columns back naive; every instant written here is
UTC, so reads re-attach UTC.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.usage.ports import (
    DailyUsage,
    PricedRecord,
    RequestFilters,
    StoredUsage,
)
from coffer.domain.usage.records import UsageRecord
from coffer.infrastructure.persistence.keyset import newest_first_after
from coffer.infrastructure.persistence.usage_models import (
    UsageDailyModel,
    UsageRequestModel,
)

#: The token columns the detail and the rollup share.
_TOKEN_COLUMNS = (
    "input_tokens",
    "cache_write_5m_tokens",
    "cache_write_1h_tokens",
    "cache_read_tokens",
    "output_tokens",
    "reasoning_tokens",
    "web_search_requests",
)
#: The rollup's counters, summed by the upsert.
_DAILY_SUMS = ("requests", "unknown_requests", "unpriced_requests", *_TOKEN_COLUMNS, "cost_usd")
#: UsageRecord fields stored as-is on the detail row.
_RECORD_FIELDS = tuple(UsageRecord.model_fields)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _maybe_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _utc(value)


def _detail_values(row: PricedRecord) -> dict[str, object]:
    values: dict[str, object] = {
        name: getattr(row.record, name)
        for name in _RECORD_FIELDS
        if name in UsageRequestModel.__table__.c
    }
    values["started_at"] = _utc(row.record.started_at)
    values["wire"] = str(row.record.wire)
    values["outcome"] = str(row.record.outcome)
    values["cost_usd"] = row.cost_usd
    values["price_version"] = row.price_version
    values["unpriced"] = row.unpriced
    return values


def _daily_values(row: PricedRecord) -> dict[str, object]:
    rec = row.record
    known = rec.usage_known
    values: dict[str, object] = {
        "day": row.day,
        "agent_uid": rec.agent_uid or "",
        "agent_type": rec.agent_type or "",
        "connection_uid": rec.connection_uid or "",
        "model": rec.model or "",
        "requests": 1,
        "unknown_requests": 0 if known else 1,
        "unpriced_requests": 1 if row.unpriced else 0,
        "cost_usd": row.cost_usd or 0.0,
    }
    for name in _TOKEN_COLUMNS:
        values[name] = (getattr(rec, name) or 0) if known else 0
    return values


class SqlAlchemyUsageRepo:
    """``UsageRepo`` over ``usage_requests`` + ``usage_daily``."""

    def __init__(self, sm: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sm

    async def ingest(self, rows: Sequence[PricedRecord]) -> int:
        inserted = 0
        async with self._sm() as session, session.begin():
            for row in rows:
                detail = (
                    sqlite_insert(UsageRequestModel)
                    .values(**_detail_values(row))
                    .on_conflict_do_nothing(index_elements=["source", "dedupe_key"])
                )
                result = await session.execute(detail)
                if not result.rowcount:  # type: ignore[attr-defined]
                    continue  # already ingested: its rollup is already counted
                inserted += 1
                daily = sqlite_insert(UsageDailyModel).values(**_daily_values(row))
                await session.execute(
                    daily.on_conflict_do_update(
                        index_elements=[
                            "day",
                            "agent_uid",
                            "agent_type",
                            "connection_uid",
                            "model",
                        ],
                        set_={
                            name: getattr(UsageDailyModel, name) + getattr(daily.excluded, name)
                            for name in _DAILY_SUMS
                        },
                    )
                )
        return inserted

    async def daily(self, start_day: str, end_day: str) -> list[DailyUsage]:
        async with self._sm() as session:
            stmt = (
                select(UsageDailyModel)
                .where(UsageDailyModel.day >= start_day, UsageDailyModel.day <= end_day)
                .order_by(UsageDailyModel.day, UsageDailyModel.id)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            DailyUsage(
                day=r.day,
                agent_uid=r.agent_uid or None,
                agent_type=r.agent_type or None,
                connection_uid=r.connection_uid or None,
                model=r.model or None,
                **{name: getattr(r, name) for name in _DAILY_SUMS},
            )
            for r in rows
        ]

    async def requests(
        self,
        *,
        filters: RequestFilters,
        limit: int,
        after: tuple[datetime, int] | None,
    ) -> list[StoredUsage]:
        m = UsageRequestModel
        stmt = select(m).order_by(m.started_at.desc(), m.id.desc()).limit(limit)
        if after is not None:
            stmt = stmt.where(newest_first_after(m.started_at, m.id, (_utc(after[0]), after[1])))
        if filters.agent_uid is not None:
            stmt = stmt.where(m.agent_uid == filters.agent_uid)
        if filters.connection_uid is not None:
            stmt = stmt.where(m.connection_uid == filters.connection_uid)
        if filters.model is not None:
            stmt = stmt.where(m.model == filters.model)
        if filters.since is not None:
            stmt = stmt.where(m.started_at >= _utc(filters.since))
        if filters.until is not None:
            stmt = stmt.where(m.started_at < _utc(filters.until))
        async with self._sm() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_stored(r) for r in rows]


def _stored(row: UsageRequestModel) -> StoredUsage:
    data = {name: getattr(row, name) for name in _RECORD_FIELDS if hasattr(row, name)}
    data["started_at"] = _utc(row.started_at)
    return StoredUsage(
        id=row.id,
        record=UsageRecord.model_validate(data),
        cost_usd=row.cost_usd,
        price_version=row.price_version,
        unpriced=row.unpriced,
    )


__all__ = ["SqlAlchemyUsageRepo"]
