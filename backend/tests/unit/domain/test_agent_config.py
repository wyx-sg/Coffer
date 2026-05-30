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


def test_resolved_skill_dir_falls_back_to_default():
    cfg = AgentConfig(type=AgentType.CODEX)
    assert cfg.resolved_skill_dir() == AgentType.CODEX.default_skill_dir()


def test_resolved_skill_dir_uses_override(tmp_path):
    custom = tmp_path / "custom-skills"
    custom.mkdir()
    cfg = AgentConfig(type=AgentType.CODEX, skill_dir=str(custom))
    assert cfg.resolved_skill_dir() == pathlib.Path(str(custom))


def test_skill_dir_must_be_absolute():
    with pytest.raises(ValidationError):
        AgentConfig(type=AgentType.CLAUDE_CODE, skill_dir="relative/path")


def test_skill_dir_empty_rejected():
    with pytest.raises(ValidationError):
        AgentConfig(type=AgentType.CLAUDE_CODE, skill_dir="   ")


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"type": "claude_code", "wat": "no"})


def test_legacy_auto_detected_key_tolerated():
    """Legacy rows stored a now-removed ``auto_detected`` flag. Loading them
    must succeed (the key is silently dropped) even though extra="forbid"."""
    cfg = AgentConfig.model_validate({"type": "claude_code", "auto_detected": False})
    assert cfg.type is AgentType.CLAUDE_CODE
    assert not hasattr(cfg, "auto_detected")
    cfg_true = AgentConfig.model_validate({"type": "codex", "auto_detected": True})
    assert cfg_true.type is AgentType.CODEX


def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"type": "nonesuch"})
