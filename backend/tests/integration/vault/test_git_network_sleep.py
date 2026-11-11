"""A remote git call across a sleeping computer (spec vault-sync
"Let a sleeping computer neither stall nor fail a round")."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from coffer.application.runtime import sleep_clock
from coffer.domain.vault.remote_errors import RemoteProblem
from coffer.infrastructure.vault import git, remote


class _Clock:
    """A sleep-counting clock that jumps when told to."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a remote call cut short by sleep is retried and its deadline counts the sleep",
)
def test_a_hung_call_is_stopped_once_the_sleep_counting_deadline_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clock = _Clock()
    monkeypatch.setattr(git.sleep_clock, "now", clock)
    monkeypatch.setattr(git.sleep_clock, "slept_since", lambda *_: 4 * 3600.0)
    monkeypatch.setattr(git, "_DEADLINE_POLL_S", 0.05)
    hang = [sys.executable, "-c", "import time; time.sleep(30)"]

    # The computer "sleeps" four hours between the first two polls.
    real_popen = subprocess.Popen

    def popen(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        clock.t += 4 * 3600
        return real_popen(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(git.subprocess, "Popen", popen)
    done = git._run_until(hang, tmp_path, {"HOME": str(tmp_path)}, None, 120.0, ("fetch",))
    assert done.returncode == -9
    message = done.stderr.decode()
    assert "git fetch timed out after 120s" in message
    assert "the computer slept" in message
    assert remote.classify(message) is RemoteProblem.UNREACHABLE


def test_a_failure_after_sleep_is_tried_once_more(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[int] = []

    def fail(*_: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(1)
        return subprocess.CompletedProcess([], 128, b"", b"fatal: unable to access")

    monkeypatch.setattr(git, "_run_until", fail)
    monkeypatch.setattr(git.sleep_clock, "slept_since", lambda *_: 600.0)
    git._run_network(["git"], tmp_path, {}, None, 120.0, ("fetch",))
    assert len(calls) == 2

    calls.clear()
    monkeypatch.setattr(git.sleep_clock, "slept_since", lambda *_: 0.0)
    git._run_network(["git"], tmp_path, {}, None, 120.0, ("fetch",))
    assert len(calls) == 1


def test_a_network_call_abandons_a_stalled_transfer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, object] = {}

    def capture(argv: list[str], *_: object) -> subprocess.CompletedProcess[bytes]:
        seen["argv"] = argv
        seen["timeout"] = _[3]
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(git, "_run_network", capture)
    git.run(tmp_path, "fetch", "origin", network=True)
    argv = seen["argv"]
    assert isinstance(argv, list)
    assert f"http.lowSpeedLimit={git.STALL_BYTES_PER_S}" in argv
    assert f"http.lowSpeedTime={git.STALL_SECONDS}" in argv
    assert seen["timeout"] == git.NETWORK_TIMEOUT_S


def test_a_stalled_transfer_is_the_remote_being_unreachable() -> None:
    detail = "git fetch failed: error: RPC failed; curl 28 Operation too slow."
    assert remote.classify(detail) is RemoteProblem.UNREACHABLE


def test_the_sleep_clock_never_runs_behind_the_awake_clock() -> None:
    import time

    started, started_awake = sleep_clock.now(), time.monotonic()
    assert sleep_clock.slept_since(started, started_awake) >= 0.0
