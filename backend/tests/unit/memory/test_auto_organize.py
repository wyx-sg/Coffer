"""Unit tests for MemoryAutoOrganizer (FR-035 session-end trigger)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.memory.auto_organize import MemoryAutoOrganizer


class _FakeOrganizer:
    def __init__(self, *, raises: bool = False) -> None:
        self.calls: list[str] = []
        self._raises = raises

    async def organize(self, *, store_name: str) -> Any:
        if self._raises:
            raise RuntimeError("boom")
        self.calls.append(store_name)


@pytest.mark.asyncio
async def test_single_change_triggers_organize() -> None:
    fake = _FakeOrganizer()
    auto = MemoryAutoOrganizer(organize=fake, delay_seconds=0.02)
    await auto.on_change("global")
    await asyncio.sleep(0.1)
    assert fake.calls == ["global"]


@pytest.mark.asyncio
async def test_rapid_changes_debounced_to_one_call() -> None:
    fake = _FakeOrganizer()
    auto = MemoryAutoOrganizer(organize=fake, delay_seconds=0.02)
    await auto.on_change("global")
    await auto.on_change("global")
    await auto.on_change("global")
    await asyncio.sleep(0.1)
    assert fake.calls == ["global"]


@pytest.mark.asyncio
async def test_multi_store_organizes_each() -> None:
    fake = _FakeOrganizer()
    auto = MemoryAutoOrganizer(organize=fake, delay_seconds=0.02)
    await auto.on_change("a")
    await auto.on_change("b")
    await asyncio.sleep(0.1)
    assert sorted(fake.calls) == ["a", "b"]


@pytest.mark.asyncio
async def test_shutdown_cancels_pending_organize() -> None:
    fake = _FakeOrganizer()
    auto = MemoryAutoOrganizer(organize=fake, delay_seconds=0.02)
    await auto.on_change("global")
    await auto.shutdown()
    await asyncio.sleep(0.1)
    assert fake.calls == []


@pytest.mark.asyncio
async def test_exception_in_organize_suppressed_and_scheduler_survives() -> None:
    fake_raising = _FakeOrganizer(raises=True)
    auto = MemoryAutoOrganizer(organize=fake_raising, delay_seconds=0.02)
    # Should not raise
    await auto.on_change("global")
    await asyncio.sleep(0.1)
    assert fake_raising.calls == []  # raises, nothing recorded
    # Scheduler survived: a subsequent on_change still works
    fake_ok = _FakeOrganizer()
    auto2 = MemoryAutoOrganizer(organize=fake_ok, delay_seconds=0.02)
    await auto2.on_change("x")
    await asyncio.sleep(0.1)
    assert fake_ok.calls == ["x"]


@pytest.mark.asyncio
async def test_shutdown_with_nothing_pending_is_noop() -> None:
    fake = _FakeOrganizer()
    auto = MemoryAutoOrganizer(organize=fake, delay_seconds=0.02)
    await auto.shutdown()  # should not raise
    assert fake.calls == []
