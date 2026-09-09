"""bootstrap.superseded_by() — the self-eviction check (ADR-006 amendment).

``live_daemon()`` only ever probes the ONE port recorded in daemon.json, so it
cannot see a daemon alive on a different port: when the probe fails for any
reason (daemon.json lost, or an already-serving daemon too busy to answer
``/daemon/status`` inside the probe timeout) the spawn binds the next free port
and the older daemon keeps running forever. Ports 8000-8009 fill up one restart
at a time.

``superseded_by()`` closes that from the other end: each daemon periodically
asks whether daemon.json now names a DIFFERENT, LIVE Coffer daemon — if so it
is the orphan and evicts itself. It must never fire on an absent daemon.json
(deleting the file would otherwise kill the live daemon) nor on a recorded pid
that is dead or is not a Coffer daemon at all.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write


def _write_daemon_json(home: Path, *, pid: int, port: int = 8001) -> None:
    write(
        home / ".coffer" / "daemon.json",
        DaemonInfo(
            version=1,
            pid=pid,
            port=port,
            token="tok",
            started_at=datetime.now(tz=UTC),
            binary_path="/fake/coffer-daemon",
        ),
    )


def test_absent_daemon_json_never_evicts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A deleted daemon.json must not take the live daemon down with it."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert bootstrap.superseded_by() is None


def test_malformed_daemon_json_never_evicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / ".coffer" / "daemon.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert bootstrap.superseded_by() is None


def test_our_own_pid_is_not_a_supersession(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_daemon_json(tmp_path, pid=os.getpid())
    assert bootstrap.superseded_by() is None


def test_another_pid_that_is_not_a_live_daemon_is_not_a_supersession(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale daemon.json left by a crashed daemon must not evict us — we are
    still the only live daemon, and the next spawn will adopt or replace us."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_daemon_json(tmp_path, pid=os.getpid() + 1)
    monkeypatch.setattr(bootstrap, "pid_is_coffer_daemon", lambda _pid: False)
    assert bootstrap.superseded_by() is None


def test_another_live_daemon_supersedes_us(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_daemon_json(tmp_path, pid=os.getpid() + 1, port=8007)
    monkeypatch.setattr(bootstrap, "pid_is_coffer_daemon", lambda _pid: True)

    info = bootstrap.superseded_by()
    assert info is not None
    assert info.pid == os.getpid() + 1
    assert info.port == 8007


def test_liveness_probe_tolerates_a_busy_daemon() -> None:
    """The probe timeout must outlast a serving-but-busy daemon's slowest
    ``/daemon/status`` (measured at ~9s on a daemon still warming up), or the
    spawn concludes "nobody is live" and binds a second port. A stale
    daemon.json costs nothing here: a dead port refuses instantly rather than
    timing out."""
    assert bootstrap._LIVENESS_PROBE_TIMEOUT >= 10.0
