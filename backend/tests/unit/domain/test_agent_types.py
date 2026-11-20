"""The supported agent types (spec agent-registry "Support exactly the Claude
Code, Codex, Antigravity, Cursor, OpenCode and DeepSeek Harness agent types")."""

from coffer.domain.agent.descriptor import AGENT_DESCRIPTORS
from coffer.domain.agent.types import AgentType


def test_exactly_the_supported_agent_types():
    assert [t.value for t in AgentType] == [
        "claude_code",
        "codex",
        "antigravity",
        "cursor",
        "opencode",
        "deepseek_harness",
    ]


def test_every_type_has_a_descriptor():
    assert set(AGENT_DESCRIPTORS) == set(AgentType)
