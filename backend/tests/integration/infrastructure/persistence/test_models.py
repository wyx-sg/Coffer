from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.internal_engine_repo import VaultInternalEngineConfigRepo
from coffer.infrastructure.persistence.models import AuditLogModel
from coffer.infrastructure.vault.instance import vault_repository


def _now() -> datetime:
    return datetime.now(tz=UTC)


@pytest.mark.asyncio
async def test_audit_log_round_trip(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    async with sm() as s:
        s.add(
            AuditLogModel(
                timestamp=_now(),
                event_type="resource_created",
                resource_kind="mcp_server",
                resource_name="filesystem",
                resource_uid="aa11bb22cc33dd44ee55ff6677889900",
                actor="cli",
                details_json='{"config": {}}',
            )
        )
        await s.commit()
    async with sm() as s:
        row = (await s.execute(select(AuditLogModel))).scalar_one()
    assert row.event_type == "resource_created"
    assert row.resource_uid == "aa11bb22cc33dd44ee55ff6677889900"
    await engine.dispose()


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="a second engine settings document is unrepresentable",
)
@pytest.mark.asyncio
async def test_internal_engine_config_refuses_a_second_row() -> None:
    """ "Which settings does the engine use?" must not become a question with
    two answers — the settings are one vault document at one fixed path, so
    every write rewrites it rather than adding a second."""
    repo = VaultInternalEngineConfigRepo()
    await repo.set_transcribe_model("whisper-1")
    await repo.set_transcribe_model("whisper-2")
    assert list(vault_repository().tree("HEAD", "state/settings/")) == [
        "state/settings/internal-engine.json"
    ]
    got = await repo.get()
    assert got is not None and got.transcribe_model == "whisper-2"
