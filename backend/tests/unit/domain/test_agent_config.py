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
    assert cfg.config_dir is None


def test_resolved_dirs_fall_back_to_type_default():
    cfg = AgentConfig(type=AgentType.CODEX)
    assert cfg.resolved_config_dir() == AgentType.CODEX.config_dir()
    # Skills are delivered to <config_dir>/skills.
    assert cfg.resolved_skill_dir() == AgentType.CODEX.config_dir() / "skills"


def test_resolved_dirs_use_config_dir_override(tmp_path):
    custom = tmp_path / "custom-cfg"
    custom.mkdir()
    cfg = AgentConfig(type=AgentType.CODEX, config_dir=str(custom))
    assert cfg.resolved_config_dir() == pathlib.Path(str(custom))
    assert cfg.resolved_skill_dir() == pathlib.Path(str(custom)) / "skills"


def test_config_dir_must_be_absolute():
    with pytest.raises(ValidationError):
        AgentConfig(type=AgentType.CLAUDE_CODE, config_dir="relative/path")


def test_config_dir_empty_rejected():
    with pytest.raises(ValidationError):
        AgentConfig(type=AgentType.CLAUDE_CODE, config_dir="   ")


def test_legacy_skill_dir_key_migrated_to_config_dir():
    """Older rows stored a now-removed ``skill_dir`` override. Loading them must
    succeed (extra="forbid") AND preserve the override by mapping it onto
    ``config_dir`` instead of silently reverting to the type default."""
    # A ``<dir>/skills`` override maps to config_dir=<dir> (same on-disk loc).
    cfg = AgentConfig.model_validate({"type": "claude_code", "skill_dir": "/data/team/skills"})
    assert cfg.type is AgentType.CLAUDE_CODE
    assert cfg.config_dir == "/data/team"
    assert cfg.resolved_skill_dir() == pathlib.Path("/data/team/skills")
    assert not hasattr(cfg, "skill_dir")

    # Any other custom dir becomes the config dir itself.
    cfg2 = AgentConfig.model_validate({"type": "codex", "skill_dir": "/data/custom"})
    assert cfg2.config_dir == "/data/custom"

    # An explicit config_dir wins over a legacy skill_dir if both are present.
    cfg3 = AgentConfig.model_validate(
        {"type": "claude_code", "config_dir": "/keep/me", "skill_dir": "/data/x/skills"}
    )
    assert cfg3.config_dir == "/keep/me"


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
