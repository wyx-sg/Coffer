"""The teardown stops running chat turns before it disposes the database.

A turn cancelled by shutdown writes its partial reply as it unwinds (spec chat
"Keep partial output when a turn is interrupted or fails"). That write needs the
engine, so the teardown must cancel and await the turns first — leaving them to
the event loop's own teardown would run them after ``engine.dispose()``.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from coffer.surfaces.http import app_shutdown


async def _done() -> None:
    return None


@pytest.mark.acceptance(
    spec="chat",
    scenario="a shutdown keeps the partial reply",
)
async def test_turns_are_stopped_before_the_engine_is_disposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []

    async def fake_stop_all_turns(*, timeout: float = 5.0) -> int:
        order.append("turns")
        return 1

    engine = MagicMock()

    async def dispose() -> None:
        order.append("engine")

    engine.dispose = dispose
    monkeypatch.setattr(app_shutdown, "stop_all_turns", fake_stop_all_turns)
    for name in (
        "stop_sync_worker",
        "stop_curation_worker",
        "stop_distil_worker",
        "stop_aggregate_worker",
        "stop_transcript_warm_worker",
        "shutdown_all_sessions",
    ):
        monkeypatch.setattr(app_shutdown, name, AsyncMock())

    kinds: Any = MagicMock()
    kinds.mcp.invocation_repo.stop = AsyncMock()
    kinds.mcp.session_supervisors = {}
    runtime: Any = MagicMock()
    runtime.dispose = AsyncMock()
    workers: Any = MagicMock()
    workers.retention_task = asyncio.ensure_future(_done())

    await app_shutdown.shutdown(
        app_shutdown.Running(
            workers=workers,
            channel_runtime=runtime,
            channel_runtime_task=asyncio.ensure_future(_done()),
            reaper_task=asyncio.ensure_future(_done()),
            reconciler_task=asyncio.ensure_future(_done()),
            attention_watch_task=asyncio.ensure_future(_done()),
            kinds=kinds,
            engine=engine,
        )
    )

    assert order == ["turns", "engine"]


async def test_a_cancelled_step_is_not_logged_as_failed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def forever() -> None:
        await asyncio.Event().wait()

    async def fake_stop_all_turns(*, timeout: float = 5.0) -> int:
        return 0

    monkeypatch.setattr(app_shutdown, "stop_all_turns", fake_stop_all_turns)
    for name in (
        "stop_sync_worker",
        "stop_curation_worker",
        "stop_distil_worker",
        "stop_aggregate_worker",
        "stop_transcript_warm_worker",
        "shutdown_all_sessions",
    ):
        monkeypatch.setattr(app_shutdown, name, AsyncMock())

    kinds: Any = MagicMock()
    kinds.mcp.invocation_repo.stop = AsyncMock()
    kinds.mcp.session_supervisors = {}
    kinds.agent_skill.skill_sources.stop = AsyncMock()
    kinds.provider.proxy.stop = AsyncMock()
    kinds.provider.stop_price_refresh = AsyncMock()
    kinds.usage.stop = AsyncMock()
    runtime: Any = MagicMock()
    runtime.dispose = AsyncMock()
    engine: Any = MagicMock()
    engine.dispose = AsyncMock()
    workers: Any = MagicMock()
    workers.retention_task = asyncio.ensure_future(_done())

    monkeypatch.setattr(app_shutdown, "tasks", lambda: MagicMock(shutdown=AsyncMock()))
    with caplog.at_level("ERROR"):
        await app_shutdown.shutdown(
            app_shutdown.Running(
                workers=workers,
                channel_runtime=runtime,
                channel_runtime_task=asyncio.ensure_future(forever()),
                reaper_task=asyncio.ensure_future(forever()),
                reconciler_task=asyncio.ensure_future(_done()),
                attention_watch_task=asyncio.ensure_future(_done()),
                kinds=kinds,
                engine=engine,
            )
        )

    assert "shutdown.step_failed" not in caplog.text
