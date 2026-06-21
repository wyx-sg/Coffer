# backend/tests/integration/memory/test_journal_service.py
"""Integration: JournalService append/read_recent over a real store."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.memory.journal import JournalService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ScopeUnresolved
from coffer.infrastructure.knowledge import paths

pytestmark = pytest.mark.asyncio


def _svc(mem, *, now):
    return JournalService(
        scope=mem.scope, store_dir=paths.memory_store_dir, audit=mem.audit, now=now
    )


async def test_append_then_read_recent(mem) -> None:
    svc = _svc(mem, now=lambda: datetime(2026, 6, 21, 9, 0, tzinfo=UTC))
    await svc.append(cwd=mem.project_cwd, body="did X", actor="agent")
    got = await svc.read_recent(cwd=mem.project_cwd, limit=10)
    assert [e.body for e in got] == ["did X"]


async def test_read_recent_is_newest_first(mem) -> None:
    times = iter(
        [datetime(2026, 6, 21, 9, 0, tzinfo=UTC), datetime(2026, 6, 21, 10, 0, tzinfo=UTC)]
    )
    svc = JournalService(
        scope=mem.scope, store_dir=paths.memory_store_dir, audit=mem.audit, now=lambda: next(times)
    )
    await svc.append(cwd=mem.project_cwd, body="first", actor="agent")
    await svc.append(cwd=mem.project_cwd, body="second", actor="agent")
    got = await svc.read_recent(cwd=mem.project_cwd, limit=10)
    assert [e.body for e in got] == ["second", "first"]


async def test_append_outside_project_raises(mem) -> None:
    svc = _svc(mem, now=lambda: datetime(2026, 6, 21, tzinfo=UTC))
    with pytest.raises(ScopeUnresolved):
        await svc.append(cwd="/not/a/project", body="x", actor="agent")


async def test_read_recent_outside_project_returns_empty(mem) -> None:
    svc = _svc(mem, now=lambda: datetime(2026, 6, 21, tzinfo=UTC))
    assert await svc.read_recent(cwd="/not/a/project", limit=10) == []


async def test_append_audit_has_no_body(mem) -> None:
    svc = _svc(mem, now=lambda: datetime(2026, 6, 21, tzinfo=UTC))
    await svc.append(cwd=mem.project_cwd, body="SECRET payload", actor="agent")
    entries = await mem.audit.query(event_type=AuditEventType.JOURNAL_APPEND.value)
    assert len(entries) == 1
    assert "SECRET" not in str(entries[0].details)
    assert entries[0].details["char_size"] == len("SECRET payload")
