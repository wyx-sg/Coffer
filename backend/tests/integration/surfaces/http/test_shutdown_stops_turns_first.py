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
        "stop_converge_worker",
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
    chat: Any = MagicMock()
    chat.gateway_session.dispose = AsyncMock()
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
            kinds=kinds,
            chat=chat,
            engine=engine,
        )
    )

    assert order == ["turns", "engine"]
