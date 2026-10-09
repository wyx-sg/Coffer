"""In-process unit tests for `coffer daemon` start/stop/status.

The existing test_daemon_lifecycle.py drives daemon_cmd through subprocess +
real-process side effects, which never exercises the in-process function
bodies for coverage and is slow.  These tests monkeypatch subprocess.Popen,
os.kill, and the daemon-discovery helpers so we can pin each branch.
"""

from __future__ import annotations

import json
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import typer

from coffer.infrastructure.daemon import spawn as _spawn
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli import daemon_cmd


def _setup_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway HOME, plus the port-range override every daemon test needs.

    ``daemon start`` pre-flights the port it is about to bind, which with no
    override is the real 38470 — the port the developer's own daemon is usually
    sitting on. These tests fake ``Popen`` and care about the spawn plumbing,
    not the port, so they pin a range of their own (as test_daemon_lifecycle.py
    does) rather than contending for a port they never intended to use.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "58200")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "58209")
    return home


# --------------------------------------------------------------------------- #
# start                                                                        #
# --------------------------------------------------------------------------- #


def test_daemon_start_writes_pid_and_echoes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """daemon_cmd.start happy path: Popen is invoked, the daemon.json is
    written by the (faked) child, and the CLI prints `daemon started`."""
    home = _setup_home(tmp_path, monkeypatch)
    daemon_json = home / ".coffer" / "daemon.json"
    daemon_json.parent.mkdir(parents=True, exist_ok=True)

    popen_args: dict[str, Any] = {}

    class _FakeProc:
        pid = 4242
        returncode = None

        def poll(self) -> None:
            return None

        def kill(self) -> None:  # not used on happy path
            pass

    def _fake_popen(cmd: list[str], **kwargs: Any) -> _FakeProc:
        popen_args["cmd"] = cmd
        popen_args["kwargs"] = kwargs
        daemon_json.write_text(json.dumps({"port": 9999, "token": "t", "pid": 4242, "version": 1}))
        return _FakeProc()

    monkeypatch.setattr(_spawn.subprocess, "Popen", _fake_popen)
    answers = iter([None, _fake_info()])  # nobody before the spawn, serving after it
    monkeypatch.setattr(daemon_cmd.bootstrap, "live_daemon", lambda: next(answers))

    daemon_cmd.start()
    out = capsys.readouterr().out
    assert "daemon started" in out
    assert popen_args["cmd"][1:] == ["-m", "coffer.infrastructure.daemon.entry"]


def test_daemon_start_short_circuits_when_a_live_daemon_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If a LIVE daemon answers (live_daemon() is not None), `daemon start`
    exits 0 with the 'already running' notice without invoking Popen."""
    _setup_home(tmp_path, monkeypatch)

    monkeypatch.setattr(daemon_cmd.bootstrap, "live_daemon", lambda: _fake_info())

    def _bad_popen(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Popen must not be invoked when daemon already running")

    monkeypatch.setattr(_spawn.subprocess, "Popen", _bad_popen)

    with pytest.raises(typer.Exit) as excinfo:
        daemon_cmd.start()
    assert excinfo.value.exit_code == 0
    assert "already running" in capsys.readouterr().out


def test_daemon_start_respawns_over_stale_daemon_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stale daemon.json (file present but no daemon answering) must NOT be
    treated as 'already running': start() must spawn a fresh daemon. This is
    spec daemon "Manage the daemon from the command line" — `daemon start`
    keys off live_daemon(), not file presence."""
    home = _setup_home(tmp_path, monkeypatch)
    daemon_json = home / ".coffer" / "daemon.json"
    daemon_json.parent.mkdir(parents=True, exist_ok=True)
    # Stale file left by a crashed daemon — present, but nothing is serving.
    daemon_json.write_text(json.dumps({"port": 9999, "token": "t", "pid": 1, "version": 1}))

    answers = iter([None, _fake_info()])
    monkeypatch.setattr(daemon_cmd.bootstrap, "live_daemon", lambda: next(answers))

    spawned = {"popen": False}

    class _FakeProc:
        pid = 7777
        returncode = None

        def poll(self) -> None:
            return None

        def kill(self) -> None:
            pass

    def _fake_popen(cmd: list[str], **kwargs: Any) -> _FakeProc:
        spawned["popen"] = True
        # Child rewrites daemon.json with its own pid.
        daemon_json.write_text(json.dumps({"port": 9998, "token": "t2", "pid": 7777, "version": 1}))
        return _FakeProc()

    monkeypatch.setattr(_spawn.subprocess, "Popen", _fake_popen)

    daemon_cmd.start()
    assert spawned["popen"] is True, "stale daemon.json must trigger a respawn"
    assert "daemon started" in capsys.readouterr().out


def test_daemon_start_fails_when_the_daemon_never_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A daemon.json (even a fresh one) is not success: if nothing answers the
    status call in time, start() exits 1 — and leaves the child alone, since a
    slow boot finishes and a stuck one gives up on the spawn lock by itself."""
    _setup_home(tmp_path, monkeypatch)

    class _FakeProc:
        pid = 4243
        returncode = None
        killed = False

        def poll(self) -> None:
            return None

        def kill(self) -> None:
            type(self).killed = True

    monkeypatch.setattr(_spawn.subprocess, "Popen", lambda cmd, **kw: _FakeProc())
    monkeypatch.setattr(daemon_cmd.bootstrap, "live_daemon", lambda: None)
    monkeypatch.setattr(daemon_cmd, "START_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(typer.Exit) as excinfo:
        daemon_cmd.start()
    assert excinfo.value.exit_code == 1
    assert _FakeProc.killed is False
    assert "did not answer" in capsys.readouterr().err


@pytest.mark.acceptance(spec="daemon", scenario="start reports a daemon that refused to start")
def test_daemon_start_reports_a_daemon_that_refused_and_exited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The lifespan refuses (migration required, git too old) after daemon.json
    is published and the process exits: start() must say so, not "started"."""
    home = _setup_home(tmp_path, monkeypatch)
    stale = home / ".coffer" / "daemon.json"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text(json.dumps({"port": 9999, "token": "t", "pid": 1, "version": 1}))

    class _FakeProc:
        pid = 4244
        returncode = 2

        def poll(self) -> int:
            return 2

    monkeypatch.setattr(_spawn.subprocess, "Popen", lambda cmd, **kw: _FakeProc())
    monkeypatch.setattr(daemon_cmd.bootstrap, "live_daemon", lambda: None)

    with pytest.raises(typer.Exit) as excinfo:
        daemon_cmd.start()
    assert excinfo.value.exit_code == 1
    assert "exited at startup" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# stop                                                                         #
# --------------------------------------------------------------------------- #


def _fake_info(port: int = 9000, pid: int = 5555) -> DaemonInfo:
    return DaemonInfo(
        version=1,
        pid=pid,
        port=port,
        token="t",
        started_at=datetime.now(tz=UTC),
    )


def test_daemon_stop_sends_sigterm_and_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """stop() resolves discover() -> info, verifies the pid IS a coffer daemon,
    sends SIGTERM to info.pid, then waits for daemon.json to be removed."""
    _setup_home(tmp_path, monkeypatch)

    info = _fake_info()
    monkeypatch.setattr(daemon_cmd._cli_client, "discover", lambda: info)
    monkeypatch.setattr(daemon_cmd, "pid_is_coffer_daemon", lambda pid: True)

    signals_sent: list[tuple[int, int]] = []

    def _fake_kill(pid: int, sig: int) -> None:
        signals_sent.append((pid, sig))

    monkeypatch.setattr(daemon_cmd.os, "kill", _fake_kill)
    monkeypatch.setattr(daemon_cmd, "_wait_for_daemon_json_gone", lambda path, timeout: True)

    daemon_cmd.stop()
    out = capsys.readouterr().out
    assert "daemon stopped" in out
    assert signals_sent == [(info.pid, signal.SIGTERM)]


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a recorded pid that is not ours is never signalled",
)
def test_daemon_stop_does_not_sigterm_an_unverified_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If the recorded pid is NOT a coffer daemon (PID recycled onto an
    unrelated process), stop() must NOT SIGTERM it. It cleans up the stale
    daemon.json instead and reports the mismatch."""
    home = _setup_home(tmp_path, monkeypatch)
    daemon_json = home / ".coffer" / "daemon.json"
    daemon_json.parent.mkdir(parents=True, exist_ok=True)
    daemon_json.write_text("{}")

    info = _fake_info()
    monkeypatch.setattr(daemon_cmd._cli_client, "discover", lambda: info)
    # The pid now belongs to some unrelated process.
    monkeypatch.setattr(daemon_cmd, "pid_is_coffer_daemon", lambda pid: False)

    def _must_not_kill(pid: int, sig: int) -> None:
        raise AssertionError("must NOT SIGTERM an unverified pid")

    monkeypatch.setattr(daemon_cmd.os, "kill", _must_not_kill)

    daemon_cmd.stop()
    out = capsys.readouterr().out
    assert "not a coffer daemon" in out.lower() or "stale" in out.lower()
    assert not daemon_json.exists(), "stale daemon.json must be cleaned up"


def test_daemon_stop_handles_already_gone_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If os.kill raises ProcessLookupError the stale daemon.json is removed
    and the CLI prints a tidy message."""
    home = _setup_home(tmp_path, monkeypatch)
    daemon_json = home / ".coffer" / "daemon.json"
    daemon_json.parent.mkdir(parents=True, exist_ok=True)
    daemon_json.write_text("{}")

    info = _fake_info()
    monkeypatch.setattr(daemon_cmd._cli_client, "discover", lambda: info)
    monkeypatch.setattr(daemon_cmd, "pid_is_coffer_daemon", lambda pid: True)

    def _gone(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(daemon_cmd.os, "kill", _gone)

    daemon_cmd.stop()
    out = capsys.readouterr().out
    assert "already exited" in out
    assert not daemon_json.exists()


def test_daemon_stop_emits_message_when_daemon_not_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When discover() returns None the CLI emits 'daemon not running' and
    exits with code 0."""
    _setup_home(tmp_path, monkeypatch)
    monkeypatch.setattr(daemon_cmd._cli_client, "discover", lambda: None)

    with pytest.raises(typer.Exit) as excinfo:
        daemon_cmd.stop()
    assert excinfo.value.exit_code == 0
    err = capsys.readouterr().err
    assert "daemon not running" in err


def test_daemon_stop_reports_failure_if_daemon_json_lingers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If the daemon never removes daemon.json after SIGTERM, stop() exits 1."""
    _setup_home(tmp_path, monkeypatch)
    monkeypatch.setattr(daemon_cmd._cli_client, "discover", lambda: _fake_info())
    monkeypatch.setattr(daemon_cmd, "pid_is_coffer_daemon", lambda pid: True)
    monkeypatch.setattr(daemon_cmd.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(daemon_cmd, "_wait_for_daemon_json_gone", lambda path, timeout: False)

    with pytest.raises(typer.Exit) as excinfo:
        daemon_cmd.stop()
    assert excinfo.value.exit_code == 1


# --------------------------------------------------------------------------- #
# _wait_for_daemon_json_*                                                      #
# --------------------------------------------------------------------------- #


def test_wait_for_daemon_json_gone_returns_true_when_absent(tmp_path: Path) -> None:
    p = tmp_path / "absent.json"
    assert daemon_cmd._wait_for_daemon_json_gone(p, timeout=0.01) is True


def test_wait_for_daemon_json_gone_returns_false_when_present(tmp_path: Path) -> None:
    p = tmp_path / "present.json"
    p.write_text("{}")
    assert daemon_cmd._wait_for_daemon_json_gone(p, timeout=0.01) is False
