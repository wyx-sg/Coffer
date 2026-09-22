"""SQLAlchemy InternalEngineConfigRepo — the singleton row of Coffer's own settings.

Split out of ``repos.py`` to keep that module within the file-size budget, as
``retention_repo`` was before it; the public name
``SqlAlchemyInternalEngineConfigRepo`` is re-exported from ``repos`` so existing
import sites keep working.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.internal_engine_config import (
    AGGREGATE,
    CURATE,
    DISTIL,
    GlobalInternalEngineConfig,
    UpkeepSetting,
)
from coffer.infrastructure.persistence.models import InternalEngineConfigModel

#: Which pair of columns each unattended pass keeps its switch and timer in.
#: One table rather than a branch per pass, so adding a pass is one entry.
_UPKEEP_COLUMNS = {
    AGGREGATE: ("auto_aggregate_enabled", "aggregate_interval_s"),
    DISTIL: ("auto_distil_enabled", "distil_interval_s"),
    CURATE: ("auto_curate_enabled", "curate_interval_s"),
}


class SqlAlchemyInternalEngineConfigRepo:
    """Concrete repo for the singleton ``internal_engine_config`` row."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def get(self) -> GlobalInternalEngineConfig | None:
        async with self._sm() as session:
            stmt = select(InternalEngineConfigModel).where(InternalEngineConfigModel.id == 1)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            updated = row.updated_at.replace(tzinfo=UTC) if row.updated_at else datetime.now(tz=UTC)
            return self._to_domain(row, updated)

    async def set(
        self,
        *,
        model: str | None,
        curate_owner_machine_id: str | None = None,
        upkeep: Mapping[str, UpkeepSetting] | None = None,
    ) -> GlobalInternalEngineConfig:
        async with self._sm() as session:
            stmt = select(InternalEngineConfigModel).where(InternalEngineConfigModel.id == 1)
            row = (await session.execute(stmt)).scalar_one_or_none()
            now = datetime.now(tz=UTC)
            if row is None:
                row = InternalEngineConfigModel(id=1, updated_at=now)
                session.add(row)
            row.model = model
            if curate_owner_machine_id is not None:
                # The empty string clears it back to "wherever this is read".
                row.curate_owner_machine_id = curate_owner_machine_id or None
            for name, setting in (upkeep or {}).items():
                enabled_col, interval_col = _UPKEEP_COLUMNS[name]
                setattr(row, enabled_col, setting.enabled)
                setattr(row, interval_col, setting.interval_s)
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return self._to_domain(row, now)

    async def set_model_timeout(self, seconds: int | None) -> GlobalInternalEngineConfig:
        """Write only the timeout column. ``None`` restores the built-in default."""
        return await self._set_one("model_timeout_s", seconds)

    async def set_transcribe_model(self, model: str | None) -> GlobalInternalEngineConfig:
        """Write only the transcription model. ``None`` stops transcription."""
        return await self._set_one("transcribe_model", model)

    async def set_curation_owner(self, machine_id: str | None) -> GlobalInternalEngineConfig:
        """Write only the curation owner. ``None`` clears it.

        A setter of its own rather than a flag on ``set``, which rewrites the
        model along with everything else — and because ``None`` has to mean
        *clear* here. ``set`` reads it as "leave alone" and takes the empty
        string for clear; that sentinel is right where the caller is restating
        a whole config and wrong where the caller's entire subject is this one
        field.
        """
        return await self._set_one("curate_owner_machine_id", machine_id)

    async def _set_one(self, column: str, value: object) -> GlobalInternalEngineConfig:
        """Read-modify-write ONE column of the singleton.

        One column per write rather than a whole-config update: this row
        converges through vault sync, so an update restating fields the caller
        never looked at is a lost update waiting for the moment the operator
        changes two settings on two machines. The same reasoning as
        ``set_upkeep``'s one-pass-per-write.
        """
        async with self._sm() as session:
            stmt = select(InternalEngineConfigModel).where(InternalEngineConfigModel.id == 1)
            row = (await session.execute(stmt)).scalar_one_or_none()
            now = datetime.now(tz=UTC)
            if row is None:
                row = InternalEngineConfigModel(id=1, updated_at=now)
                session.add(row)
            setattr(row, column, value)
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return self._to_domain(row, now)

    @staticmethod
    def _to_domain(
        row: InternalEngineConfigModel, updated_at: datetime
    ) -> GlobalInternalEngineConfig:
        return GlobalInternalEngineConfig(
            model=row.model,
            updated_at=updated_at,
            auto_curate_enabled=bool(row.auto_curate_enabled),
            curate_owner_machine_id=row.curate_owner_machine_id,
            auto_aggregate_enabled=bool(row.auto_aggregate_enabled),
            aggregate_interval_s=row.aggregate_interval_s,
            auto_distil_enabled=bool(row.auto_distil_enabled),
            distil_interval_s=row.distil_interval_s,
            curate_interval_s=row.curate_interval_s,
            model_timeout_s=row.model_timeout_s,
            transcribe_model=row.transcribe_model,
        )
