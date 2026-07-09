"""The file-tree watcher feeds change notifications (spec 010, ADR-043)."""

from __future__ import annotations

import asyncio

from coffer.infrastructure.sync.watcher import watch_trees


async def test_watcher_notifies_on_file_change(tmp_path) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "memory"
    notified = asyncio.Event()
    stop = asyncio.Event()
    task = asyncio.create_task(watch_trees([root], notified.set, stop))
    try:
        await asyncio.sleep(0.3)  # let the watcher arm (it also mkdirs the root)
        (root / "fact.md").write_text("hello\n", encoding="utf-8")
        await asyncio.wait_for(notified.wait(), timeout=10.0)
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5.0)


async def test_watcher_stops_cleanly_and_never_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
    stop = asyncio.Event()
    task = asyncio.create_task(watch_trees([tmp_path / "kb"], lambda: None, stop))
    await asyncio.sleep(0.2)
    stop.set()
    await asyncio.wait_for(task, timeout=5.0)  # returns, no exception
