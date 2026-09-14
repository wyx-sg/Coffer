"""ResourceService.update_scope end-to-end persistence (ADR per-agent-resource-scope).

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
async def test_kind_pre_validation_rejects_before_any_write(tmp_path):
    """``Kind.validate_scope_for`` is the scope path's counterpart to
    ``on_update_config``: the kind gets a say BEFORE persistence, so a rejected
    scope leaves the row — and the audit log — untouched."""
    seen: list[tuple[str, list[str] | None]] = []

    def _reject_b(resource, scope):
        seen.append((resource.name, scope))
        if scope and "agent-b" in scope:
            raise ValueError("agent-b may not have this")

    svc, audit, engine = await _service(
        tmp_path,
        kinds={
            "picky_kind": Kind(
                name="picky_kind",
                display_name="Picky Kind",
                config_schema=_FakeConfig,
                supports_scope=True,
                validate_scope_for=_reject_b,
            )
        },
    )
    await svc.register(kind="picky_kind", name="t", config={"foo": 1}, actor="cli")
    with pytest.raises(ScopeInvalidError, match="agent-b"):
        await svc.update_scope(ResourceRef("picky_kind", "t"), ["agent-b"], actor="cli")
    # The hook saw the resource as it still stands, and nothing was written.
    assert seen == [("t", ["agent-b"])]
    assert (await svc.get(ResourceRef("picky_kind", "t"))).scope is None
    assert await audit.query(event_type=AuditEventType.RESOURCE_SCOPE_UPDATED.value) == []

    # An acceptable scope still lands.
    updated = await svc.update_scope(ResourceRef("picky_kind", "t"), ["agent-a"], actor="cli")
    assert updated.scope == ["agent-a"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_kind_pre_validation_may_be_async(tmp_path):
    """Sync or async, exactly like ``on_update_config`` — the service awaits an
    awaitable hook result."""

    async def _reject(_resource, _scope):
        raise ValueError("never")

    svc, _, engine = await _service(
        tmp_path,
        kinds={
            "picky_kind": Kind(
                name="picky_kind",
                display_name="Picky Kind",
                config_schema=_FakeConfig,
                supports_scope=True,
                validate_scope_for=_reject,
            )
        },
    )
    await svc.register(kind="picky_kind", name="t", config={"foo": 1}, actor="cli")
    with pytest.raises(ScopeInvalidError, match="never"):
        await svc.update_scope(ResourceRef("picky_kind", "t"), ["agent-a"], actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_kind_with_no_pre_validation_hook_is_unaffected(tmp_path):
    """Every kind but `channel` supplies none, and must behave exactly as before
    the hook existed."""
    svc, _, engine = await _service(tmp_path)
    assert svc._require_kind("scoped_kind").validate_scope_for is None
    await svc.register(kind="scoped_kind", name="t", config={"foo": 1}, actor="cli")
    updated = await svc.update_scope(ResourceRef("scoped_kind", "t"), ["anything"], actor="cli")
    assert updated.scope == ["anything"]
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
