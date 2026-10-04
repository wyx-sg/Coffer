"""The resource list is ORDERED, and a write does not reshuffle it.

The list this repo returns is rendered as a table the user clicks rows in. Its
order is (kind, name) whatever order the files were written in, and a write to
one resource does not move any other: from the user's seat the alternative is
"I clicked row 1 and row 4 changed".
"""

from datetime import UTC, datetime

from coffer.domain.resource import Resource
from tests.support.vault_stores import make_resource_repo


def _resource(name: str, *, kind: str = "mcp_server") -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        # The uid is the identity, but it is deliberately NOT what the list is
        # ordered by: a reader scans the name column, and an opaque identity
        # sorts into an order nobody can predict.
        uid=f"uid-{kind}-{name}",
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


async def test_list_is_sorted_by_name() -> None:
    repo = make_resource_repo()
    for name in _NAMES:
        await repo.create(_resource(name))
    listed = [r.name for r in await repo.list(kind="mcp_server")]
    assert listed == sorted(_NAMES)


async def test_order_survives_a_write_to_one_row() -> None:
    """The regression itself: disabling one row must not move any row."""
    repo = make_resource_repo()
    for name in _NAMES:
        await repo.create(_resource(name))
    before = [r.name for r in await repo.list(kind="mcp_server")]

    zulu = await repo.find_by_name("mcp_server", "zulu")
    assert zulu is not None
    await repo.set_enabled(zulu.uid, False)
    after = [r.name for r in await repo.list(kind="mcp_server")]

    assert after == before
    # And the write landed on the row that was asked for, not a neighbour.
    disabled = [r.name for r in await repo.list(kind="mcp_server", enabled=False)]
    assert disabled == ["zulu"]


async def test_kinds_do_not_interleave() -> None:
    """Ordering by (kind, name) keeps an unfiltered list grouped by kind, which
    is what a caller listing everything reads it as."""
    repo = make_resource_repo()
    await repo.create(_resource("zulu", kind="channel"))
    await repo.create(_resource("alpha", kind="mcp_server"))
    await repo.create(_resource("alpha", kind="channel"))
    listed = [(r.kind, r.name) for r in await repo.list()]
    assert listed == [
        ("channel", "alpha"),
        ("channel", "zulu"),
        ("mcp_server", "alpha"),
    ]
