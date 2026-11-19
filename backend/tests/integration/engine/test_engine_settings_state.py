"""The engine's settings document as other code reads it (spec internal-engine).

Real ``InternalEngineConfigService`` over the real vault-document repo in the
test's own HOME: the one document that carries the settings between machines
(``state/settings/internal-engine.json``).
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.internal_engine_config_service import InternalEngineConfigService
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
    doc["upkeep"] = {"memory_sync": {"enabled": False, "interval_s": 600}}
    doc["written_by_a_newer_build"] = {"kept": True}
    path.write_text(json.dumps(doc, indent=2) + "\n")
    vault_writer().settle([DOC])

    held = await machine.service.get()
    assert not hasattr(held, "model_timeout_s")
    assert held.transcribe_model == "hears"
    assert not hasattr(held, "model")
    assert not hasattr(held, "curate_owner_machine_id")
    assert not hasattr(held, "upkeep")

    await machine.service.set_transcribe_model("hears-2", actor="api")
    stored = json.loads(vault_writer().repo.read("HEAD", DOC) or b"{}")
    assert "model" not in stored
    assert "curate_owner_machine_id" not in stored
    assert "model_timeout_s" not in stored
    assert "upkeep" not in stored
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
    await machine.service.set_transcribe_model("hears")

    # Another machine's deletion, arriving as a commit.
    vault_writer().delete_file(
        DOC, meta=CommitMeta(writer=WRITER_SYNC, operation="sync", summary="merged")
    )

    held = await machine.service.get()
    assert held.transcribe_model is None

