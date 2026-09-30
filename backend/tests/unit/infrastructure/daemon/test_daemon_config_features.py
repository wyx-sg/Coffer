"""The ``features`` object of ``daemon-config.json``, and ``COFFER_FEATURES``."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.feature_settings import DaemonConfigFeatureSettings

_KNOWN = ("fake_a", "fake_b", "fake_c")


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _write_raw(payload: object) -> None:
    path = daemon_config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_no_file_means_no_settings() -> None:
    assert daemon_config.read_feature_settings() == {}


def test_write_keeps_the_other_settings_and_the_other_features() -> None:
    _write_raw({"port": 9123, "features": {"fake_b": False, "from_newer_build": True}})
    daemon_config.write_feature_setting("fake_c", True)
    payload = json.loads(daemon_config.config_path().read_text())
    assert payload == {
        "port": 9123,
        "features": {"fake_b": False, "from_newer_build": True, "fake_c": True},
    }
    assert daemon_config.read_feature_settings() == {
        "fake_b": False,
        "from_newer_build": True,
        "fake_c": True,
    }


def test_a_non_boolean_value_is_ignored_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    _write_raw({"features": {"fake_c": "yes", "fake_b": True}})
    with caplog.at_level(logging.WARNING):
        assert daemon_config.read_feature_settings() == {"fake_b": True}
    assert "fake_c" in caplog.text


def test_a_features_value_that_is_not_an_object_is_ignored() -> None:
    _write_raw({"features": ["fake_c"]})
    assert daemon_config.read_feature_settings() == {}
    daemon_config.write_feature_setting("fake_c", False)
    assert daemon_config.read_feature_settings() == {"fake_c": False}


def test_the_adapter_round_trips_through_the_file() -> None:
    adapter = DaemonConfigFeatureSettings()
    adapter.write("fake_a", True)
    assert adapter.read() == {"fake_a": True}
    assert json.loads(daemon_config.config_path().read_text()) == {"features": {"fake_a": True}}


def test_pins_parse_on_and_off() -> None:
    assert daemon_config.parse_feature_pins("fake_a=on, fake_c=OFF", _KNOWN) == {
        "fake_a": True,
        "fake_c": False,
    }


def test_no_pins_when_unset_or_empty() -> None:
    assert daemon_config.parse_feature_pins(None, _KNOWN) == {}
    assert daemon_config.parse_feature_pins(" , ", _KNOWN) == {}


def test_unknown_and_malformed_pins_are_skipped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        pins = daemon_config.parse_feature_pins(
            "workflow=on,fake_b,fake_c=maybe,fake_b=off", _KNOWN
        )
    assert pins == {"fake_b": False}
    assert "workflow" in caplog.text
    assert "fake_c=maybe" in caplog.text


def test_pins_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(daemon_config.FEATURES_ENV, "fake_b=off")
    assert daemon_config.read_feature_pins(_KNOWN) == {"fake_b": False}
