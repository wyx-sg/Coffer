"""The resource list is ORDERED, and a write does not reshuffle it.

The list this repo returns is rendered as a table the user clicks rows in. An
unordered SELECT let SQLite return rows in whatever order a scan produced, and
an UPDATE could move a row within it — so toggling one server re-rendered the
list in a new order and the row the user had just clicked was somewhere else.
From the user's seat that is "I clicked row 1 and row 4 changed".
"""

from datetime import UTC, datetime

import pytest

from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyResourceRepo


async def _repo(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlAlchemyResourceRepo(session_maker(engine)), engine


def _resource(name: str, *, kind: str = "mcp_server") -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        id=0,
        kind=kind,
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=now,
        updated_at=now,
    )


# Inserted deliberately out of alphabetical order, so "sorted" cannot be
# mistaken for "insertion order happened to be sorted".
_NAMES = ["zulu", "alpha", "mike", "bravo", "yankee"]


@pytest.mark.asyncio
async def test_list_is_sorted_by_name(tmp_path) -> None:
    repo, engine = await _repo(tmp_path)
    try:
        for name in _NAMES:
            await repo.create(_resource(name))
        listed = [r.name for r in await repo.list(kind="mcp_server")]
        assert listed == sorted(_NAMES)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_order_survives_a_write_to_one_row(tmp_path) -> None:
    """The regression itself: disabling one row must not move any row."""
    repo, engine = await _repo(tmp_path)
    try:
        for name in _NAMES:
            await repo.create(_resource(name))
        before = [r.name for r in await repo.list(kind="mcp_server")]

        await repo.set_enabled(ResourceRef("mcp_server", "zulu"), False)
        after = [r.name for r in await repo.list(kind="mcp_server")]

        assert after == before
        # And the write landed on the row that was asked for, not a neighbour.
        disabled = [r.name for r in await repo.list(kind="mcp_server", enabled=False)]
        assert disabled == ["zulu"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_kinds_do_not_interleave(tmp_path) -> None:
    """Ordering by (kind, name) keeps an unfiltered list grouped by kind, which
    is what a caller listing everything reads it as."""
    repo, engine = await _repo(tmp_path)
    try:
        await repo.create(_resource("zulu", kind="channel"))
        await repo.create(_resource("alpha", kind="mcp_server"))
        await repo.create(_resource("alpha", kind="channel"))
        listed = [(r.kind, r.name) for r in await repo.list()]
        assert listed == [
            ("channel", "alpha"),
            ("channel", "zulu"),
            ("mcp_server", "alpha"),
        ]
    finally:
        await engine.dispose()
