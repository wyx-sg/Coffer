"""Tests for AgentType default paths + detect markers."""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.agent.types import AgentType


def test_display_names_present():
    for t in AgentType:
        assert t.display_name


def test_default_skill_dir_returns_absolute_path():
    for t in AgentType:
        p = t.default_skill_dir()
        assert isinstance(p, pathlib.Path)
        assert p.is_absolute(), f"{t.value} default not absolute: {p}"


def test_detect_marker_is_parent_of_skill_dir():
    for t in AgentType:
        assert t.detect_marker() == t.default_skill_dir().parent


def test_default_skill_dir_basename_is_skills():
    for t in AgentType:
        # All four types' default skill_dir ends in `skills`.
        assert t.default_skill_dir().name == "skills"


@pytest.mark.parametrize(
    "t,expected_tail",
    [
        (AgentType.CLAUDE_CODE, [".claude", "skills"]),
        (AgentType.CURSOR, [".cursor", "skills"]),
        (AgentType.CODEX_CLI, [".codex", "skills"]),
    ],
)
def test_default_skill_dir_tails(t, expected_tail):
    p = t.default_skill_dir()
    assert list(p.parts[-2:]) == expected_tail


# ---------------------------------------------------------------------------
# TEST25-111 / TEST25-204 — claude_desktop branches per `sys.platform`
# ---------------------------------------------------------------------------


def test_claude_desktop_darwin_path(monkeypatch, tmp_path):
    """On macOS the default skill_dir lives under ~/Library/Application Support/Claude."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("sys.platform", "darwin")
    p = AgentType.CLAUDE_DESKTOP.default_skill_dir()
    assert list(p.parts[-4:]) == ["Library", "Application Support", "Claude", "skills"]
    assert str(p).startswith(str(tmp_path))


def test_claude_desktop_win32_path(monkeypatch, tmp_path):
    """On Windows the default skill_dir lives under %APPDATA%\\Claude."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setattr("sys.platform", "win32")
    p = AgentType.CLAUDE_DESKTOP.default_skill_dir()
    assert list(p.parts[-2:]) == ["Claude", "skills"]
    assert "Roaming" in str(p)


def test_claude_desktop_linux_path(monkeypatch, tmp_path):
    """On Linux the default skill_dir falls under ~/.config/Claude."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("sys.platform", "linux")
    p = AgentType.CLAUDE_DESKTOP.default_skill_dir()
    assert list(p.parts[-3:]) == [".config", "Claude", "skills"]


def test_appdata_fallback_when_env_unset(monkeypatch, tmp_path):
    """If %APPDATA% is unset, _appdata() falls back to HOME/AppData/Roaming."""
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("sys.platform", "win32")
    p = AgentType.CLAUDE_DESKTOP.default_skill_dir()
    # Tail must still resolve through the AppData/Roaming fallback.
    assert list(p.parts[-4:]) == ["AppData", "Roaming", "Claude", "skills"]
