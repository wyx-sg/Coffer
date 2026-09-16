"""spec daemon FR-011 — the daemon binds one port, or it does not start.

The daemon has exactly one port: the one the user pinned, or 8000 when they
pinned none. There is no scan left on a user-facing start, so the two
behaviours worth pinning are the two the user experiences — the port does not
move between restarts, and when it cannot be had the daemon says so instead of
quietly turning up somewhere else.

The default is exercised through a monkeypatched ``DEFAULT_PORT`` rather than
against the real 8000: a developer's own Coffer daemon is usually sitting on
that port, and a test that fought it for ownership would fail for a reason that
has nothing to do with the code under test.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.port_alloc import PortInUse

# High, out of the way of both the real 8000 and the ranges other tests in this
# suite pin for themselves.
_FIXED_PORT = 59650
_HELD_PORT = 59651
_STAND_IN_DEFAULT = 59652


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # The env range is the test harness's override and outranks the configured
    # port by design, so these tests must run with it absent — otherwise they
    # would silently exercise the scan path they exist to distinguish from.
    monkeypatch.delenv("COFFER_PORT_RANGE_START", raising=False)
    monkeypatch.delenv("COFFER_PORT_RANGE_END", raising=False)
    return home


def _hold(port: int) -> socket.socket:
    """Squat ``port`` the way an unrelated dev server would."""
    squatter = socket.socket()
    squatter.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    squatter.bind(("127.0.0.1", port))
    squatter.listen(1)
    return squatter


@pytest.mark.acceptance(spec="daemon", scenario="a configured daemon port survives restarts")
def test_fixed_port_is_bound_on_every_start(_isolated_home: Path) -> None:
    """Two consecutive starts land on the same port — the one the user chose.

    A scan does the opposite (a second acquire() while the first still holds
    its port moves to the next one), so "same port twice" is exactly what
    separates the daemon's bind from the range override that remains for tests.
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
    spec="daemon",
    scenario="a port that is taken refuses to start and says what holds it",
)
def test_taken_fixed_port_refuses_to_start_with_an_actionable_message(
    _isolated_home: Path,
) -> None:
    daemon_config.write_fixed_port(_HELD_PORT)

    squatter = _hold(_HELD_PORT)
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
    # This port is not the default, so returning to the default is a real way
    # out and the message owes the user that option.
    assert "coffer daemon port clear" in message
    # Identifying the holder is best-effort (another user's process cannot be
    # inspected), but this one is ours, so it must be named.
    assert raised.value.holder is not None
    assert f"pid {raised.value.holder.pid}" in message

    # Nothing was published: a daemon that never bound must not leave a
    # daemon.json pointing at a port owned by whoever holds it.
    assert not (_isolated_home / ".coffer" / "daemon.json").exists()


def test_the_default_port_is_8000() -> None:
    """The number itself is the contract.

    A bookmark, the docs, and the browser localStorage keyed by this origin all
    name 8000; changing it is a user-visible break, not an implementation
    detail, so it is asserted here rather than only read from the constant.
    """
    assert daemon_config.DEFAULT_PORT == 8000


def test_no_configured_port_binds_the_default_and_never_scans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing configured the daemon takes 8000 — it does not go looking.

    This is the inversion ADR "The Desktop Shell Returns" asked for: the old
    behaviour scanned 8000-8009 here, which left the UI's origin free to drift
    between restarts and silently reset everything the browser keyed to it.
    """
    asked_for: list[int] = []

    def _fake_fixed(port: int) -> socket.socket:
        asked_for.append(port)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        return sock

    def _unexpected_scan(**kwargs: int) -> socket.socket:  # pragma: no cover - must not run
        raise AssertionError(f"bind_free_socket({kwargs}) called with no range override set")

    monkeypatch.setattr(bootstrap, "bind_fixed_socket", _fake_fixed)
    monkeypatch.setattr(bootstrap, "bind_free_socket", _unexpected_scan)

    sock = bootstrap._bind_port()
    sock.close()
    assert asked_for == [daemon_config.DEFAULT_PORT]


@pytest.mark.acceptance(spec="daemon", scenario="the daemon binds the same port every start")
def test_an_unconfigured_daemon_binds_the_default_on_every_start(
    _isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two starts, nothing configured, one port — and it is in daemon.json both times.

    This is the inversion itself. The old behaviour scanned 8000-8009 here, so
    a second start while anything held the first port landed somewhere else and
    the UI's origin moved with it — taking every preference the browser had
    keyed to that origin, with nothing on screen connecting the two events.

    ``DEFAULT_PORT`` is stood in for by a high port so the test does not have to
    win the real 8000 from the developer's own running daemon; what is under
    test is that the same number comes back twice, not which number it is.
    """
    monkeypatch.setattr(daemon_config, "DEFAULT_PORT", _STAND_IN_DEFAULT)
    assert daemon_config.read_fixed_port() is None
    daemon_json = _isolated_home / ".coffer" / "daemon.json"

    for _ in range(2):
        info, sock = bootstrap.acquire()
        try:
            assert sock.getsockname() == ("127.0.0.1", _STAND_IN_DEFAULT)
            assert info.port == _STAND_IN_DEFAULT
            # A bookmark only keeps working if the port every surface reads is
            # the one that was bound, so the file has to agree each time.
            assert json.loads(daemon_json.read_text())["port"] == _STAND_IN_DEFAULT
        finally:
            # Stand the daemon down before the next start, as a restart would.
            sock.close()


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a port that is taken refuses to start and says what holds it",
)
def test_a_held_default_port_refuses_to_start_with_nothing_configured(
    _isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal is not reserved for a port the user chose.

    Before the inversion this was the case that moved on quietly to the next
    port; it is now the same startup failure as a squatted fixed port, and has
    to carry the same diagnosis. ``coffer daemon port clear`` is deliberately
    NOT offered: nothing is configured, so it would change nothing.
    """
    monkeypatch.setattr(daemon_config, "DEFAULT_PORT", _STAND_IN_DEFAULT)
    assert daemon_config.read_fixed_port() is None

    squatter = _hold(_STAND_IN_DEFAULT)
    try:
        with pytest.raises(PortInUse) as raised:
            bootstrap.acquire()
    finally:
        squatter.close()

    message = str(raised.value)
    assert str(_STAND_IN_DEFAULT) in message
    assert raised.value.holder is not None
    assert f"pid {raised.value.holder.pid}" in message
    assert "coffer daemon port set" in message
    assert "coffer daemon port clear" not in message

    assert not (_isolated_home / ".coffer" / "daemon.json").exists()


def test_env_range_outranks_a_configured_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """The harness override wins, so a test run is hermetic on a machine whose
    real vault has a port fixed — and so concurrent test daemons do not all
    queue up for the one port a real start insists on."""
    daemon_config.write_fixed_port(_FIXED_PORT)
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59660")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59669")

    sock = bootstrap._bind_port()
    try:
        assert 59660 <= sock.getsockname()[1] <= 59669
    finally:
        sock.close()


def test_planned_port_is_what_the_next_start_will_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    """What the CLI's pre-flight asks, so it can never diagnose the wrong port.

    Under the range override there is no single port to check ahead of time,
    and saying so (``None``) is what keeps the pre-flight from refusing a test
    daemon's start over a port it was never going to touch.
    """
    assert bootstrap.planned_port() == daemon_config.DEFAULT_PORT

    daemon_config.write_fixed_port(_FIXED_PORT)
    assert bootstrap.planned_port() == _FIXED_PORT

    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59660")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59669")
    assert bootstrap.planned_port() is None
