"""``SnapshotSessionSource``: stale-while-revalidate, single flight, invalidation."""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any

import pytest

from coffer.application.agent.native_session_service import SourcePage
from coffer.application.agent.session_listing_snapshot import SnapshotSessionSource

_DIR = pathlib.Path("/cfg")


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _Inner:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.gate: asyncio.Event | None = None
        self.renamed: list[str] = []

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        self.calls += 1
        n = self.calls
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("boom")
        return SourcePage(items=[], next_position=[n], total=n)

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None:
        self.renamed.append(session_id)

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None:
        self.renamed.append(session_id)


def _make(**kw: Any) -> tuple[SnapshotSessionSource, _Inner, _Clock]:
    inner, clock = _Inner(), _Clock()
    return SnapshotSessionSource(inner, clock=clock, **kw), inner, clock


async def _list(src: SnapshotSessionSource, position: list[Any] | None = None) -> SourcePage:
    return await src.list(_DIR, q=None, limit=50, position=position)


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_fresh_entry_is_served_without_asking() -> None:
    src, inner, clock = _make()
    first = await _list(src)
    clock.now += 4
    assert await _list(src) is first
    assert inner.calls == 1


async def test_stale_entry_is_served_and_refreshed_once() -> None:
    src, inner, clock = _make()
    first = await _list(src)
    clock.now += 10
    inner.gate = asyncio.Event()
    assert await _list(src) is first  # served at once
    assert await _list(src) is first  # still one refresh in flight
    await _settle()
    assert inner.calls == 2
    inner.gate.set()
    await _settle()
    fresh = await _list(src)
    assert fresh.total == 2
    assert inner.calls == 2


async def test_concurrent_misses_share_one_fetch() -> None:
    src, inner, _ = _make()
    inner.gate = asyncio.Event()
    tasks = [asyncio.create_task(_list(src)) for _ in range(4)]
    await _settle()
    inner.gate.set()
    pages = await asyncio.gather(*tasks)
    assert inner.calls == 1
    assert all(p is pages[0] for p in pages)


async def test_entry_older_than_max_age_blocks_on_a_fetch() -> None:
    src, inner, clock = _make(max_age_s=60)
    await _list(src)
    clock.now += 61
    page = await _list(src)
    assert inner.calls == 2
    assert page.total == 2


async def test_rename_and_delete_drop_the_dir_then_next_read_is_fresh() -> None:
    src, inner, _ = _make()
    await _list(src)
    await src.rename(_DIR, "s1", "t")
    await _list(src)
    assert inner.calls == 2
    await src.delete(_DIR, "s1")
    await _list(src)
    assert inner.calls == 3
    assert inner.renamed == ["s1", "s1"]


async def test_other_config_dirs_survive_an_invalidation() -> None:
    src, inner, _ = _make()
    await src.list(pathlib.Path("/other"), q=None, limit=50, position=None)
    await _list(src)
    await src.rename(_DIR, "s1", "t")
    await src.list(pathlib.Path("/other"), q=None, limit=50, position=None)
    assert inner.calls == 2


async def test_background_failure_keeps_the_old_entry() -> None:
    src, inner, clock = _make()
    first = await _list(src)
    clock.now += 10
    inner.fail = True
    assert await _list(src) is first
    await _settle()
    assert inner.calls == 2
    assert await _list(src) is first  # still served; refresh retried, not an error


async def test_foreground_failure_propagates() -> None:
    src, inner, _ = _make()
    inner.fail = True
    with pytest.raises(RuntimeError):
        await _list(src)
    inner.fail = False
    assert (await _list(src)).total == 2  # a failure is not cached


async def test_position_and_query_are_part_of_the_key() -> None:
    src, inner, _ = _make()
    await _list(src, [1, "a"])
    await _list(src, [1, "a"])
    await _list(src, [2, "b"])
    await _list(src, None)
    assert inner.calls == 3


async def test_lru_bound() -> None:
    src, inner, _ = _make(max_entries=2)
    for i in range(3):
        await _list(src, [i])
    assert inner.calls == 3
    await _list(src, [2])
    await _list(src, [1])
    assert inner.calls == 3
    await _list(src, [0])  # evicted
    assert inner.calls == 4


async def test_aclose_cancels_inflight_refresh() -> None:
    src, inner, clock = _make()
    await _list(src)
    clock.now += 10
    inner.gate = asyncio.Event()
    await _list(src)
    await _settle()
    await src.aclose()
    assert not src._inflight


async def test_a_read_in_flight_across_a_rename_answers_but_is_not_kept() -> None:
    src, inner, _clock = _make()
    inner.gate = asyncio.Event()
    waiting = asyncio.ensure_future(_list(src))
    await _settle()
    await src.rename(_DIR, "s1", "new")
    inner.gate.set()
    first = await waiting  # the caller still gets its answer
    assert first.total == 1
    again = await _list(src)  # but it was not kept: the agent is asked again
    assert again.total == 2
    assert inner.calls == 2
