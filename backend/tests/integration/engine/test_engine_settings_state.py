"""The engine's settings row as other code reads it (spec internal-engine).

Real ``InternalEngineConfigService`` over the real SQLAlchemy repo and a SQLite
file under ``tmp_path``: the synced state area that carries the row between
machines, and the unattended workers that read their switch and interval from
it while they run.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.engine_settings_sync import DOC, EngineSettingsSyncState
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.memory.aggregate_worker import AggregateWorker
from coffer.application.upkeep_schedule import wait_for_next_pass
from coffer.domain.internal_engine_config import AGGREGATE, CURATE, DISTIL, UpkeepSetting
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyInternalEngineConfigRepo,
)


@dataclass
class _Machine:
    service: InternalEngineConfigService
    area: EngineSettingsSyncState
    audit: AuditService


@pytest.fixture
async def machine(tmp_path: pathlib.Path) -> AsyncIterator[_Machine]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    repo = SqlAlchemyInternalEngineConfigRepo(sm)
    service = InternalEngineConfigService(repo=repo, audit=audit)
    yield _Machine(service, EngineSettingsSyncState(service, internal_repo=repo), audit)
    await engine.dispose()


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="a machine holding the defaults publishes no settings document",
)
async def test_the_defaults_publish_nothing_and_a_choice_publishes_one_document(
    machine: _Machine,
) -> None:
    # Never written.
    assert await machine.area.export_docs() == []

    # Written, but back to the defaults: the same decision as no row.
    await machine.service.update(model="m", actor="api")
    await machine.service.update(model=None, actor="api")
    await machine.service.set_upkeep(CURATE, UpkeepSetting(enabled=True), actor="api")
    assert await machine.area.export_docs() == []

    await machine.service.update(model="brain", actor="api")
    docs = await machine.area.export_docs()
    assert [path for path, _ in docs] == [DOC]
    assert docs[0][1]["model"] == "brain"


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="a document missing a key leaves this machine's value alone",
)
async def test_an_omitted_key_is_an_older_machine_and_an_explicit_null_is_a_decision(
    machine: _Machine,
) -> None:
    await machine.service.set_upkeep(DISTIL, UpkeepSetting(enabled=False, interval_s=900))
    await machine.service.set_model_timeout(120)
    await machine.service.set_transcribe_model("hears")

    errors = await machine.area.import_docs([(DOC, {"model": "from-elsewhere"})])
    assert errors == []
    held = await machine.service.get()
    assert held.model == "from-elsewhere"
    assert held.upkeep(DISTIL) == UpkeepSetting(enabled=False, interval_s=900)
    assert held.model_timeout_s == 120
    assert held.transcribe_model == "hears"

    errors = await machine.area.import_docs(
        [(DOC, {"model": "from-elsewhere", "model_timeout_s": None, "transcribe_model": None})]
    )
    assert errors == []
    held = await machine.service.get()
    assert held.model_timeout_s is None
    assert held.transcribe_model is None
    assert held.upkeep(DISTIL) == UpkeepSetting(enabled=False, interval_s=900)


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="deleting the settings document resets this machine to the defaults",
)
async def test_a_deleted_document_resets_every_setting_audited_as_sync(
    machine: _Machine,
) -> None:
    await machine.service.update(model="brain", actor="api")
    await machine.service.set_upkeep(CURATE, UpkeepSetting(enabled=False, interval_s=600))
    await machine.service.set_model_timeout(200)
    await machine.service.set_transcribe_model("hears")

    await machine.area.delete_docs([f"{DOC}"])

    held = await machine.service.get()
    assert held.model is None
    assert held.model_timeout_s is None
    assert held.transcribe_model is None
    for name in (AGGREGATE, DISTIL, CURATE):
        assert held.upkeep(name) == UpkeepSetting(enabled=True, interval_s=None)

    entries = await machine.audit.query(event_type="internal_engine_model_set", limit=50)
    sync_entries = [e for e in entries if e.actor == "sync"]
    assert len(sync_entries) >= 1
    assert await machine.area.export_docs() == []


def _enabled(service: InternalEngineConfigService, name: str):  # type: ignore[no-untyped-def]
    async def read() -> bool:
        return (await service.get()).upkeep(name).enabled

    return read


def _interval(service: InternalEngineConfigService, name: str):  # type: ignore[no-untyped-def]
    async def read() -> int | None:
        return (await service.get()).upkeep(name).interval_s

    return read


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="a running worker picks up a changed switch and interval",
)
async def test_a_running_worker_follows_the_row_without_being_rebuilt(
    machine: _Machine,
) -> None:
    passes: list[str] = []

    async def aggregate(*, actor: str) -> None:
        passes.append(actor)

    worker = AggregateWorker(
        aggregate=aggregate,
        is_enabled=_enabled(machine.service, AGGREGATE),
        read_interval=_interval(machine.service, AGGREGATE),
    )
    await worker.run_once()
    assert len(passes) == 1

    await machine.service.set_upkeep(AGGREGATE, UpkeepSetting(enabled=False))
    await worker.run_once()
    assert len(passes) == 1  # switched off: the same worker skips the pass

    # A wait already in progress at a 3600s interval ends at the new 120s one.
    await machine.service.set_upkeep(AGGREGATE, UpkeepSetting(enabled=True, interval_s=3600))
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) == 2:
            await machine.service.set_upkeep(AGGREGATE, UpkeepSetting(enabled=True, interval_s=120))

    await wait_for_next_pass(
        _interval(machine.service, AGGREGATE), default_s=3600.0, slice_s=30.0, sleep=sleep
    )
    assert sum(slept) == 120.0
