"""The SSE-session reaper's env knobs (CODE-022).

A mistyped knob used to be dropped silently, so an operator who set
``COFFER_MCP_SESSION_IDLE_S=5m`` got the default idle window and no hint why.
Now the raw value is named in a WARNING and the default still applies.
"""

from __future__ import annotations

import logging

import pytest

from coffer.surfaces.http.app_mcp_composition import reaper_kwargs_from_env

_IDLE = "COFFER_MCP_SESSION_IDLE_S"
_INTERVAL = "COFFER_MCP_SESSION_REAPER_INTERVAL_S"


def test_unset_knobs_leave_the_defaults_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_IDLE, raising=False)
    monkeypatch.delenv(_INTERVAL, raising=False)

    assert reaper_kwargs_from_env() == {}


def test_numeric_knobs_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_IDLE, "120")
    monkeypatch.setenv(_INTERVAL, "2.5")

    assert reaper_kwargs_from_env() == {"max_idle_seconds": 120.0, "interval_seconds": 2.5}


def test_an_unparsable_knob_is_logged_and_falls_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(_IDLE, "5m")
    monkeypatch.setenv(_INTERVAL, "30")

    with caplog.at_level(logging.WARNING, logger="coffer.surfaces.http.app_mcp_composition"):
        kwargs = reaper_kwargs_from_env()

    # The bad knob is dropped (so the reaper's own default applies); the good
    # one beside it is still honoured.
    assert kwargs == {"interval_seconds": 30.0}
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert _IDLE in warnings[0].getMessage()
    assert "'5m'" in warnings[0].getMessage(), "the raw value must be named"
