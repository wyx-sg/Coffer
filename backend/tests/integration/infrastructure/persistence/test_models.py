from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.models import (
    AuditLogModel,
    ResourceModel,
    RetentionPolicyModel,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


@pytest.mark.asyncio
async def test_resource_model_round_trip(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    async with sm() as s:
        s.add(
            ResourceModel(
                kind="fake_kind",
                name="t",
                description=None,
                config_json="{}",
                enabled=True,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await s.commit()
    async with sm() as s:
        row = (await s.execute(select(ResourceModel))).scalar_one()
    assert row.kind == "fake_kind"
    assert row.name == "t"
    assert row.enabled is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_resource_unique_kind_name(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    async with sm() as s:
        s.add(
            ResourceModel(
                kind="fake_kind",
                name="t",
                description=None,
                config_json="{}",
                enabled=True,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await s.commit()

    import sqlalchemy.exc

    async with sm() as s:
        s.add(
            ResourceModel(
                kind="fake_kind",
                name="t",
                description=None,
                config_json="{}",
                enabled=True,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await s.commit()
    await engine.dispose()


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
                actor="cli",
                details_json='{"config": {}}',
            )
        )
        await s.commit()
    async with sm() as s:
        row = (await s.execute(select(AuditLogModel))).scalar_one()
    assert row.event_type == "resource_created"
    await engine.dispose()


@pytest.mark.asyncio
async def test_retention_policy_check_constraint(tmp_path):
    """retention_days=0 is forbidden by the CHECK constraint."""
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    import sqlalchemy.exc

    async with sm() as s:
        s.add(
            RetentionPolicyModel(
                table_name="audit_log",
                retention_days=0,
                last_pruned_at=None,
                last_pruned_rows=0,
                updated_at=_now(),
            )
        )
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await s.commit()

    async with sm() as s:
        s.add(
            RetentionPolicyModel(
                table_name="audit_log",
                retention_days=None,
                last_pruned_at=None,
                last_pruned_rows=0,
                updated_at=_now(),
            )
        )
        await s.commit()

    async with sm() as s:
        row = (await s.execute(select(RetentionPolicyModel))).scalar_one()
    assert row.retention_days is None
    await engine.dispose()
