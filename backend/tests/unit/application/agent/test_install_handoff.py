"""The prompt that hands installing an agent to the person while none is found
(spec web-ui "Hand installing an agent to the person when none is found")."""

from __future__ import annotations

import pytest

from coffer.application.agent.auto_detect import AgentTypeDetection
from coffer.application.agent.install_handoff import agent_install_handoff
from coffer.domain.agent.detection import DetectionState
from coffer.domain.agent.types import AgentType
from coffer.domain.handoff import STANDING_RULES


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


@pytest.mark.acceptance(
    spec="web-ui", scenario="with no agent found the install prompt is built by the daemon"
)
def test_with_no_agent_found_the_install_prompt_is_built_by_the_daemon() -> None:
    rows = [
        _row(AgentType.CLAUDE_CODE, "Claude Code", "~/.claude", DetectionState.MISSING),
        _row(AgentType.CODEX, "OpenAI Codex", "~/.codex", DetectionState.CONFIG_ONLY),
    ]
    prompt = agent_install_handoff(rows)
    assert prompt is not None
    assert prompt.startswith("Please install Claude Code or OpenAI Codex on this Mac")
    assert "~/.claude" in prompt and "~/.codex" in prompt
    assert "Scan again" in prompt
    # No installer is named: the assistant picks one for this machine.
    assert "brew" not in prompt and "npm" not in prompt and "curl" not in prompt
    for rule in STANDING_RULES:
        assert rule in prompt

    # Once one is installed there is nothing to hand over.
    rows[0] = _row(
        AgentType.CLAUDE_CODE, "Claude Code", "~/.claude", DetectionState.INSTALLED_NEVER_RUN
    )
    assert agent_install_handoff(rows) is None
    assert agent_install_handoff([]) is None
