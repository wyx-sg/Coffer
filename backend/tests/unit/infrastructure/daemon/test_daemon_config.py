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
    assert payload == {"port": 9123}


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


def test_a_file_from_an_older_build_keeps_its_keys_and_still_reads() -> None:
    """Every vault written before this build has a ``version`` key no reader
    ever consulted, plus whatever a newer build might add.

    Forward compatibility here is key-preservation, not a version gate: the
    file loads unchanged, and a write of one setting leaves the other keys —
    known, retired and unknown alike — exactly where they were.
    """
    path = daemon_config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "port": 9123, "machine_id": "mid", "from_the_future": 7})
    )

    assert daemon_config.read_fixed_port() == 9123
    assert daemon_config.read_cached_machine_id() == "mid"
    assert daemon_config.config_is_readable()

    daemon_config.write_machine_name("laptop")
    assert json.loads(path.read_text()) == {
        "version": 1,
        "port": 9123,
        "machine_id": "mid",
        "from_the_future": 7,
        "machine_name": "laptop",
    }
    assert daemon_config.read_machine_name() == "laptop"


# --- the idle window (spec daemon "Stand down after an idle window") --------
#
# Three states, not two, and the difference matters: absent means "the default
# applies", null means "the user turned it off", and those must not collapse.


def test_idle_window_defaults_when_nothing_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert daemon_config.read_idle_shutdown_hours() == daemon_config.DEFAULT_IDLE_SHUTDOWN_HOURS


def test_idle_window_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    daemon_config.write_idle_shutdown_hours(3)
    assert daemon_config.read_idle_shutdown_hours() == 3


def test_idle_window_can_be_turned_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicitly off — for a vault whose channels must answer at any hour —
    and distinguishable from never having been set."""
    monkeypatch.setenv("HOME", str(tmp_path))
    daemon_config.write_idle_shutdown_hours(None)
    assert daemon_config.read_idle_shutdown_hours() is None


def test_an_idle_window_too_short_to_mean_anything_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Below the floor the setting stops meaning "nobody is using it" and
    # starts meaning "pay a cold start for every quiet minute".
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(daemon_config.InvalidIdleShutdown):
        daemon_config.write_idle_shutdown_hours(0.01)


def test_a_nonsense_idle_window_in_the_file_falls_back_to_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Same rule the port follows: a hand-mangled config must not stop the
    # daemon, because an unbootable daemon cannot be repaired from the UI.
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".coffer").mkdir()
    (tmp_path / ".coffer" / "daemon-config.json").write_text('{"idle_shutdown_hours": "soon"}')
    assert daemon_config.read_idle_shutdown_hours() == daemon_config.DEFAULT_IDLE_SHUTDOWN_HOURS


def test_setting_the_idle_window_keeps_the_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One file, several settings: writing one must not drop another.
    monkeypatch.setenv("HOME", str(tmp_path))
    daemon_config.write_fixed_port(8123)
    daemon_config.write_idle_shutdown_hours(6)
    assert daemon_config.read_fixed_port() == 8123
    assert daemon_config.read_idle_shutdown_hours() == 6
