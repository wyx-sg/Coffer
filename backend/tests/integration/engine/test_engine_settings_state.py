"""The engine's settings document as other code reads it (spec internal-engine).

Real ``InternalEngineConfigService`` over the real vault-document repo in the
test's own HOME: the one document that carries the settings between machines
(``state/settings/internal-engine.json``), and the unattended workers that
read their switch and interval from it while they run.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import pathlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.memory import sync_worker
from coffer.application.memory.sync_worker import MemorySyncWorker
from coffer.application.upkeep_schedule import wait_for_next_pass
from coffer.domain.internal_engine_config import MEMORY_SYNC, RETIRED_AGGREGATE, UpkeepSetting
from coffer.domain.vault.writers import WRITER_SYNC, CommitMeta
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.internal_engine_repo import VaultInternalEngineConfigRepo
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_repository, vault_writer

DOC = "state/settings/internal-engine.json"


@dataclass
class _Machine:
    service: InternalEngineConfigService
    repo: VaultInternalEngineConfigRepo
    audit: AuditService


@pytest.fixture
async def machine(tmp_path: pathlib.Path) -> AsyncIterator[_Machine]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    repo = VaultInternalEngineConfigRepo()
    service = InternalEngineConfigService(repo=repo, audit=audit)
    yield _Machine(service, repo, audit)
    await engine.dispose()


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="a machine holding the defaults publishes no settings document",
)
async def test_the_defaults_publish_nothing_and_a_choice_publishes_one_document(
    machine: _Machine,
) -> None:
    # Never written.
    assert vault_repository().tree("HEAD", "state/") == {}

    # Written, but back to the defaults: the same decision as no document.
    await machine.service.set_transcribe_model("hears", actor="api")
    await machine.service.set_transcribe_model(None, actor="api")
    await machine.service.set_upkeep(MEMORY_SYNC, UpkeepSetting(enabled=True), actor="api")
    assert vault_repository().tree("HEAD", "state/") == {}

    await machine.service.set_transcribe_model("hears", actor="api")
    assert list(vault_repository().tree("HEAD", "state/")) == [DOC]
    assert (await machine.service.get()).transcribe_model == "hears"


@pytest.mark.acceptance(
    spec="internal-engine", scenario="ignore retired keys when the settings are read"
)
@pytest.mark.acceptance(spec="internal-engine", scenario="drop retired keys on the next write")
async def test_keys_an_older_build_wrote_are_ignored_and_dropped_on_the_next_write(
    machine: _Machine,
) -> None:
    await machine.service.set_transcribe_model("hears", actor="api")
    path = vault_root() / DOC
    doc = json.loads(path.read_text())
    doc["model"] = "brain"
    doc["curate_owner_machine_id"] = "laptop-1"
    doc["model_timeout_s"] = 200
    doc["upkeep"]["curate"] = {"enabled": False, "interval_s": 600}
    doc["upkeep"]["distil"] = {"enabled": False, "interval_s": 600}
    doc["written_by_a_newer_build"] = {"kept": True}
    path.write_text(json.dumps(doc, indent=2) + "\n")
    vault_writer().settle([DOC])

    held = await machine.service.get()
    assert not hasattr(held, "model_timeout_s")
    assert held.transcribe_model == "hears"
    assert not hasattr(held, "model")
    assert not hasattr(held, "curate_owner_machine_id")
    assert held.upkeep(MEMORY_SYNC).enabled is True
    for retired in ("curate", "distil"):
        with pytest.raises(ValueError):
            held.upkeep(retired)

    await machine.service.set_transcribe_model("hears-2", actor="api")
    stored = json.loads(vault_writer().repo.read("HEAD", DOC) or b"{}")
    assert "model" not in stored
    assert "curate_owner_machine_id" not in stored
    assert "model_timeout_s" not in stored
    assert set(stored["upkeep"]) == {MEMORY_SYNC}
    assert stored["transcribe_model"] == "hears-2"
    assert stored["written_by_a_newer_build"] == {"kept": True}


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="deleting the settings document resets this machine to the defaults",
)
@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="the engine's settings converge and a deletion means the defaults",
)
async def test_a_deleted_document_resets_every_setting(machine: _Machine) -> None:
    await machine.service.set_upkeep(MEMORY_SYNC, UpkeepSetting(enabled=False, interval_s=600))
    await machine.service.set_transcribe_model("hears")

    # Another machine's deletion, arriving as a commit.
    vault_writer().delete_file(
        DOC, meta=CommitMeta(writer=WRITER_SYNC, operation="sync", summary="merged")
    )

    held = await machine.service.get()
    assert held.transcribe_model is None
    assert held.upkeep(MEMORY_SYNC) == UpkeepSetting(enabled=True, interval_s=None)


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
    machine: _Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``run_forever`` itself, on a virtual clock.

    The worker's own wait is the real ``wait_for_next_pass``; only its sleep is
    swapped for one that advances a counter, so an hour-long interval costs
    nothing. What the operator changes goes through the settings row while the
    worker's task is running, and the worker is never rebuilt.
    """
    now = 0.0
    passes: list[float] = []
    done = asyncio.Event()

    async def sync(actor: str) -> None:
        passes.append(now)

    async def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds
        # Operator actions, at virtual times inside the worker's waits.
        if now == 60.0:
            # Mid-way through the first wait, which started at a 3600s interval.
            await machine.service.set_upkeep(
                MEMORY_SYNC, UpkeepSetting(enabled=True, interval_s=120)
            )
        elif now == 150.0:
            # Inside the second wait: the pass is switched off.
            await machine.service.set_upkeep(
                MEMORY_SYNC, UpkeepSetting(enabled=False, interval_s=120)
            )
        elif now >= 300.0:
            done.set()
            await asyncio.Event().wait()  # park until cancelled
        await asyncio.sleep(0)

    monkeypatch.setattr(
        sync_worker,
        "wait_for_next_pass",
        functools.partial(wait_for_next_pass, slice_s=30.0, sleep=sleep),
    )
    await machine.service.set_upkeep(MEMORY_SYNC, UpkeepSetting(enabled=True, interval_s=3600))
    worker = MemorySyncWorker(
        sync=sync,
        is_enabled=_enabled(machine.service, MEMORY_SYNC),
        read_interval=_interval(machine.service, MEMORY_SYNC),
    )

    task = asyncio.create_task(worker.run_forever())
    try:
        await asyncio.wait_for(done.wait(), timeout=10)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # The catch-up pass at start; then the wait that began at 3600s ended at
    # the 120s set during it; then, switched off, the pass due at 240 did not run.
    assert passes == [0.0, 120.0]


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="an older build's aggregation switch carries over to the memory sync",
)
async def test_the_retired_aggregation_switch_becomes_the_memory_syncs(
    machine: _Machine,
) -> None:
    """A vault an older build wrote carries ``upkeep.aggregate`` and no
    ``upkeep.memory_sync``: the person's choice carries over, and the next
    write records it under the memory sync's own name."""
    await machine.service.set_transcribe_model("hears", actor="api")
    path = vault_root() / DOC
    doc = json.loads(path.read_text())
    doc["upkeep"] = {RETIRED_AGGREGATE: {"enabled": False, "interval_s": 900}}
    path.write_text(json.dumps(doc, indent=2) + "\n")
    vault_writer().settle([DOC])

    held = await machine.service.get()
    assert held.upkeep(MEMORY_SYNC) == UpkeepSetting(enabled=False, interval_s=900)

    await machine.service.set_transcribe_model("hears-2", actor="api")
    stored = json.loads(vault_writer().repo.read("HEAD", DOC) or b"{}")
    assert stored["upkeep"] == {MEMORY_SYNC: {"enabled": False, "interval_s": 900}}
