"""Integration tests for bootstrap.live_daemon() — the detect-or-spawn duplicate guard.

live_daemon() returns the running daemon's info ONLY when daemon.json exists
AND a Coffer daemon answers /daemon/status on its recorded port; otherwise
None. We stub httpx so the test never needs a real daemon, while still pinning
that a foreign listener (non-200 / connection error) is NOT treated as live.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write


def _write_daemon_json(home: Path, port: int) -> None:
    write(
        home / ".coffer" / "daemon.json",
        DaemonInfo(
            version=1,
            pid=4242,
            port=port,
            token="tok",
            started_at=datetime.now(tz=UTC),
            binary_path="/fake/coffer-daemon",
        ),
    )


class _Resp:
    def __init__(self, status_code: int, body: object = None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> object:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body if self._body is not None else {"version": "x", "port": 8123}


def test_live_daemon_none_when_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    # No daemon.json → must short-circuit before any HTTP probe.
    monkeypatch.setattr(
        bootstrap.httpx,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not probe")),
    )
    assert bootstrap.live_daemon() is None


def test_live_daemon_returns_info_when_coffer_status_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_daemon_json(tmp_path, 8123)
    monkeypatch.setattr(bootstrap.httpx, "get", lambda *a, **k: _Resp(200))

    info = bootstrap.live_daemon()
    assert info is not None
    assert info.port == 8123


def test_live_daemon_none_when_foreign_listener_non_200(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-Coffer process squatting the recorded port answers non-200 (or
    not at all) → NOT a live daemon, so startup proceeds normally."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_daemon_json(tmp_path, 8123)
    monkeypatch.setattr(bootstrap.httpx, "get", lambda *a, **k: _Resp(404))
    assert bootstrap.live_daemon() is None


def test_live_daemon_none_when_connection_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing listening on the recorded port → httpx raises → None."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_daemon_json(tmp_path, 8123)

    def _boom(*_a: object, **_k: object) -> None:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(bootstrap.httpx, "get", _boom)
    assert bootstrap.live_daemon() is None


# --------------------------------------------------------------------------- #
# probe_status — the body behind live_daemon, for callers that read it         #
# --------------------------------------------------------------------------- #


def _info(port: int = 8123) -> DaemonInfo:
    return DaemonInfo(
        version=1,
        pid=4242,
        port=port,
        token="tok",
        started_at=datetime.now(tz=UTC),
        binary_path="/fake/coffer-daemon",
    )


def test_probe_status_returns_the_status_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bootstrap.httpx, "get", lambda *a, **k: _Resp(200, {"version": "9.9.9", "port": 8123})
    )
    assert bootstrap.probe_status(_info()) == {"version": "9.9.9", "port": 8123}


def test_probe_status_none_when_not_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap.httpx, "get", lambda *a, **k: _Resp(503, {"version": "x"}))
    assert bootstrap.probe_status(_info()) is None


def test_probe_status_none_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a: object, **k: object) -> object:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(bootstrap.httpx, "get", _boom)
    assert bootstrap.probe_status(_info()) is None


def test_probe_status_treats_a_200_with_no_json_object_as_live_but_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Liveness never hinges on the payload: a 200 is a live daemon even when
    the body is not a JSON object, and the caller gets nothing to compare."""
    monkeypatch.setattr(bootstrap.httpx, "get", lambda *a, **k: _Resp(200, ValueError("bad")))
    assert bootstrap.probe_status(_info()) == {}
    monkeypatch.setattr(bootstrap.httpx, "get", lambda *a, **k: _Resp(200, ["not", "a", "dict"]))
    assert bootstrap.probe_status(_info()) == {}
