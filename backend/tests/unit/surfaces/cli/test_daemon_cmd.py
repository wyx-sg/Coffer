"""TEST-018 — in-process unit tests for `coffer daemon` start/stop/status.

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

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli import daemon_cmd


def _setup_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
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

        def kill(self) -> None:  # not used on happy path
            pass

    def _fake_popen(cmd: list[str], **kwargs: Any) -> _FakeProc:
        popen_args["cmd"] = cmd
        popen_args["kwargs"] = kwargs
        # Simulate the child writing daemon.json synchronously so
        # _wait_for_daemon_json returns True immediately.
        daemon_json.write_text(json.dumps({"port": 9999, "token": "t", "pid": 4242, "version": 1}))
        return _FakeProc()

    monkeypatch.setattr(daemon_cmd.subprocess, "Popen", _fake_popen)

    daemon_cmd.start()
    out = capsys.readouterr().out
    assert "daemon started" in out
    assert popen_args["cmd"][1:] == ["-m", "coffer.infrastructure.daemon.entry"]


def test_daemon_start_short_circuits_when_already_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If daemon.json exists at start time, `daemon start` exits 0 with the
    'already running' notice without invoking Popen."""
    home = _setup_home(tmp_path, monkeypatch)
    daemon_json = home / ".coffer" / "daemon.json"
    daemon_json.parent.mkdir(parents=True, exist_ok=True)
    daemon_json.write_text("{}")

    invoked = {"popen": False}

    def _bad_popen(*args: Any, **kwargs: Any) -> None:
        invoked["popen"] = True
        raise AssertionError("Popen must not be invoked when daemon already running")

    monkeypatch.setattr(daemon_cmd.subprocess, "Popen", _bad_popen)

    with pytest.raises(typer.Exit) as excinfo:
        daemon_cmd.start()
    assert excinfo.value.exit_code == 0
    assert "already running" in capsys.readouterr().out
    assert invoked["popen"] is False


def test_daemon_start_fails_when_child_never_writes_daemon_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If the child never writes daemon.json within the timeout, start()
    calls Popen.kill() and exits 1 with a helpful stderr message."""
    _setup_home(tmp_path, monkeypatch)

    class _FakeProc:
        pid = 4243
        killed = False

        def kill(self) -> None:
            type(self).killed = True

    def _fake_popen(cmd: list[str], **kwargs: Any) -> _FakeProc:
        return _FakeProc()

    monkeypatch.setattr(daemon_cmd.subprocess, "Popen", _fake_popen)
    # Short-circuit the wait loop.
    monkeypatch.setattr(daemon_cmd, "_wait_for_daemon_json", lambda path, timeout: False)

    with pytest.raises(typer.Exit) as excinfo:
        daemon_cmd.start()
    assert excinfo.value.exit_code == 1
    assert _FakeProc.killed is True


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
        binary_path="/usr/bin/python3",
    )


def test_daemon_stop_sends_sigterm_and_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """stop() resolves discover() -> info, sends SIGTERM to info.pid, then
    waits for daemon.json to be removed."""
    _setup_home(tmp_path, monkeypatch)

    info = _fake_info()
    monkeypatch.setattr(daemon_cmd._cli_client, "discover", lambda: info)

    signals_sent: list[tuple[int, int]] = []

    def _fake_kill(pid: int, sig: int) -> None:
        signals_sent.append((pid, sig))

    monkeypatch.setattr(daemon_cmd.os, "kill", _fake_kill)
    monkeypatch.setattr(daemon_cmd, "_wait_for_daemon_json_gone", lambda path, timeout: True)

    daemon_cmd.stop()
    out = capsys.readouterr().out
    assert "daemon stopped" in out
    assert signals_sent == [(info.pid, signal.SIGTERM)]


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
    monkeypatch.setattr(daemon_cmd.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(daemon_cmd, "_wait_for_daemon_json_gone", lambda path, timeout: False)

    with pytest.raises(typer.Exit) as excinfo:
        daemon_cmd.stop()
    assert excinfo.value.exit_code == 1


# --------------------------------------------------------------------------- #
# _wait_for_daemon_json_*                                                      #
# --------------------------------------------------------------------------- #


def test_wait_for_daemon_json_returns_false_on_timeout(tmp_path: Path) -> None:
    p = tmp_path / "missing.json"
    assert daemon_cmd._wait_for_daemon_json(p, timeout=0.01) is False


def test_wait_for_daemon_json_returns_true_when_present(tmp_path: Path) -> None:
    p = tmp_path / "present.json"
    p.write_text("{}")
    assert daemon_cmd._wait_for_daemon_json(p, timeout=0.01) is True


def test_wait_for_daemon_json_gone_returns_true_when_absent(tmp_path: Path) -> None:
    p = tmp_path / "absent.json"
    assert daemon_cmd._wait_for_daemon_json_gone(p, timeout=0.01) is True


def test_wait_for_daemon_json_gone_returns_false_when_present(tmp_path: Path) -> None:
    p = tmp_path / "present.json"
    p.write_text("{}")
    assert daemon_cmd._wait_for_daemon_json_gone(p, timeout=0.01) is False
