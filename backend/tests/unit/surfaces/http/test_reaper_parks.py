"""The MCP session reaper parks while no session is open (ADR
background-workers-wake-on-events)."""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.runtime.workers import workers
from coffer.surfaces.http.mcp import session_registry as registry


def _state() -> str | None:
    row = next((w for w in workers().snapshot() if w.name == "mcp-session-reaper"), None)
    return row.state if row else None


async def _until(predicate) -> None:  # type: ignore[no-untyped-def]
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest.mark.acceptance(spec="daemon", scenario="the MCP session reaper parks with no session open")
async def test_the_reaper_parks_with_no_session_and_wakes_on_activity() -> None:
    assert not registry._LAST_ACTIVITY
    task = registry.start_session_reaper(interval_seconds=0.02, max_idle_seconds=0.05)
    try:
        await _until(lambda: _state() == "parked")
        registry._touch("s-1")
        await _until(lambda: _state() in {"waiting", "running"})
        # Idle past the limit: reaped, and with nothing left the reaper parks again.
        await _until(lambda: "s-1" not in registry._LAST_ACTIVITY)
        await _until(lambda: _state() == "parked")
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        registry._LAST_ACTIVITY.pop("s-1", None)
