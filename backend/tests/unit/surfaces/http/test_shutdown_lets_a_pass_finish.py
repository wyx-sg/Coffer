"""The teardown cancels the reconciler between passes, not inside one.

A pass cancelled mid-query leaves its database connection closing while the
engine is disposed, and that close never returns, so the teardown hung.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

from coffer.surfaces.http import app_shutdown


class _Reconciler:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        async with self.lock:
            yield


def _running(task: asyncio.Task[None], reconciler: Any) -> app_shutdown.Running:
    return app_shutdown.Running(
        workers=MagicMock(),
        channel_runtime=MagicMock(),
        channel_runtime_task=MagicMock(),
        reaper_task=MagicMock(),
        reconciler_task=task,
        attention_watch_task=MagicMock(),
        kinds=MagicMock(),
        engine=MagicMock(),
        reconciler=reconciler,
    )


async def test_a_pass_in_flight_finishes_before_the_loop_is_cancelled() -> None:
    reconciler = _Reconciler()
    finished: list[str] = []

    async def serve() -> None:
        while True:
            async with reconciler.lock:
                await asyncio.sleep(0.05)
                finished.append("pass")
            await asyncio.sleep(3600)

    task = asyncio.ensure_future(serve())
    await asyncio.sleep(0)  # the loop is inside its pass now

    await app_shutdown._stop_reconciler(_running(task, reconciler))

    assert finished == ["pass"]
    assert task.cancelled()


async def test_a_stuck_pass_does_not_hold_shutdown(monkeypatch: Any) -> None:
    monkeypatch.setattr(app_shutdown, "_PASS_GRACE_S", 0.05)
    reconciler = _Reconciler()

    async def serve() -> None:
        async with reconciler.lock:
            await asyncio.sleep(3600)

    task = asyncio.ensure_future(serve())
    await asyncio.sleep(0)

    await asyncio.wait_for(app_shutdown._stop_reconciler(_running(task, reconciler)), 2.0)

    assert task.cancelled()
