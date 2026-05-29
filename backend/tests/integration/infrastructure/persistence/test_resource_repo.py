from datetime import UTC, datetime

import pytest

from coffer.domain.errors import ResourceAlreadyExists
from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyResourceRepo


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _make_resource(kind: str = "fake_kind", name: str = "t") -> Resource:
    return Resource(
        id=0,
        kind=kind,
        name=name,
        description=None,
        config={"key": "value"},
        enabled=True,
        created_at=_now(),
        updated_at=_now(),
    )


async def _repo(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlAlchemyResourceRepo(session_maker(engine)), engine


@pytest.mark.asyncio
async def test_create_then_find(tmp_path):
    repo, engine = await _repo(tmp_path)
    created = await repo.create(_make_resource())
    assert created.id != 0
    found = await repo.find(ResourceRef("fake_kind", "t"))
    assert found is not None
    assert found.kind == "fake_kind"
    assert found.name == "t"
    assert found.config == {"key": "value"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_find_missing(tmp_path):
    repo, engine = await _repo(tmp_path)
    assert await repo.find(ResourceRef("fake_kind", "nope")) is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_duplicate_raises(tmp_path):
    repo, engine = await _repo(tmp_path)
    await repo.create(_make_resource())
    with pytest.raises(ResourceAlreadyExists):
        await repo.create(_make_resource())
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_all_and_by_kind(tmp_path):
    repo, engine = await _repo(tmp_path)
    await repo.create(_make_resource(kind="fake_kind", name="a"))
    await repo.create(_make_resource(kind="fake_kind", name="b"))
    await repo.create(_make_resource(kind="other_kind", name="c"))
    all_resources = await repo.list()
    assert {r.name for r in all_resources} == {"a", "b", "c"}
    fake_only = await repo.list(kind="fake_kind")
    assert {r.name for r in fake_only} == {"a", "b"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_config(tmp_path):
    repo, _engine = await _repo(tmp_path)
    await repo.create(_make_resource())
    updated = await repo.update_config(
        ResourceRef("fake_kind", "t"),
        config={"new": "value"},
        description="now with description",
    )
    assert updated.config == {"new": "value"}
    assert updated.description == "now with description"


@pytest.mark.asyncio
async def test_set_enabled(tmp_path):
    repo, _engine = await _repo(tmp_path)
    await repo.create(_make_resource())
    disabled = await repo.set_enabled(ResourceRef("fake_kind", "t"), False)
    assert disabled.enabled is False
    enabled = await repo.set_enabled(ResourceRef("fake_kind", "t"), True)
    assert enabled.enabled is True


@pytest.mark.asyncio
async def test_delete(tmp_path):
    repo, _engine = await _repo(tmp_path)
    await repo.create(_make_resource())
    await repo.delete(ResourceRef("fake_kind", "t"))
    assert await repo.find(ResourceRef("fake_kind", "t")) is None
    # delete is idempotent
    await repo.delete(ResourceRef("fake_kind", "t"))


@pytest.mark.asyncio
async def test_config_round_trip_through_json(tmp_path):
    repo, engine = await _repo(tmp_path)
    nested = {"transport": {"type": "stdio", "args": ["a", "b"]}, "ttl": 30}
    await repo.create(_make_resource())
    await repo.update_config(ResourceRef("fake_kind", "t"), config=nested, description=None)
    found = await repo.find(ResourceRef("fake_kind", "t"))
    assert found is not None
    assert found.config == nested
    await engine.dispose()
