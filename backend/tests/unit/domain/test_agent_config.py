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


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"type": "claude_code", "wat": "no"})


@pytest.mark.parametrize(
    "dead_key, value",
    [
        ("skill_dir", "/data/team/skills"),
        ("auto_detected", True),
        ("disable_native_memory", False),
    ],
)
def test_removed_fields_are_rejected_not_tolerated(dead_key, value):
    """Each of these was a real field once, and each was carried by rows a
    migration has since rewritten (0005, 0056). The model used to tolerate them
    at load time on top of that; it no longer does, so the only way one reaches
    here is a config that never went through this database's migrations — an
    import bundle from an older build, which quarantines rather than corrupts.
    """
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"type": "claude_code", dead_key: value})


def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"type": "nonesuch"})


def test_follow_defaults_and_roundtrip() -> None:
    cfg = AgentConfig(type=AgentType.CODEX)
    assert cfg.follow_all_skills is True  # preserves pre-amendment auto-bind trust mode
    assert cfg.skill_exclusions == []
    cfg2 = AgentConfig.model_validate(
        {"type": "codex", "follow_all_skills": False, "skill_exclusions": ["frontend-slides"]}
    )
    assert cfg2.follow_all_skills is False
    assert cfg2.skill_exclusions == ["frontend-slides"]


def test_follow_fields_survive_model_dump() -> None:
    cfg = AgentConfig.model_validate({"type": "codex", "skill_exclusions": ["a"]})
    dumped = cfg.model_dump()
    assert dumped["follow_all_skills"] is True and dumped["skill_exclusions"] == ["a"]
