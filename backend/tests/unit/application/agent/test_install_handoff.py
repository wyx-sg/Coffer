"""The prompts that hand installing an agent's program to an agent (spec
agent-registry "Hand installing an agent's program to an agent"; spec web-ui
"Hand installing an agent to the person when none is found")."""

from __future__ import annotations

import pytest

from coffer.application.agent.auto_detect import AgentTypeDetection
from coffer.application.agent.install_handoff import (
    MachineFacts,
    agent_install_handoff,
    agent_program_handoff,
)
from coffer.domain.agent.detection import DetectionState
from coffer.domain.agent.types import AgentType
from coffer.domain.handoff import STANDING_RULES

FACTS = MachineFacts(machine="macOS 15.6, arm64", lookup_path="/opt/tools/bin:/usr/bin")
# No installer or package manager is named: the agent picks one for this machine.
INSTALLERS = ("brew", "npm", "curl", "pip", "install -g")


def _row(kind: AgentType, name: str, home: str, state: DetectionState) -> AgentTypeDetection:
    return AgentTypeDetection(
        type=kind,
        display_name=name,
        config_dir=home,
        standard_config_dir=home,
        default_skill_dir=f"{home}/skills",
        state=state,
        version=None,
    )


def _no_installer(prompt: str) -> None:
    for word in INSTALLERS:
        assert word not in prompt


@pytest.mark.acceptance(
    spec="web-ui", scenario="with no agent found the install prompt is built by the daemon"
)
def test_with_no_agent_found_the_install_prompt_is_built_by_the_daemon() -> None:
    rows = [
        _row(AgentType.CLAUDE_CODE, "Claude Code", "~/.claude", DetectionState.MISSING),
        _row(AgentType.CODEX, "OpenAI Codex", "~/.codex", DetectionState.CONFIG_ONLY),
    ]
    prompt = agent_install_handoff(rows, FACTS)
    assert prompt is not None
    assert prompt.startswith("Please install Claude Code or OpenAI Codex on this machine")
    assert "~/.claude" in prompt and "~/.codex" in prompt
    assert "macOS 15.6, arm64" in prompt and "/opt/tools/bin:/usr/bin" in prompt
    assert "Scan again" in prompt
    _no_installer(prompt)
    for rule in STANDING_RULES:
        assert rule in prompt

    # Once one is installed there is nothing to hand over.
    rows[0] = _row(
        AgentType.CLAUDE_CODE, "Claude Code", "~/.claude", DetectionState.INSTALLED_NEVER_RUN
    )
    assert agent_install_handoff(rows, FACTS) is None
    assert agent_install_handoff([], FACTS) is None


@pytest.mark.acceptance(
    spec="agent-registry", scenario="a type that is not installed carries its install prompt"
)
def test_a_type_that_is_not_installed_carries_its_install_prompt() -> None:
    prompt = agent_program_handoff(
        AgentType.CODEX,
        config_dir="/Users/me/.codex",
        state=DetectionState.MISSING,
        registered=False,
        facts=FACTS,
    )
    assert prompt is not None
    assert prompt.startswith("Please install OpenAI Codex on this machine")
    # The program Coffer looks for, the PATH it looks on, and how to confirm.
    assert "`codex`" in prompt and "`codex --version`" in prompt
    assert "/opt/tools/bin:/usr/bin" in prompt and "macOS 15.6, arm64" in prompt
    assert "/Users/me/.codex" in prompt
    assert "Leave signing in to OpenAI Codex to me." in prompt
    assert "Check again" in prompt
    _no_installer(prompt)
    for rule in STANDING_RULES:
        assert rule in prompt


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="an agent whose program is gone carries a reinstall prompt that keeps its folder",
)
def test_an_agent_whose_program_is_gone_carries_a_reinstall_prompt_keeping_its_folder() -> None:
    prompt = agent_program_handoff(
        AgentType.CLAUDE_CODE,
        config_dir="/Users/me/.claude",
        state=DetectionState.CONFIG_ONLY,
        registered=True,
        facts=FACTS,
    )
    assert prompt is not None
    assert prompt.startswith("Please reinstall Claude Code on this machine")
    assert "/Users/me/.claude already exists; keep it" in prompt
    assert "`claude --version`" in prompt
    _no_installer(prompt)

    # Registered, and its folder gone too: still a reinstall, and it says so.
    gone = agent_program_handoff(
        AgentType.CLAUDE_CODE,
        config_dir="/Users/me/.claude",
        state=DetectionState.MISSING,
        registered=True,
        facts=FACTS,
    )
    assert gone is not None and gone.startswith("Please reinstall Claude Code")
    assert "not there any more" in gone

    # A found program has nothing to hand over.
    for state in (DetectionState.INSTALLED_ACTIVE, DetectionState.INSTALLED_NEVER_RUN):
        assert (
            agent_program_handoff(
                AgentType.CLAUDE_CODE,
                config_dir="/Users/me/.claude",
                state=state,
                registered=True,
                facts=FACTS,
            )
            is None
        )
