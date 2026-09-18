"""The repo addresses every row by its ``uid``.

The port used to take a ``(kind, name)`` pair, which made "address a resource
by its label" a rule of the persistence layer rather than a choice any one
surface made. ``find_by_name`` survives for the two jobs that genuinely start
from a label — resolving what a human typed, and enforcing the within-kind
uniqueness the label still has — and every mutation names the uid.
"""

from datetime import UTC, datetime

import pytest

from coffer.domain.errors import ResourceAlreadyExists
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyResourceRepo


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _make_resource(kind: str = "fake_kind", name: str = "t", *, uid: str | None = None) -> Resource:
    # The uid is minted by the caller (ResourceService) and handed to the repo;
    # the repo assigns only the integer surrogate key.
    return Resource(
        id=0,
        uid=uid or f"uid-{kind}-{name}",
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
    # The uid the caller minted survives the round trip untouched — the repo
    # never invents one and never rewrites one.
    assert created.uid == "uid-fake_kind-t"
    found = await repo.find(created.uid)
    assert found is not None
    assert found.kind == "fake_kind"
    assert found.name == "t"
    assert found.config == {"key": "value"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_find_missing(tmp_path):
    repo, engine = await _repo(tmp_path)
    assert await repo.find("no-such-uid") is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_find_by_name_is_the_label_lookup(tmp_path):
    """The one lookup that still starts from a label. It is how a human's input
    is resolved into a uid, and how the within-kind uniqueness of a name is
    checked — never a way to carry identity around."""
    repo, engine = await _repo(tmp_path)
    created = await repo.create(_make_resource())
    found = await repo.find_by_name("fake_kind", "t")
    assert found is not None
    assert found.uid == created.uid
    # Scoped to the kind: the same label in another kind is another resource.
    assert await repo.find_by_name("other_kind", "t") is None
    assert await repo.find_by_name("fake_kind", "nope") is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_duplicate_name_raises(tmp_path):
    """A distinct uid does not buy a second resource the same label: the name
    is still unique within its kind, because it is what a user reads."""
    repo, engine = await _repo(tmp_path)
    await repo.create(_make_resource())
    with pytest.raises(ResourceAlreadyExists):
        await repo.create(_make_resource(uid="a-different-uid"))
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
    created = await repo.create(_make_resource())
    updated = await repo.update_config(
        created.uid,
        config={"new": "value"},
        description="now with description",
    )
    assert updated.config == {"new": "value"}
    assert updated.description == "now with description"


@pytest.mark.asyncio
async def test_set_enabled(tmp_path):
    repo, _engine = await _repo(tmp_path)
    created = await repo.create(_make_resource())
    disabled = await repo.set_enabled(created.uid, False)
    assert disabled.enabled is False
    enabled = await repo.set_enabled(created.uid, True)
    assert enabled.enabled is True


@pytest.mark.asyncio
async def test_rename_moves_the_label_only(tmp_path):
    repo, engine = await _repo(tmp_path)
    created = await repo.create(_make_resource(name="before"))
    renamed = await repo.rename(created.uid, "after")
    assert renamed.name == "after"
    # The row did not move: same identity, same surrogate key, so nothing
    # holding either has to be rewritten.
    assert renamed.uid == created.uid
    assert renamed.id == created.id
    assert (await repo.find(created.uid)).name == "after"
    # And the label it left behind resolves to nothing.
    assert await repo.find_by_name("fake_kind", "before") is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_rename_onto_a_taken_label_raises(tmp_path):
    """The (kind, name) unique constraint is the authority on collisions, and
    it surfaces as ``ResourceAlreadyExists`` — never a raw IntegrityError —
    because a racing writer must look to the caller exactly like the pre-check
    it slipped past."""
    repo, engine = await _repo(tmp_path)
    a = await repo.create(_make_resource(name="a"))
    await repo.create(_make_resource(name="b"))
    with pytest.raises(ResourceAlreadyExists):
        await repo.rename(a.uid, "b")
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete(tmp_path):
    repo, _engine = await _repo(tmp_path)
    created = await repo.create(_make_resource())
    await repo.delete(created.uid)
    assert await repo.find(created.uid) is None
    # delete is idempotent
    await repo.delete(created.uid)


@pytest.mark.asyncio
async def test_config_round_trip_through_json(tmp_path):
    repo, engine = await _repo(tmp_path)
    nested = {"transport": {"type": "stdio", "args": ["a", "b"]}, "ttl": 30}
    created = await repo.create(_make_resource())
    await repo.update_config(created.uid, config=nested, description=None)
    found = await repo.find(created.uid)
    assert found is not None
    assert found.config == nested
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_defaults_scope_to_none(tmp_path):
    repo, engine = await _repo(tmp_path)
    created = await repo.create(_make_resource())
    assert created.scope is None
    found = await repo.find(created.uid)
    assert found is not None
    assert found.scope is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_scope_json_round_trip(tmp_path):
    repo, engine = await _repo(tmp_path)
    created = await repo.create(_make_resource())
    # Agent UIDS — a scope is a reference to another resource.
    scope = Scope(agents=["aa11bb22cc33dd44", "bb22cc33dd44ee55"])
    updated = await repo.update_scope(created.uid, scope)
    assert updated is not None
    assert updated.scope == scope

    found = await repo.find(created.uid)
    assert found is not None
    assert found.scope == scope

    # The dormant scope (an empty agents axis) must survive the JSON round trip
    # distinctly from None (unscoped) — `json.dumps` vs a NULL column.
    dormant = await repo.update_scope(created.uid, Scope(agents=[]))
    assert dormant is not None
    assert dormant.scope == Scope(agents=[])
    found_dormant = await repo.find(created.uid)
    assert found_dormant is not None
    assert found_dormant.scope == Scope(agents=[])

    cleared = await repo.update_scope(created.uid, None)
    assert cleared is not None
    assert cleared.scope is None
    found_cleared = await repo.find(created.uid)
    assert found_cleared is not None
    assert found_cleared.scope is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_scope_missing_uid_returns_none(tmp_path):
    repo, engine = await _repo(tmp_path)
    result = await repo.update_scope("no-such-uid", Scope(agents=["aa11bb22cc33dd44"]))
    assert result is None
    await engine.dispose()
