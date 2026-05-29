import pytest
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    ConfigValidationError,
    ResourceAlreadyExists,
    ResourceNotFound,
    UnknownKind,
)
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
    foo: int
    bar: str = "default"


async def _service(tmp_path, *, kinds=None, on_delete=None):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    if kinds is None:
        kinds = {
            "fake_kind": Kind(
                name="fake_kind",
                display_name="Fake Kind",
                config_schema=_FakeConfig,
                on_delete=on_delete,
            ),
        }
    repo = SqlAlchemyResourceRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    return ResourceService(kinds=kinds, repo=repo, audit=audit), audit, engine


@pytest.mark.asyncio
async def test_register_persists_and_audits(tmp_path):
    svc, audit, engine = await _service(tmp_path)
    r = await svc.register(
        kind="fake_kind",
        name="t",
        config={"foo": 1, "bar": "hello"},
        description="test resource",
        actor="cli",
    )
    assert r.id != 0
    assert r.kind == "fake_kind"
    assert r.config == {"foo": 1, "bar": "hello"}
    assert r.enabled is True

    # Audit recorded
    entries = await audit.query(event_type=AuditEventType.RESOURCE_CREATED.value)
    assert len(entries) == 1
    assert entries[0].resource_kind == "fake_kind"
    assert entries[0].resource_name == "t"
    assert entries[0].actor == "cli"
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_validates_via_schema(tmp_path):
    svc, _, engine = await _service(tmp_path)
    with pytest.raises(ConfigValidationError):
        await svc.register(
            kind="fake_kind",
            name="t",
            config={"foo": "not_an_int"},
            actor="cli",
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_unknown_kind_raises(tmp_path):
    svc, _, engine = await _service(tmp_path)
    with pytest.raises(UnknownKind):
        await svc.register(kind="nope", name="x", config={}, actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_duplicate_raises(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    with pytest.raises(ResourceAlreadyExists):
        await svc.register(kind="fake_kind", name="t", config={"foo": 2}, actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_and_get(tmp_path):
    svc, _, engine = await _service(tmp_path)
    await svc.register(kind="fake_kind", name="a", config={"foo": 1}, actor="cli")
    await svc.register(kind="fake_kind", name="b", config={"foo": 2}, actor="cli")

    all_resources = await svc.list()
    assert {r.name for r in all_resources} == {"a", "b"}

    r = await svc.get(ResourceRef("fake_kind", "a"))
    assert r.config == {"foo": 1, "bar": "default"}

    with pytest.raises(ResourceNotFound):
        await svc.get(ResourceRef("fake_kind", "nope"))
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_config_audits_with_before_after(tmp_path):
    svc, audit, engine = await _service(tmp_path)
    await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    await svc.update_config(
        ResourceRef("fake_kind", "t"),
        new_config={"foo": 2, "bar": "different"},
        actor="api",
        description="changed",
    )
    entries = await audit.query(event_type=AuditEventType.RESOURCE_UPDATED.value)
    assert len(entries) == 1
    assert entries[0].actor == "api"
    assert entries[0].details["before"] == {"foo": 1, "bar": "default"}
    assert entries[0].details["after"] == {"foo": 2, "bar": "different"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_set_enabled_is_idempotent_and_audits_only_on_change(tmp_path):
    svc, audit, engine = await _service(tmp_path)
    await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")

    # idempotent: enabling an already-enabled resource doesn't audit
    await svc.set_enabled(ResourceRef("fake_kind", "t"), True, actor="api")
    enabled_events = await audit.query(event_type=AuditEventType.RESOURCE_ENABLED.value)
    assert len(enabled_events) == 0

    await svc.set_enabled(ResourceRef("fake_kind", "t"), False, actor="api")
    disabled_events = await audit.query(event_type=AuditEventType.RESOURCE_DISABLED.value)
    assert len(disabled_events) == 1
    assert disabled_events[0].actor == "api"
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_invokes_on_delete_hook_and_audits(tmp_path):
    calls: list[ResourceRef] = []
    svc, audit, engine = await _service(tmp_path, on_delete=lambda ref: calls.append(ref))
    await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    await svc.delete(ResourceRef("fake_kind", "t"), actor="cli")
    assert calls == [ResourceRef("fake_kind", "t")]
    assert await svc.list() == []

    entries = await audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert len(entries) == 1
    assert entries[0].details.get("snapshot") is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_aborts_when_on_delete_raises(tmp_path):
    def boom(ref: ResourceRef) -> None:
        raise RuntimeError("cleanup failed")

    svc, audit, engine = await _service(tmp_path, on_delete=boom)
    await svc.register(kind="fake_kind", name="t", config={"foo": 1}, actor="cli")
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await svc.delete(ResourceRef("fake_kind", "t"), actor="cli")

    # Resource still exists
    r = await svc.get(ResourceRef("fake_kind", "t"))
    assert r.name == "t"
    # No deletion audit entry
    entries = await audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert entries == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_unknown_resource_raises(tmp_path):
    svc, _, engine = await _service(tmp_path)
    with pytest.raises(ResourceNotFound):
        await svc.delete(ResourceRef("fake_kind", "nope"), actor="cli")
    await engine.dispose()
