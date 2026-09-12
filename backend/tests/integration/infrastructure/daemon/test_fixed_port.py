"""spec mcp-gateway FR-028 — the daemon binds the port the user fixed, or none at all.

The point of the setting is a browser bookmark that keeps working, so the two
behaviours worth pinning are the two the user experiences: the port does not
move between restarts, and when it cannot be had the daemon says so instead of
quietly moving somewhere else.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.port_alloc import PortInUse

# High, out of the way of both the default 8000-8009 range and the ranges other
# tests in this suite pin for themselves.
_FIXED_PORT = 59650
_HELD_PORT = 59651


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # The env range is the test harness's override and outranks the fixed port
    # by design, so these tests must run with it absent — otherwise they would
    # silently exercise the scan path they exist to distinguish from.
    monkeypatch.delenv("COFFER_PORT_RANGE_START", raising=False)
    monkeypatch.delenv("COFFER_PORT_RANGE_END", raising=False)
    return home


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a fixed daemon port survives restarts")
def test_fixed_port_is_bound_on_every_start(_isolated_home: Path) -> None:
    """Two consecutive starts land on the same port — the one the user chose.

    The scan path deliberately does the opposite (a second acquire() while the
    first still holds its port moves to the next one), so "same port twice" is
    exactly what separates a fixed port from the old behaviour.
    """
    daemon_config.write_fixed_port(_FIXED_PORT)
    daemon_json = _isolated_home / ".coffer" / "daemon.json"

    for _ in range(2):
        info, sock = bootstrap.acquire()
        try:
            assert sock.getsockname() == ("127.0.0.1", _FIXED_PORT)
            assert info.port == _FIXED_PORT
            # Every Coffer surface reads the port out of daemon.json, so the
            # fixed port only holds if it is what lands there.
            assert json.loads(daemon_json.read_text())["port"] == _FIXED_PORT
        finally:
            # Stand the daemon down before the next start, as a restart would.
            sock.close()


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a fixed port that is taken refuses to start and says what holds it",
)
def test_taken_fixed_port_refuses_to_start_with_an_actionable_message(
    _isolated_home: Path,
) -> None:
    daemon_config.write_fixed_port(_HELD_PORT)

    squatter = socket.socket()
    squatter.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    squatter.bind(("127.0.0.1", _HELD_PORT))
    squatter.listen(1)
    try:
        with pytest.raises(PortInUse) as raised:
            bootstrap.acquire()
    finally:
        squatter.close()

    message = str(raised.value)
    assert str(_HELD_PORT) in message
    # It must not merely fail — it must leave the user able to act without
    # going looking for the commands.
    assert "coffer daemon port set" in message
    assert "coffer daemon port clear" in message
    # Identifying the holder is best-effort (another user's process cannot be
    # inspected), but this one is ours, so it must be named.
    assert raised.value.holder is not None
    assert f"pid {raised.value.holder.pid}" in message

    # Nothing was published: a daemon that never bound must not leave a
    # daemon.json pointing at a port owned by whoever holds it.
    assert not (_isolated_home / ".coffer" / "daemon.json").exists()


def test_no_fixed_port_still_scans_the_default_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing configured, the behaviour is exactly what it was before."""
    calls: dict[str, object] = {}

    def _fake_scan(*, start: int, end: int) -> socket.socket:
        calls["range"] = (start, end)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        return sock

    def _unexpected_fixed(port: int) -> socket.socket:  # pragma: no cover - must not run
        raise AssertionError(f"bind_fixed_socket({port}) called with no fixed port configured")

    monkeypatch.setattr(bootstrap, "bind_free_socket", _fake_scan)
    monkeypatch.setattr(bootstrap, "bind_fixed_socket", _unexpected_fixed)

    sock = bootstrap._bind_port()
    sock.close()
    assert calls["range"] == (8000, 8009)


def test_env_range_outranks_a_fixed_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """The harness override wins, so a test run is hermetic on a machine whose
    real vault has a port fixed."""
    daemon_config.write_fixed_port(_FIXED_PORT)
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59660")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59669")

    sock = bootstrap._bind_port()
    try:
        assert 59660 <= sock.getsockname()[1] <= 59669
    finally:
        sock.close()
