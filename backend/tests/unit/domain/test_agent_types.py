"""Tests for AgentType default paths + detect markers + config dirs."""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.agent.types import AgentType


def test_display_names_present():
    for t in AgentType:
        assert t.display_name


def test_supported_types():
    assert {t.value for t in AgentType} == {
        "claude_code",
        "codex",
        "cursor",
        "opencode",
        "openclaw",
        "hermes",
    }


def test_default_skill_dir_returns_absolute_path():
    for t in AgentType:
        p = t.default_skill_dir()
        assert isinstance(p, pathlib.Path)
        assert p.is_absolute(), f"{t.value} default not absolute: {p}"


# OpenClaw nests its skills under workspace/skills, so its skill dir is two
# levels below the config dir; the rest deliver directly into <config>/skills.
_NESTED_SKILL_TYPES = {AgentType.OPENCLAW}


def test_detect_marker_is_config_dir():
    for t in AgentType:
        assert t.detect_marker() == t.config_dir()


def test_config_dir_is_skill_dir_root():
    for t in AgentType:
        assert t.config_dir() == t.detect_marker()
        if t not in _NESTED_SKILL_TYPES:
            assert t.config_dir() == t.default_skill_dir().parent
        else:
            # workspace/skills → the config dir is the grandparent.
            assert t.config_dir() == t.default_skill_dir().parent.parent


def test_default_skill_dir_basename_is_skills():
    for t in AgentType:
        assert t.default_skill_dir().name == "skills"


def test_openclaw_skill_dir_nests_under_workspace():
    assert list(AgentType.OPENCLAW.default_skill_dir().parts[-3:]) == [
        ".openclaw",
        "workspace",
        "skills",
    ]


@pytest.mark.parametrize(
    "t,expected_tail",
    [
        (AgentType.CLAUDE_CODE, [".claude", "skills"]),
        (AgentType.CODEX, [".codex", "skills"]),
    ],
)
def test_default_skill_dir_tails(t, expected_tail):
    p = t.default_skill_dir()
    assert list(p.parts[-2:]) == expected_tail


@pytest.mark.parametrize(
    "t,expected_tail",
    [
        (AgentType.CLAUDE_CODE, ".claude"),
        (AgentType.CODEX, ".codex"),
    ],
)
def test_config_dir_tails(t, expected_tail):
    assert t.config_dir().name == expected_tail


def test_config_dir_honours_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert AgentType.CLAUDE_CODE.config_dir() == tmp_path / ".claude"
    assert AgentType.CODEX.config_dir() == tmp_path / ".codex"
