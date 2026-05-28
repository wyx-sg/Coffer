"""TEST-015 — make_mcp_kind.on_delete evicts active supervisor sessions.

When the user deletes an MCP server resource, every session that has a
live subprocess for that name must lose it so the next call doesn't hit a
stale connection.  This wires a real ResourceService + a fake supervisor
and asserts evict() lands.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.resource_service import ResourceService
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)


class _RecordingSupervisor:
    """Captures every evict() call so we can assert the delete hook fired."""

    def __init__(self) -> None:
        self.evicted: list[str] = []

    async def evict(self, name: str) -> None:
        self.evicted.append(name)


@pytest.mark.asyncio
async def test_delete_evicts_active_supervisor_sessions(tmp_path: Path) -> None:
    """Deleting an mcp_server resource must trigger on_delete, which
    schedules an async evict against every registered supervisor.
    """
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    repo = SqlAlchemyResourceRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))

    # Wire a real Kind whose on_delete is the production hook.
    sup_a = _RecordingSupervisor()
    sup_b = _RecordingSupervisor()
    supervisor_for: dict[str, object] = {"session-a": sup_a, "session-b": sup_b}
    mcp_kind = make_mcp_kind(supervisor_for)  # type: ignore[arg-type]

    rsvc = ResourceService(
        kinds={"mcp_server": mcp_kind},
        repo=repo,
        audit=audit,
    )

    await rsvc.register(
        kind="mcp_server",
        name="fs",
        config={
            "transport": {
                "type": "stdio",
                "command": "/bin/true",
                "args": [],
            }
        },
        actor="test",
    )

    # Delete the resource — the kind hook is invoked synchronously, and it
    # schedules an asyncio.create_task to evict against every supervisor.
    await rsvc.delete(ResourceRef("mcp_server", "fs"), actor="test")

    # Yield long enough for the fire-and-forget task to complete.  Several
    # event-loop ticks are fine because the eviction itself is in-memory.
    for _ in range(20):
        await asyncio.sleep(0)
        if sup_a.evicted and sup_b.evicted:
            break

    assert sup_a.evicted == ["fs"], f"session-a never received evict: {sup_a.evicted}"
    assert sup_b.evicted == ["fs"], f"session-b never received evict: {sup_b.evicted}"

    await engine.dispose()


@pytest.mark.asyncio
async def test_on_delete_is_a_noop_outside_event_loop() -> None:
    """When `make_mcp_kind.on_delete` runs with no event loop (sync CLI
    delete path), it returns silently without raising.  Pinned because the
    only mechanism preventing a crash is `asyncio.get_running_loop()`
    raising RuntimeError, which is platform-stable but worth a guard test.
    """
    supervisor_for: dict[str, object] = {}
    mcp_kind = make_mcp_kind(supervisor_for)  # type: ignore[arg-type]

    def _sync_call() -> None:
        # Inside an event loop here — but the on_delete fn is sync, and we
        # want to assert the no-running-loop branch.  Use a thread for that.
        mcp_kind.on_delete(ResourceRef("mcp_server", "anything"))  # type: ignore[misc]

    import threading

    captured: dict[str, Exception | None] = {"exc": None}

    def _runner() -> None:
        try:
            _sync_call()
        except Exception as e:
            captured["exc"] = e

    t = threading.Thread(target=_runner)
    t.start()
    t.join()
    assert captured["exc"] is None, f"on_delete raised: {captured['exc']!r}"
