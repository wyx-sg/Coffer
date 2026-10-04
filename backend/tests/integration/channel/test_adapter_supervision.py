"""A channel adapter's inbound loop runs supervised: a crash restarts that
adapter's loop alone (spec daemon "Supervise every background task the daemon
starts").

Two Telegram adapters, each with its own poll loop. The loop of the first one
raises once — the kind of bug the poll loop's own retry ladder does not catch —
and the supervisor logs it with the task's name and starts that loop again,
while the second adapter's loop is never touched.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
import pytest

from coffer.application.channel.ports import AdapterCallbacks
from coffer.infrastructure.channel import telegram as telegram_module
from coffer.infrastructure.channel.telegram import TelegramAdapter
from coffer.infrastructure.channel.telegram_profile import BotIdentity


async def _noop(*_: Any, **__: Any) -> None:
    return None


@pytest.mark.acceptance(
    spec="daemon", scenario="a crashed channel adapter restarts without touching the others"
)
async def test_one_adapters_crash_restarts_only_its_poll_loop(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    polls: dict[str, int] = {"alpha": 0, "beta": 0}
    alpha_back = asyncio.Event()

    async def fake_poll(_call: Any, _dispatch: Any, *, channel: str, timeout: int) -> None:
        polls[channel] += 1
        if channel == "alpha" and polls[channel] == 1:
            raise RuntimeError("a bug outside the poll loop's retry ladder")
        if channel == "alpha":
            alpha_back.set()
        await asyncio.Event().wait()

    async def fake_identity(_call: Any) -> BotIdentity:
        return BotIdentity()

    monkeypatch.setattr(telegram_module, "poll_updates", fake_poll)
    monkeypatch.setattr(telegram_module, "probe_identity", fake_identity)
    monkeypatch.setattr(telegram_module, "register_profile", _noop)

    callbacks = AdapterCallbacks(on_message=_noop, on_callback=_noop)
    adapters = [
        TelegramAdapter(name, "000:fake", client=httpx.AsyncClient()) for name in ("alpha", "beta")
    ]
    with caplog.at_level(logging.ERROR):
        for adapter in adapters:
            await adapter.start(callbacks)
        await asyncio.wait_for(alpha_back.wait(), timeout=5)
    try:
        assert polls == {"alpha": 2, "beta": 1}
        crashed = [r for r in caplog.records if r.getMessage() == "runtime.task.crashed"]
        assert [r.task for r in crashed] == ["telegram-poll:alpha"]  # type: ignore[attr-defined]
    finally:
        for adapter in adapters:
            await adapter.stop()
