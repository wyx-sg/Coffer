"""Integration tests for bootstrap.release() — pid-checked unlink.

release() must only remove daemon.json when it still records OUR pid. An
orphaned daemon (one whose daemon.json was already clobbered by a racing
spawn) must NOT delete the *live* daemon's discovery file on its way out.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write


def _setup_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _info(pid: int, port: int = 8000) -> DaemonInfo:
    return DaemonInfo(
        version=1,
        pid=pid,
        port=port,
        token="tok",
        started_at=datetime.now(tz=UTC),
        binary_path="/fake/coffer-daemon",
    )


def test_release_unlinks_when_daemon_json_records_our_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _setup_home(tmp_path, monkeypatch)
    path = home / ".coffer" / "daemon.json"
    write(path, _info(os.getpid()))

    bootstrap.release()

    assert not path.exists(), "release() must remove our own daemon.json"


def test_release_preserves_daemon_json_owned_by_another_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An orphaned daemon (whose daemon.json was clobbered to point at the
    winner's pid) must NOT delete the live daemon's discovery file."""
    home = _setup_home(tmp_path, monkeypatch)
    path = home / ".coffer" / "daemon.json"
    # daemon.json now records a DIFFERENT pid (the live winner), not us.
    other_pid = os.getpid() + 1
    write(path, _info(other_pid, port=8123))

    bootstrap.release()

    assert path.exists(), "release() must not delete another daemon's daemon.json"
    from coffer.infrastructure.daemon.pid_lock import read

    assert read(path).pid == other_pid


def test_release_is_noop_when_daemon_json_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_home(tmp_path, monkeypatch)
    # Must not raise when there is nothing to remove.
    bootstrap.release()


def test_release_tolerates_malformed_daemon_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed daemon.json (can't read pid) is left in place rather than
    blindly unlinked — we only remove a file we can prove is ours."""
    home = _setup_home(tmp_path, monkeypatch)
    path = home / ".coffer" / "daemon.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json")

    bootstrap.release()

    assert path.exists(), "malformed daemon.json must not be unlinked by release()"
