# backend/tests/integration/application/test_retention_service.py
from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.retention_registry import (
    FilePolicy,
    PrunableRegistry,
    PrunableTable,
    UnknownPrunableTable,
)
from coffer.application.retention_service import RetentionService
from coffer.domain.audit import AuditEventType
from coffer.infrastructure.chat import persistence_models as _chat_models  # noqa: F401
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.models import AuditLogModel
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.persistence.retention_repo import (
    FileRetentionRepo,
    allowlist_from_registry,
)


async def _service(tmp_path, *, extra_tables=()):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    registry = PrunableRegistry()
    registry.register(
        PrunableTable(
            name="audit_log",
            timestamp_column="timestamp",
            default_retention_days=365,
            display_name="Audit Log",
            description="Resource lifecycle events.",
        )
    )
    for t in extra_tables:
        registry.register(t)
    repo = FileRetentionRepo(sm, allowlist=allowlist_from_registry(registry.all()))
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    return RetentionService(registry=registry, repo=repo, audit=audit), sm, engine


@pytest.mark.asyncio
async def test_initialize_defaults_seeds_policies(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.initialize_defaults()
    policies = await svc.list_policies()
    names = {p.name for p in policies}
    assert names == {"audit_log"}
    p = policies[0]
    assert p.retention_days == 365
    await engine.dispose()


@pytest.mark.asyncio
async def test_initialize_defaults_is_idempotent(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.initialize_defaults()
    await svc.set_retention("audit_log", 180, actor="cli")
    await svc.initialize_defaults()  # should NOT overwrite
    policies = await svc.list_policies()
    assert policies[0].retention_days == 180
    await engine.dispose()


@pytest.mark.acceptance(spec="resource-framework", scenario="configure retention per log")
@pytest.mark.asyncio
async def test_set_retention_audits(tmp_path):
    svc, sm, engine = await _service(tmp_path)
    await svc.initialize_defaults()
    await svc.set_retention("audit_log", 180, actor="api")
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    entries = await audit.query(event_type=AuditEventType.RETENTION_UPDATED.value)
    assert len(entries) == 1
    # The window it replaced too (the default, 365 days).
    assert entries[0].details == {
        "table": "audit_log",
        "retention_days": 180,
        "previous_days": 365,
    }
    assert entries[0].actor == "api"
    await engine.dispose()


@pytest.mark.asyncio
async def test_set_retention_forever(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.initialize_defaults()
    await svc.set_retention("audit_log", None, actor="cli")
    policies = await svc.list_policies()
    assert policies[0].retention_days is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_set_retention_rejects_zero_and_negative(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.initialize_defaults()
    with pytest.raises(ValueError):
        await svc.set_retention("audit_log", 0, actor="cli")
    with pytest.raises(ValueError):
        await svc.set_retention("audit_log", -5, actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_set_retention_unknown_table_rejected(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.initialize_defaults()
    with pytest.raises(UnknownPrunableTable):
        await svc.set_retention("nope", 30, actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_prune_deletes_older_rows_and_records_to_policy(tmp_path):
    svc, sm, engine = await _service(tmp_path)
    await svc.initialize_defaults()
    await svc.set_retention("audit_log", 7, actor="system")  # 7-day retention

    now = datetime(2026, 5, 20, tzinfo=UTC)
    async with sm() as s:
        for i in range(5):
            s.add(
                AuditLogModel(
                    timestamp=now - timedelta(days=i * 5),  # 0, 5, 10, 15, 20 days old
                    event_type="resource_created",
                    resource_kind="mcp_server",
                    resource_name=f"r{i}",
                    actor="cli",
                    details_json=None,
                )
            )
        await s.commit()

    result = await svc.prune(now=now)
    assert result == {"audit_log": 3}  # 3 rows older than 7 days (i=2,3,4 at 10/15/20 days)

    policies = await svc.list_policies()
    assert policies[0].last_pruned_rows == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_prune_skips_forever_retention(tmp_path):
    svc, sm, engine = await _service(tmp_path)
    await svc.initialize_defaults()
    await svc.set_retention("audit_log", None, actor="cli")

    async with sm() as s:
        s.add(
            AuditLogModel(
                timestamp=datetime(1999, 1, 1, tzinfo=UTC),
                event_type="resource_created",
                resource_kind="mcp_server",
                resource_name="ancient",
                actor="cli",
                details_json=None,
            )
        )
        await s.commit()

    result = await svc.prune()
    assert result == {"audit_log": 0}  # not pruned
    await engine.dispose()


@pytest.mark.asyncio
async def test_prune_single_table_only(tmp_path):
    svc, _sm, engine = await _service(
        tmp_path,
        extra_tables=(
            PrunableTable(
                name="mcp_invocations",
                timestamp_column="timestamp",
                default_retention_days=30,
                display_name="MCP Invocations",
                description="…",
            ),
        ),
    )
    await svc.initialize_defaults()
    # Only audit_log gets explicit pruning; mcp_invocations table doesn't
    # exist in the create_all schema so we can't actually prune it.
    # The service should NOT touch tables not asked for.
    result = await svc.prune(table_name="audit_log")
    assert "audit_log" in result
    assert "mcp_invocations" not in result
    await engine.dispose()


@pytest.mark.asyncio
async def test_prune_unknown_table_rejected(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.initialize_defaults()
    with pytest.raises(UnknownPrunableTable):
        await svc.prune(table_name="nope")
    await engine.dispose()


@pytest.mark.acceptance(
    spec="chat", scenario="the upgrade drops the text and keeps channel conversations"
)
@pytest.mark.asyncio
async def test_initialize_defaults_forgets_the_rows_of_retired_policies(tmp_path):
    """A policy the registry no longer holds (the conversation archive/delete pair)
    leaves its row in ``local/retention.json``; the next start drops it."""
    svc, _sm, engine = await _service(tmp_path)
    await svc._repo.upsert("conversations", 30)
    await svc._repo.upsert("conversations_archive", 7)

    await svc.initialize_defaults()

    assert {p.table_name for p in await svc._repo.list()} == {"audit_log"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_full_prune_runs_the_attachment_sweeps_with_the_stored_window(tmp_path):
    """The attachments policy sweeps both dirs with its stored window; a sweep
    that raises is logged and skipped, and neither the table prune nor the other
    sweep is lost. A single-table prune runs no attachment sweep."""
    service, _sm, engine = await _service(tmp_path)
    calls: list[tuple[str, int]] = []

    def _broken(now: datetime, days: int) -> list[str]:
        calls.append(("broken", days))
        raise OSError("disk went away")

    def _two(now: datetime, days: int) -> list[str]:
        calls.append(("two", days))
        return ["a", "b"]

    service = RetentionService(
        registry=service._registry,
        repo=service._repo,
        audit=service._audit,
        file_policies=[
            FilePolicy(
                name="attachments",
                display_name="Attachments",
                description="files",
                default_retention_days=30,
                sweeps=(_broken, _two),
                count=lambda now, days: (10, 4),
            )
        ],
    )
    await service.initialize_defaults()

    full = await service.prune()
    assert full["attachments"] == 2
    assert "audit_log" in full
    assert calls == [("broken", 30), ("two", 30)]

    single = await service.prune("audit_log")
    assert set(single) == {"audit_log"}
    assert len(calls) == 2

    only = await service.prune("attachments")
    assert only == {"attachments": 2}

    await service.set_retention("attachments", 7, actor="t")
    assert await service.preview("attachments", 3) == (10, 4)
    calls.clear()
    await service.prune()
    assert calls == [("broken", 7), ("two", 7)]
    view = next(v for v in await service.list_policies() if v.name == "attachments")
    assert (view.retention_days, view.last_pruned_rows) == (7, 2)

    await service.set_retention("attachments", None, actor="t")
    calls.clear()
    assert (await service.prune())["attachments"] == 0
    assert calls == []
    await engine.dispose()
