"""Each isolated-HOME builder produces a machine Coffer's own code resolves into."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from coffer.domain.agent.descriptor import AGENT_DESCRIPTORS
from coffer.domain.agent.scan import scan_locations
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.daemon.config import config_path
from coffer.infrastructure.knowledge.paths import knowledge_root
from tests.support.homes import (
    ROOT_PINS,
    FakeAgentDir,
    IsolatedHome,
    TwoMachineHomes,
    fake_agent_dir,
    make_home,
)

# --- one machine ------------------------------------------------------------


def test_isolated_home_is_where_coffer_resolves_its_trees(isolated_home: IsolatedHome) -> None:
    assert pathlib.Path.home() == isolated_home.root
    assert not any(name in os.environ for name in ROOT_PINS)
    assert knowledge_root() == isolated_home.knowledge_root
    assert config_path().parent == isolated_home.coffer_dir
    assert (isolated_home.root / ".gitconfig").is_file()


def test_isolated_home_env_runs_a_subprocess_as_that_machine(tmp_path: pathlib.Path) -> None:
    other = make_home(tmp_path / "other")  # built, not activated
    probe = (
        "import os, pathlib;print(pathlib.Path.home());print(os.environ.get('COFFER_LOG_DIR', '-'))"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe],
        env=other.env({"EXTRA": "1"}),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert out == [str(other.root), "-"]
    assert pathlib.Path.home() != other.root


# --- two machines and a remote ----------------------------------------------


def _git(home: IsolatedHome, *args: str, cwd: pathlib.Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=home.env(), capture_output=True, text=True, check=True
    ).stdout


def test_two_homes_share_only_the_remote(two_homes: TwoMachineHomes) -> None:
    a, b = two_homes.a, two_homes.b
    assert a.root != b.root and not a.root.is_relative_to(b.root)
    assert two_homes.remote_log() == []

    clone_a = a.root / "work"
    _git(a, "clone", two_homes.remote_url, str(clone_a))
    (clone_a / "note.md").write_text("from a\n", encoding="utf-8")
    _git(a, "add", "note.md", cwd=clone_a)
    _git(a, "commit", "-m", "a writes", cwd=clone_a)  # identity from a's own ~/.gitconfig
    _git(a, "push", "origin", f"HEAD:{two_homes.branch}", cwd=clone_a)

    clone_b = b.root / "work"
    _git(b, "clone", "-b", two_homes.branch, two_homes.remote_url, str(clone_b))
    assert (clone_b / "note.md").read_text(encoding="utf-8") == "from a\n"
    assert two_homes.remote_log() == ["a writes"]
    assert not (b.coffer_dir / "note.md").exists()


# --- agent config dirs ------------------------------------------------------


@pytest.mark.parametrize("agent_type", list(AGENT_DESCRIPTORS))
def test_default_agent_dir_is_the_one_the_descriptor_finds(
    isolated_home: IsolatedHome, agent_type: AgentType
) -> None:
    agent = fake_agent_dir(isolated_home, agent_type)
    descriptor = AGENT_DESCRIPTORS[agent_type]
    assert agent.is_default and agent.home_env() == {}
    assert agent.config_dir == descriptor.default_config_dir()
    assert agent.skills_dir == descriptor.default_skill_dir()
    assert agent.skills_dir.is_dir()
    assert scan_locations(agent_type, agent.config_dir)[0] == agent.skills_dir


def test_claude_global_config_sits_beside_the_default_dir(claude_code_dir: FakeAgentDir) -> None:
    home = claude_code_dir.home.root
    written = claude_code_dir.write("global", '{"mcpServers": {}}')
    assert written == home / ".claude.json"
    assert claude_code_dir.path("settings") == home / ".claude" / "settings.json"


def test_custom_claude_dir_keeps_global_config_inside_and_names_its_env(
    isolated_home: IsolatedHome,
) -> None:
    custom = isolated_home.root / "work-claude"
    agent = fake_agent_dir(
        isolated_home, AgentType.CLAUDE_CODE, config_dir=custom, files={"global": "{}"}
    )
    assert (custom / ".claude.json").read_text(encoding="utf-8") == "{}"
    assert not (isolated_home.root / ".claude.json").exists()
    assert agent.home_env() == {"CLAUDE_CONFIG_DIR": str(custom)}


def test_codex_dir_files_and_skills(codex_dir: FakeAgentDir) -> None:
    config = codex_dir.write("config", '[mcp_servers.x]\ncommand = "x"\n')
    assert config == codex_dir.home.root / ".codex" / "config.toml"
    skill = codex_dir.add_skill("mine")
    assert (skill / "SKILL.md").is_file()
    assert skill.parent in scan_locations(AgentType.CODEX, codex_dir.config_dir)
    with pytest.raises(KeyError, match="settings"):
        codex_dir.path("settings")
