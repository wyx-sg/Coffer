import asyncio

import pytest

from coffer.application.async_ops.registry import AsyncOpRegistry, OpState
from coffer.application.async_ops.runner import AsyncOpRunner


async def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not met within timeout")


@pytest.mark.asyncio
async def test_enqueue_runs_factory_then_clears():
    reg = AsyncOpRegistry()
    runner = AsyncOpRunner(reg, concurrency=2)
    await runner.start()
    ran = asyncio.Event()

    async def work() -> None:
        ran.set()

    runner.enqueue("distill", "s1", work)
    # marked queued synchronously on enqueue
    assert reg.get("distill", "s1").state is OpState.queued  # type: ignore[union-attr]

    await asyncio.wait_for(ran.wait(), timeout=2.0)
    await _wait_until(lambda: reg.get("distill", "s1") is None)
    await runner.stop()


@pytest.mark.asyncio
async def test_failure_is_recorded_and_worker_survives():
    reg = AsyncOpRegistry()
    runner = AsyncOpRunner(reg, concurrency=1)
    await runner.start()

    async def boom() -> None:
        raise RuntimeError("kaboom")

    ok = asyncio.Event()

    async def fine() -> None:
        ok.set()

    runner.enqueue("distill", "bad", boom)
    runner.enqueue("distill", "good", fine)

    # the failing item is recorded as error...
    await _wait_until(
        lambda: (e := reg.get("distill", "bad")) is not None and e.state is OpState.error
    )
    assert reg.get("distill", "bad").message == "kaboom"  # type: ignore[union-attr]
    # ...and the worker kept going for the next item
    await asyncio.wait_for(ok.wait(), timeout=2.0)
    await runner.stop()


@pytest.mark.asyncio
async def test_concurrency_cap_is_respected():
    reg = AsyncOpRegistry()
    runner = AsyncOpRunner(reg, concurrency=2)
    await runner.start()

    active = 0
    peak = 0
    release = asyncio.Event()

    async def hold() -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await release.wait()
        finally:
            active -= 1

    for i in range(6):
        runner.enqueue("distill", f"s{i}", hold)

    # let workers pick up; with cap=2 only 2 run at once
    await _wait_until(lambda: active == 2)
    await asyncio.sleep(0.05)
    assert peak == 2
    release.set()
    await _wait_until(lambda: reg.snapshot("distill") == {})
    await runner.stop()
