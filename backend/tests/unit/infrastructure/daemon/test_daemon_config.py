"""``~/.coffer/daemon-config.json`` — the one setting read before the DB exists.

Everything here turns on one rule: a config file that cannot be understood must
never stop the daemon from starting. The UI that would fix it is served BY the
daemon, so a refusal here is unrecoverable without a text editor. What an
unusable file falls back to is the default port — the same place clearing the
setting goes, since the daemon no longer has a "pick one for me" mode at all.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from coffer.infrastructure.daemon import config as daemon_config


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def test_no_file_means_the_default_port() -> None:
    """Nothing configured is not "choose for me" — it is 8000.

    ``read_fixed_port`` still answers None, because "the user pinned nothing"
    is a distinction the CLI's ``show`` needs to make; it is ``effective_port``
    that turns that into the number the daemon will bind.
    """
    assert daemon_config.read_fixed_port() is None
    assert daemon_config.effective_port() == daemon_config.DEFAULT_PORT
    assert daemon_config.config_is_readable()


def test_the_default_port_is_8000() -> None:
    """A bookmark and the browser state keyed to this origin both name it, so
    the number is part of the contract rather than a detail of the bind."""
    assert daemon_config.DEFAULT_PORT == 8000


def test_write_then_read_round_trips() -> None:
    daemon_config.write_fixed_port(9123)
    assert daemon_config.read_fixed_port() == 9123
    assert daemon_config.effective_port() == 9123
    payload = json.loads(daemon_config.config_path().read_text())
    assert payload == {"version": 1, "port": 9123}


def test_written_config_is_user_only() -> None:
    daemon_config.write_fixed_port(8000)
    mode = stat.S_IMODE(daemon_config.config_path().stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_clearing_returns_to_the_default_port() -> None:
    """Clearing is a return to 8000, not a return to the daemon choosing."""
    daemon_config.write_fixed_port(9123)
    daemon_config.write_fixed_port(None)
    assert daemon_config.read_fixed_port() is None
    assert daemon_config.effective_port() == daemon_config.DEFAULT_PORT


@pytest.mark.parametrize("port", [0, 80, 1023, 65536, 70000, -1])
def test_unbindable_ports_are_refused_at_the_boundary(port: int) -> None:
    """Below 1024 needs privileges the daemon does not have and must not gain,
    so accepting one would only defer a clear rejection into an unbindable port."""
    with pytest.raises(daemon_config.InvalidPort):
        daemon_config.write_fixed_port(port)
    assert not daemon_config.config_path().exists()


def test_malformed_file_falls_back_to_the_default_and_is_reported() -> None:
    path = daemon_config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json")
    # Falls back rather than raising: a daemon that refuses to boot over a
    # mangled config cannot be fixed from the UI it would have served.
    assert daemon_config.read_fixed_port() is None
    assert daemon_config.effective_port() == daemon_config.DEFAULT_PORT
    # ...but the surfaces can still tell the user there IS a broken file.
    assert not daemon_config.config_is_readable()


@pytest.mark.parametrize("value", ["8000", 8000.5, True, [8000], {"port": 8000}])
def test_non_integer_port_is_ignored(value: object) -> None:
    path = daemon_config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "port": value}))
    assert daemon_config.read_fixed_port() is None


def test_out_of_range_port_in_the_file_is_ignored() -> None:
    path = daemon_config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "port": 80}))
    assert daemon_config.read_fixed_port() is None
    assert daemon_config.effective_port() == daemon_config.DEFAULT_PORT
