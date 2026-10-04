"""The daemon's own restart planner (spec daemon "Restart itself on request"):
the successor's environment and its wait for the predecessor, over fakes."""

from __future__ import annotations

import pytest

from coffer.infrastructure.daemon import self_restart
from coffer.infrastructure.daemon.self_restart import (
    PREDECESSOR_ENV,
    await_predecessor,
    successor_env,
)


def test_the_successor_inherits_the_environment_and_names_its_predecessor() -> None:
    env = successor_env({"PATH": "/bin", "HOME": "/h"}, 321, frozen=False)
    assert env == {"PATH": "/bin", "HOME": "/h", PREDECESSOR_ENV: "321"}


def test_a_frozen_successor_unpacks_its_own_files() -> None:
    """A one-file build starting itself must not reuse the parent's unpack dir,
    which goes when the parent exits."""
    env = successor_env({"PATH": "/bin"}, 1, frozen=True)
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert "PYINSTALLER_RESET_ENVIRONMENT" not in successor_env(
        {"PYINSTALLER_RESET_ENVIRONMENT": "1"}, 1, frozen=False
    )


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_a_plain_start_waits_for_nothing() -> None:
    environ: dict[str, str] = {}
    clock = _Clock()
    assert await_predecessor(environ, gone=lambda _pid: False, sleep=clock.sleep, clock=clock)
    assert clock.slept == []


@pytest.mark.acceptance(
    spec="daemon", scenario="the successor binds only after its predecessor has exited"
)
def test_the_successor_waits_until_the_predecessor_is_gone() -> None:
    environ = {PREDECESSOR_ENV: "77", "PATH": "/bin"}
    clock = _Clock()
    asked: list[int] = []

    def gone(pid: int) -> bool:
        asked.append(pid)
        return len(asked) > 3

    assert await_predecessor(environ, gone=gone, sleep=clock.sleep, clock=clock)
    assert set(asked) == {77} and len(asked) == 4
    assert len(clock.slept) == 3
    # Read once: nothing this daemon spawns inherits it.
    assert PREDECESSOR_ENV not in environ


def test_a_predecessor_that_never_exits_is_given_up_on() -> None:
    environ = {PREDECESSOR_ENV: "77"}
    clock = _Clock()
    assert not await_predecessor(
        environ, gone=lambda _pid: False, sleep=clock.sleep, clock=clock, timeout=1.0
    )
    assert clock.now >= 1.0


def test_a_malformed_predecessor_is_ignored() -> None:
    environ = {PREDECESSOR_ENV: "not-a-pid"}
    assert await_predecessor(environ, gone=lambda _pid: False)
    assert PREDECESSOR_ENV not in environ


def test_a_missing_process_counts_as_gone() -> None:
    # A pid far past any real one: psutil reports it absent.
    assert self_restart.process_is_gone(2**22 + 12345)


def test_spawn_successor_passes_the_planned_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class _Proc:
        pid = 999

    def fake_spawn(env: dict[str, str] | None = None) -> _Proc:
        seen["env"] = env
        return _Proc()

    monkeypatch.setattr(self_restart, "spawn_detached_daemon", fake_spawn)
    monkeypatch.setattr(self_restart.os, "getpid", lambda: 555)
    assert self_restart.spawn_successor() == 999
    env = seen["env"]
    assert isinstance(env, dict) and env[PREDECESSOR_ENV] == "555"
