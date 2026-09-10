"""The daemon's self-eviction watcher (detect-or-spawn amendment).

A daemon orphaned by a spawn that could not see it — daemon.json lost, or an
already-serving daemon too busy to answer the liveness probe in time — used to
run forever holding its port, one restart at a time, until 8000-8009 were all
taken and no new daemon could start at all. Each daemon now watches whether
daemon.json has been taken over by a different live daemon and, if so, asks
uvicorn to exit.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from coffer.infrastructure.daemon import entry
from coffer.infrastructure.daemon.pid_lock import DaemonInfo


class _FakeServer:
    def __init__(self) -> None:
        self.should_exit = False


def _info(pid: int = 999, port: int = 8003) -> DaemonInfo:
    return DaemonInfo(
        version=1,
        pid=pid,
        port=port,
        token="tok",
        started_at=datetime.now(tz=UTC),
        binary_path="/fake/coffer-daemon",
    )


async def test_evicts_once_another_daemon_owns_daemon_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(entry.bootstrap, "superseded_by", lambda: _info())
    server = _FakeServer()

    await asyncio.wait_for(
        entry._evict_when_superseded(server, interval=0.01),  # type: ignore[arg-type]
        timeout=2.0,
    )

    assert server.should_exit is True


async def test_keeps_serving_while_daemon_json_is_still_ours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The watcher must never exit on its own — only a real supersession ends it."""
    monkeypatch.setattr(entry.bootstrap, "superseded_by", lambda: None)
    server = _FakeServer()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            entry._evict_when_superseded(server, interval=0.01),  # type: ignore[arg-type]
            timeout=0.2,
        )

    assert server.should_exit is False


async def test_a_failing_check_never_takes_the_daemon_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reading daemon.json is best-effort: an unreadable file or a psutil hiccup
    must leave the daemon serving, not evict it on a guess."""

    def _boom() -> DaemonInfo | None:
        raise OSError("cannot stat daemon.json")

    monkeypatch.setattr(entry.bootstrap, "superseded_by", _boom)
    server = _FakeServer()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            entry._evict_when_superseded(server, interval=0.01),  # type: ignore[arg-type]
            timeout=0.2,
        )

    assert server.should_exit is False
