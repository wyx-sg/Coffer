"""The proxy supervisor does not hot-loop a start that cannot succeed, and does
not start a proxy nothing is routed through."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coffer.domain.model_proxy.state import (
    ProxyMember,
    ProxyRoute,
    ProxyState,
    UpstreamAuth,
)
from coffer.domain.usage.records import Wire
from coffer.infrastructure.model_proxy import supervisor as sup
from coffer.infrastructure.model_proxy.info import ProxyInfo
from coffer.infrastructure.model_proxy.supervisor import FAILING_AFTER, ProxySupervisor


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _routed() -> ProxyState:
    member = ProxyMember(
        connection_uid="c",
        connection_name="C",
        upstream_root="https://c.example",
        auth=UpstreamAuth.BEARER,
        key="k",
    )
    return ProxyState(
        revision=1, routes=[ProxyRoute(agent_uid="a", wire=Wire.ANTHROPIC, members=[member])]
    )


def _supervisor(
    tmp_path: Path, clock: _Clock, state: ProxyState, **kwargs: object
) -> ProxySupervisor:
    async def provider() -> ProxyState:
        return state

    return ProxySupervisor(
        provider,
        port=1,
        coffer_dir=tmp_path,
        version="0.0.0",
        clock=clock,
        interval=0.0,
        **kwargs,  # type: ignore[arg-type]
    )


async def test_a_failing_start_backs_off_exponentially_up_to_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    supervisor = _supervisor(tmp_path, clock, _routed())
    attempts = 0

    async def failing_spawn() -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("model proxy exited at start (code 9)")

    monkeypatch.setattr(supervisor, "_spawn", failing_spawn)

    waits: list[float] = []
    for _ in range(12):
        before = attempts
        await supervisor._tick()
        assert attempts == before + 1  # the first tick after the wait tries again
        waits.append(supervisor._retry_at - clock.now)
        # Ticks inside the backoff window attempt nothing.
        for _ in range(5):
            await supervisor._tick()
        assert attempts == before + 1
        clock.now = supervisor._retry_at
    assert waits[:4] == [5.0, 10.0, 20.0, 40.0]
    assert max(waits) == sup._BACKOFF_MAX
    status = supervisor.status()
    assert status.failing is True
    assert status.consecutive_failures == 12
    assert status.last_error == "RuntimeError: model proxy exited at start (code 9)"


async def test_the_log_says_it_once_then_the_status_carries_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    clock = _Clock()
    supervisor = _supervisor(tmp_path, clock, _routed())

    async def failing_spawn() -> None:
        raise RuntimeError("same cause")

    monkeypatch.setattr(supervisor, "_spawn", failing_spawn)
    with caplog.at_level("WARNING", logger=sup.__name__):
        for _ in range(10):
            await supervisor._tick()
            clock.now = supervisor._retry_at
    lines = [r for r in caplog.records if "restart_failed" in r.getMessage()]
    # First failure, and the one that turns it into a standing failure.
    assert len(lines) == 2
    assert FAILING_AFTER == 3


async def test_a_good_probe_ends_the_failure_streak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    supervisor = _supervisor(tmp_path, clock, _routed())
    supervisor._failures = 4
    supervisor._info = ProxyInfo(port=1, pid=1, started_at="t", version="0.0.0", control_token="x")
    supervisor._pushed_revision = 7

    async def alive(_info: object) -> dict[str, object]:
        return {"revision": 7, "version": "0.0.0"}

    monkeypatch.setattr(supervisor, "_probe", alive)
    await supervisor._tick()
    assert supervisor.status().consecutive_failures == 0
    assert supervisor.status().failing is False


async def test_nothing_is_spawned_while_no_agent_is_routed_through_the_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    supervisor = _supervisor(tmp_path, clock, ProxyState())
    spawned = 0

    async def spawn_counter() -> None:
        nonlocal spawned
        spawned += 1

    monkeypatch.setattr(supervisor, "_spawn", spawn_counter)
    await supervisor.start()
    await supervisor.stop()
    assert spawned == 0
    status = supervisor.status()
    assert status.running is False
    assert status.failing is False
    assert status.last_error is None


async def test_a_state_push_wakes_an_idle_supervisor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    state = ProxyState()
    supervisor = _supervisor(tmp_path, clock, state)
    spawned = 0

    async def spawn_counter() -> None:
        nonlocal spawned
        spawned += 1
        raise RuntimeError("stop here")

    monkeypatch.setattr(supervisor, "_spawn", spawn_counter)
    await supervisor._tick()
    assert supervisor._idle is True
    await supervisor._tick()  # still inside the idle wait: not asked again
    assert spawned == 0

    # An agent gets a route; the reconcile pass that followed pushes state.
    routed = _routed()
    state.routes = routed.routes
    await supervisor.refresh()
    await supervisor._tick()
    assert spawned == 1


async def test_a_port_held_by_another_process_is_named_not_reported_as_a_bare_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path / "logs"))
    clock = _Clock()
    supervisor = _supervisor(
        tmp_path,
        clock,
        _routed(),
        command=[sys.executable, "-c", "raise SystemExit(3)"],
    )
    await supervisor.start()
    await supervisor.stop()
    error = supervisor.status().last_error
    assert error is not None
    assert "could not bind 127.0.0.1:1" in error
    assert "code 3" not in error
