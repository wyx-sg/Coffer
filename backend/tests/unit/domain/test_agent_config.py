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


def test_retired_follow_policy_keys_are_rejected() -> None:
    """The agent carries no skill-delivery policy any more (delivery is decided
    on the skill: ``enabled`` + ``scope``). ``extra="forbid"`` means a stored
    row still carrying either key fails to load — migration 0058 strips them,
    and no load-time shim tolerates them."""
    for key, value in (("follow_all_skills", False), ("skill_exclusions", ["x"])):
        with pytest.raises(ValidationError):
            AgentConfig.model_validate({"type": "codex", key: value})


def test_dump_carries_no_delivery_policy() -> None:
    dumped = AgentConfig(type=AgentType.CODEX).model_dump()
    assert "follow_all_skills" not in dumped
    assert "skill_exclusions" not in dumped
