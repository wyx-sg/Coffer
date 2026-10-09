"""The channel runtime runs a pass when something it reads changes, not on a
short timer (ADR background-workers-wake-on-events)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.channel import runtime as runtime_module
from coffer.application.channel.runtime import ChannelRuntime

from .conftest import ChannelEnv, uid_of


def _quiet_runtime(env: ChannelEnv, factory: Any = None) -> ChannelRuntime:
    """The fixture's runtime, but with a fallback no test waits out."""
    return ChannelRuntime(
        resources=env.resources,
        adapter_factory=factory or env.adapter_factory,
        processor=env.processor,
        pairing=env.pairing,
        fallback_seconds=3600.0,
    )


async def _until(predicate: Any, timeout: float = 3.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest.mark.acceptance(
    spec="daemon", scenario="a resource write brings the channel runtime's next pass forward"
)
async def test_a_write_brings_the_next_pass_forward(env: ChannelEnv) -> None:
    runtime = _quiet_runtime(env)
    task = asyncio.create_task(runtime.run())
    try:
        await env.register_channel("tg")
        await asyncio.sleep(0.3)
        assert not runtime.is_running(uid_of("tg")), "nothing woke it, so nothing ran"
        runtime.on_changed(object())
        await _until(lambda: runtime.is_running(uid_of("tg")))
    finally:
        runtime.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runtime.dispose()


@pytest.mark.acceptance(
    spec="daemon", scenario="a failed channel start is retried when its wait is over"
)
async def test_a_failed_start_is_retried_once_its_wait_is_over(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime_module, "FAILURE_RETRY_SECONDS", 0.2)
    calls = 0

    async def flaky(uid: str, config: dict[str, object]) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("platform unreachable")
        return await env.adapter_factory(uid, config)

    runtime = _quiet_runtime(env, flaky)
    await env.register_channel("tg")
    task = asyncio.create_task(runtime.run())
    try:
        await _until(lambda: runtime.is_running(uid_of("tg")))
        assert calls == 2
    finally:
        runtime.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runtime.dispose()
