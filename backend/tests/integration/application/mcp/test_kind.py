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

    # Delete the resource — CODE-033: the kind hook is now an async hook that
    # ResourceService.delete AWAITS before removing the row, so eviction is
    # complete the instant delete() returns (no fire-and-forget polling).
    await rsvc.delete(ResourceRef("mcp_server", "fs"), actor="test")

    assert sup_a.evicted == ["fs"], f"session-a never received evict: {sup_a.evicted}"
    assert sup_b.evicted == ["fs"], f"session-b never received evict: {sup_b.evicted}"

    await engine.dispose()


@pytest.mark.asyncio
async def test_on_delete_awaitable_and_suppresses_supervisor_errors() -> None:
    """CODE-033: on_delete is an awaitable coroutine; awaiting it evicts every
    registered supervisor, and a single supervisor whose evict() raises is
    suppressed so it can't abort the others or the deletion.
    """

    class _Boom:
        async def evict(self, name: str) -> None:
            raise RuntimeError("boom")

    good = _RecordingSupervisor()
    supervisor_for: dict[str, object] = {"bad": _Boom(), "good": good}
    mcp_kind = make_mcp_kind(supervisor_for)  # type: ignore[arg-type]

    assert mcp_kind.on_delete is not None
    result = mcp_kind.on_delete(ResourceRef("mcp_server", "fs"))
    assert asyncio.iscoroutine(result), "on_delete must be an awaitable async hook"
    await result  # must not raise despite the failing supervisor

    assert good.evicted == ["fs"], "a failing supervisor must not block eviction of the rest"


def test_validate_name_rejects_double_underscore() -> None:
    """CODE-030: mcp_server names may not contain '__' (reserved separator)."""
    mcp_kind = make_mcp_kind({})  # type: ignore[arg-type]
    assert mcp_kind.validate_name is not None
    mcp_kind.validate_name("ok_name")  # single underscore is fine
    mcp_kind.validate_name("dotted.name-ok")
    with pytest.raises(ValueError, match="__"):
        mcp_kind.validate_name("my__server")
