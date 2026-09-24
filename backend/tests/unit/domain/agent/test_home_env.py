"""The environment that points an agent's own runtime at its config directory.

Claude Code reads a config directory other than ``~/.claude`` only through
``CLAUDE_CONFIG_DIR``; Codex reads one other than ``~/.codex`` only through
``CODEX_HOME``. For the default directory nothing is set, so the spawned
process behaves exactly as it does when the user runs it themselves.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_claude_code_with_its_own_directory_names_it_in_claude_config_dir(
    home: pathlib.Path,
) -> None:
    custom = home / "work-claude"
    cfg = AgentConfig(type=AgentType.CLAUDE_CODE, config_dir=str(custom))

    assert cfg.runtime_env() == {"CLAUDE_CONFIG_DIR": str(custom)}


def test_codex_with_its_own_directory_names_it_in_codex_home(home: pathlib.Path) -> None:
    custom = home / "work-codex"
    cfg = AgentConfig(type=AgentType.CODEX, config_dir=str(custom))

    assert cfg.runtime_env() == {"CODEX_HOME": str(custom)}


@pytest.mark.parametrize("agent_type", [AgentType.CLAUDE_CODE, AgentType.CODEX])
def test_the_default_directory_sets_nothing(home: pathlib.Path, agent_type: AgentType) -> None:
    # Unset, and set explicitly to the standard location: both are the default.
    assert AgentConfig(type=agent_type).runtime_env() == {}
    explicit = AgentConfig(type=agent_type, config_dir=str(agent_type.config_dir()))
    assert explicit.runtime_env() == {}
