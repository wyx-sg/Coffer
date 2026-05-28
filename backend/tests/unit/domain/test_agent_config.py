"""AgentConfig Pydantic validation."""

from __future__ import annotations

import pathlib

import pytest
from pydantic import ValidationError

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType


def test_minimum_fields():
    cfg = AgentConfig(type=AgentType.CLAUDE_CODE)
    assert cfg.type is AgentType.CLAUDE_CODE
    assert cfg.skill_dir is None
    assert cfg.auto_detected is False


def test_resolved_skill_dir_falls_back_to_default():
    cfg = AgentConfig(type=AgentType.CURSOR)
    assert cfg.resolved_skill_dir() == AgentType.CURSOR.default_skill_dir()


def test_resolved_skill_dir_uses_override(tmp_path):
    custom = tmp_path / "custom-skills"
    custom.mkdir()
    cfg = AgentConfig(type=AgentType.CURSOR, skill_dir=str(custom))
    assert cfg.resolved_skill_dir() == pathlib.Path(str(custom))


def test_skill_dir_must_be_absolute():
    with pytest.raises(ValidationError):
        AgentConfig(type=AgentType.CLAUDE_CODE, skill_dir="relative/path")


def test_skill_dir_empty_rejected():
    with pytest.raises(ValidationError):
        AgentConfig(type=AgentType.CLAUDE_CODE, skill_dir="   ")


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"type": "claude_code", "wat": "no", "auto_detected": False})


def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"type": "nonesuch"})
