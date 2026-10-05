"""The attention list is computed once and handed to every reader until
something may have changed it."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from coffer.application.attention import (
    AttentionAction,
    AttentionItem,
    AttentionService,
    Severity,
)


def _item(uid: str) -> AttentionItem:
    return AttentionItem(
        kind="mcp_server",
        uid=uid,
        title=uid,
        reason_code="down",
        reason="Because.",
        severity=Severity.WARNING,
        action=AttentionAction("check", "GET", "/api/v1/mcp"),
    )


class _Source:
    name = "mcp"
    feature: str | None = None

    def __init__(self) -> None:
        self.asked = 0
        self.uids = ["a"]
        self.gate: asyncio.Event | None = None

    async def items(self) -> Sequence[AttentionItem]:
        self.asked += 1
        if self.gate is not None:
            await self.gate.wait()
        return [_item(u) for u in self.uids]


class _Clock:
    now = 100.0

    def __call__(self) -> float:
        return self.now


class _Ignores:
    def __init__(self) -> None:
        self.held: set[str] = set()

    async def keys(self) -> set[str]:
        return set(self.held)

    async def add(self, key: str) -> bool:
        before = len(self.held)
        self.held.add(key)
        return len(self.held) > before

    async def remove(self, key: str) -> bool:
        if key in self.held:
            self.held.discard(key)
            return True
        return False


def _service(source: _Source, clock: _Clock, **kw: object) -> AttentionService:
    return AttentionService(
        [source], feature_enabled=lambda _f: True, reuse_seconds=30.0, clock=clock, **kw
    )  # type: ignore[arg-type]


async def test_readers_share_one_computation_until_it_ages() -> None:
    source, clock = _Source(), _Clock()
    service = _service(source, clock)
    await service.report()
    await service.report()
    assert source.asked == 1
    clock.now += 30
    await service.report()
    assert source.asked == 2


async def test_concurrent_readers_wait_for_one_computation() -> None:
    source, clock = _Source(), _Clock()
    source.gate = asyncio.Event()
    service = _service(source, clock)
    readers = [asyncio.ensure_future(service.report()) for _ in range(3)]
    await asyncio.sleep(0)
    source.gate.set()
    await asyncio.gather(*readers)
    assert source.asked == 1


async def test_fresh_and_invalidate_ask_the_sources_again() -> None:
    source, clock = _Source(), _Clock()
    service = _service(source, clock)
    await service.report()
    await service.report(fresh=True)
    assert source.asked == 2
    source.uids = []
    service.invalidate()
    assert (await service.report()).items == ()
    assert source.asked == 3


async def test_a_report_computed_across_an_invalidation_is_not_kept() -> None:
    source, clock = _Source(), _Clock()
    source.gate = asyncio.Event()
    service = _service(source, clock)
    reading = asyncio.ensure_future(service.report())
    await asyncio.sleep(0)
    service.invalidate()  # a write landed while the sources were being asked
    source.gate.set()
    await reading
    source.gate = None
    await service.report()
    assert source.asked == 2


async def test_ignoring_drops_the_kept_report() -> None:
    source, clock = _Source(), _Clock()
    service = _service(source, clock, ignores=_Ignores())
    assert len((await service.report()).items) == 1
    await service.ignore("mcp_server:a:down", actor="test")
    assert (await service.report()).items == ()
    await service.unignore("mcp_server:a:down", actor="test")
    assert len((await service.report()).items) == 1


async def test_reuse_is_off_by_default() -> None:
    source = _Source()
    service = AttentionService([source], feature_enabled=lambda _f: True)  # type: ignore[list-item]
    await service.report()
    await service.report()
    assert source.asked == 2
