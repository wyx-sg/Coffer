"""ResourceService.update_scope end-to-end persistence (ADR-045).

Colocated with `test_resource_service.py` (no unit-level ResourceService test
module exists — the real ResourceService tests already run against a real
SQLite-backed `SqlAlchemyResourceRepo`, matching the `_service()` helper style
used there) so the update_scope round-trip is proven through the real repo.
"""

import pytest
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound, ScopeInvalidError
from coffer.domain.resource import Kind, ResourceRef
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)


class _FakeConfig(BaseModel):
    foo: int = 0


async def _service(tmp_path, *, kinds=None):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    if kinds is None:
        kinds = {
            "scoped_kind": Kind(
                name="scoped_kind",
                display_name="Scoped Kind",
                config_schema=_FakeConfig,
                supports_scope=True,
            ),
            "unscopable_kind": Kind(
                name="unscopable_kind",
                display_name="Unscopable Kind",
                config_schema=_FakeConfig,
            ),
            "lifecycle_kind": Kind(
                name="lifecycle_kind",
                display_name="Lifecycle Kind",
                config_schema=_FakeConfig,
                supports_scope=True,
                generic_create_allowed=False,
            ),
        }
    repo = SqlAlchemyResourceRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    return ResourceService(kinds=kinds, repo=repo, audit=audit), audit, engine


@pytest.mark.asyncio
async def test_register_keeps_scope_none(tmp_path):
    svc, _, engine = await _service(tmp_path)
    r = await svc.register(kind="scoped_kind", name="t", config={"foo": 1}, actor="cli")
    assert r.scope is None
    fetched = await svc.get(ResourceRef("scoped_kind", "t"))
    assert fetched.scope is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_scope_round_trips_agent_list_through_real_repo(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.register(kind="scoped_kind", name="t", config={"foo": 1}, actor="cli")
    agents = ["agent-a", "agent-b"]
    updated = await svc.update_scope(ResourceRef("scoped_kind", "t"), agents, actor="cli")
    assert updated.scope == agents

    # Persisted — a fresh read (new session under the hood) must see it too.
    fetched = await svc.get(ResourceRef("scoped_kind", "t"))
    assert fetched.scope == agents

    # The dormant scope ([]) round-trips distinctly from None.
    dormant = await svc.update_scope(ResourceRef("scoped_kind", "t"), [], actor="cli")
    assert dormant.scope == []
    assert (await svc.get(ResourceRef("scoped_kind", "t"))).scope == []

    # Clearing scope (back to unscoped) round-trips to None as well.
    cleared = await svc.update_scope(ResourceRef("scoped_kind", "t"), None, actor="cli")
    assert cleared.scope is None
    fetched_again = await svc.get(ResourceRef("scoped_kind", "t"))
    assert fetched_again.scope is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_scope_on_kind_without_scope_raises(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.register(kind="unscopable_kind", name="t", config={"foo": 1}, actor="cli")
    with pytest.raises(ScopeInvalidError):
        await svc.update_scope(ResourceRef("unscopable_kind", "t"), ["agent-a"], actor="cli")
    # Even the empty list is rejected — the kind carries no scope at all.
    with pytest.raises(ScopeInvalidError):
        await svc.update_scope(ResourceRef("unscopable_kind", "t"), [], actor="cli")
    # Rejected before any write — scope stays None.
    fetched = await svc.get(ResourceRef("unscopable_kind", "t"))
    assert fetched.scope is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_scope_records_audit_event(tmp_path):
    svc, audit, engine = await _service(tmp_path)
    await svc.register(kind="scoped_kind", name="t", config={"foo": 1}, actor="cli")
    scope = ["agent-a"]
    await svc.update_scope(ResourceRef("scoped_kind", "t"), scope, actor="api")
    entries = await audit.query(event_type=AuditEventType.RESOURCE_SCOPE_UPDATED.value)
    assert len(entries) == 1
    assert entries[0].resource_kind == "scoped_kind"
    assert entries[0].resource_name == "t"
    assert entries[0].actor == "api"
    assert entries[0].details["scope"] == scope
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_scope_unknown_ref_raises(tmp_path):
    svc, _, engine = await _service(tmp_path)
    with pytest.raises(ResourceNotFound):
        await svc.update_scope(ResourceRef("scoped_kind", "nope"), ["agent-a"], actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_scope_works_for_lifecycle_kind_without_opt_in(tmp_path):
    """update_scope must NOT be gated on allow_lifecycle_kind — the per-agent
    activation scope is a framework-level concern orthogonal to a kind's
    creation-invariant lockdown (a skill owns its creation but not its
    activation scoping)."""
    svc, _, engine = await _service(tmp_path)
    await svc.register(
        kind="lifecycle_kind",
        name="t",
        config={"foo": 1},
        actor="owning-service",
        allow_lifecycle_kind=True,
    )
    updated = await svc.update_scope(ResourceRef("lifecycle_kind", "t"), ["agent-a"], actor="cli")
    assert updated.scope == ["agent-a"]
    await engine.dispose()
