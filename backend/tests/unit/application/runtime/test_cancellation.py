"""A task asked to stop knows it, even when cleanup turned the cancel into
another exception (ADR background-loops-stop-when-their-task-is-cancelled)."""

from __future__ import annotations

import asyncio

from coffer.application.runtime.cancellation import stop_requested


async def test_a_running_task_has_no_stop_outstanding() -> None:
    assert not stop_requested()


async def test_a_cancelled_task_knows_after_cleanup_raised_something_else() -> None:
    seen: list[bool] = []

    async def query() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # What SQLAlchemy's pool can raise when a second cancel lands
            # while it closes the connection of a cancelled query.
            raise RuntimeError("no active connection") from None

    async def worker() -> None:
        try:
            await query()
        except RuntimeError:
            seen.append(stop_requested())

    task = asyncio.create_task(worker())
    await asyncio.sleep(0)
    task.cancel()
    await task
    assert seen == [True]


async def test_a_timeout_that_withdrew_its_cancel_is_not_a_stop() -> None:
    try:
        async with asyncio.timeout(0.01):
            await asyncio.Event().wait()
    except TimeoutError:
        pass
    assert not stop_requested()
