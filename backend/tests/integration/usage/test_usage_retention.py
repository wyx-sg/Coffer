"""Usage retention: the detail follows the MCP-calls window; rollups keep a year."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from coffer.application.audit_service import AuditService
from coffer.application.retention_registry import PrunableRegistry, PrunableTable
from coffer.application.retention_service import RetentionService
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.persistence.retention_repo import (
    FileRetentionRepo,
    allowlist_from_registry,
)
from coffer.infrastructure.persistence.usage_models import UsageDailyModel, UsageRequestModel
from coffer.infrastructure.persistence.usage_repo import SqlAlchemyUsageRepo
from coffer.surfaces.http.app_mcp_composition import build_prunable_registry

from .conftest import record

_NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _retention(sm) -> RetentionService:  # type: ignore[no-untyped-def]
    registry = build_prunable_registry()
    return RetentionService(
        registry=registry,
        repo=FileRetentionRepo(sm, allowlist=allowlist_from_registry(registry.all())),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )


async def _seed(sm) -> None:  # type: ignore[no-untyped-def]
    from coffer.application.usage.ports import PricedRecord

    rows = [
        PricedRecord(
            record(1, started_at=_NOW - timedelta(days=40)), "2026-08-21", 0.1, None, False
        ),
        PricedRecord(
            record(2, started_at=_NOW - timedelta(days=1)), "2026-09-29", 0.1, None, False
        ),
    ]
    await SqlAlchemyUsageRepo(sm).ingest(rows)
    async with sm() as s:
        await s.execute(
            text(
                "INSERT INTO usage_daily (day, agent_uid, agent_type, connection_uid, model, "
                "requests, unknown_requests, unpriced_requests, input_tokens, "
                "cache_write_5m_tokens, cache_write_1h_tokens, cache_read_tokens, "
                "output_tokens, reasoning_tokens, web_search_requests, cost_usd) VALUES "
                "('2025-06-01', '', '', '', 'old', 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)"
            )
        )
        await s.commit()


async def _keys(sm, model) -> set[str]:  # type: ignore[no-untyped-def]
    async with sm() as s:
        col = model.dedupe_key if model is UsageRequestModel else model.day
        return set((await s.execute(select(col))).scalars().all())


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="request detail follows the MCP calls window",
)
async def test_request_detail_follows_the_mcp_calls_window(sm) -> None:  # type: ignore[no-untyped-def]
    svc = _retention(sm)
    await svc.initialize_defaults()
    names = {v.name for v in await svc.list_policies()}
    assert "usage_daily" in names
    assert "usage_requests" not in names  # a follower lists no policy of its own
    await _seed(sm)

    result = await svc.prune("mcp_invocations", now=_NOW)  # 30-day default
    assert result["usage_requests"] == 1
    assert await _keys(sm, UsageRequestModel) == {"req_2"}

    # The whole pass prunes the year-old rollup row too.
    result = await svc.prune(now=_NOW)
    assert result["usage_daily"] == 1
    assert "2025-06-01" not in await _keys(sm, UsageDailyModel)

    with pytest.raises(Exception, match="follows"):
        await svc.set_retention("usage_requests", 5, actor="test")


async def test_follower_uses_the_leaders_changed_window(sm) -> None:  # type: ignore[no-untyped-def]
    svc = _retention(sm)
    await svc.initialize_defaults()
    await _seed(sm)
    await svc.set_retention("mcp_invocations", None, actor="test")  # keep forever
    assert (await svc.prune(now=_NOW))["usage_requests"] == 0
    assert await _keys(sm, UsageRequestModel) == {"req_1", "req_2"}


def test_a_follower_must_name_a_registered_policy() -> None:
    registry = PrunableRegistry()
    with pytest.raises(ValueError, match="not a registered policy"):
        registry.register(
            PrunableTable(
                name="x",
                timestamp_column="t",
                default_retention_days=None,
                display_name="X",
                description="",
                policy_name="nope",
            )
        )
