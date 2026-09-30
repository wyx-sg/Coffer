"""Every sync round this machine ran, in ``runs.db`` (implements
``application.sync.round_ports.RoundHistoryPort``).

Machine-local: a history that travelled would be another machine's account
of rounds this one never ran. The columns are what a list reads at a glance
(status, times, the commit it reached, the error); everything else a
``RoundRecord`` carries is one JSON payload written once, so no column can
disagree with it. Swept by the retention worker (``sync_runs``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.domain.sync.rounds import RoundRecord
from coffer.infrastructure.persistence.models import SyncRunModel


def _when(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class SyncRunRepo:
    def __init__(self, sm: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sm

    async def append(self, record: RoundRecord) -> RoundRecord:
        payload = record.to_json()
        payload.pop("id", None)
        async with self._sm() as session, session.begin():
            row = SyncRunModel(
                started_at=_when(record.started_at),
                finished_at=_when(record.finished_at),
                status=record.status.value,
                join_kind=record.join,
                commit_sha=record.to_commit,
                error=record.detail,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
            session.add(row)
            await session.flush()
            new_id = row.id
        return RoundRecord.from_json(payload, id=new_id)

    async def recent(self, limit: int, offset: int = 0) -> list[RoundRecord]:
        async with self._sm() as session:
            rows = (
                await session.execute(
                    select(SyncRunModel)
                    .order_by(SyncRunModel.finished_at.desc(), SyncRunModel.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).scalars()
            return [_record(r) for r in rows]

    async def get(self, round_id: int) -> RoundRecord | None:
        async with self._sm() as session:
            row = await session.get(SyncRunModel, round_id)
            return _record(row) if row is not None else None

    async def count(self) -> int:
        async with self._sm() as session:
            return int((await session.execute(select(func.count(SyncRunModel.id)))).scalar_one())


def _record(row: SyncRunModel) -> RoundRecord:
    return RoundRecord.from_json(json.loads(row.payload_json or "{}"), id=row.id)


__all__ = ["SyncRunRepo"]
