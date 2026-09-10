"""The supported agent types — exactly two, both fully faceted (FR-003)."""

from coffer.domain.agent.descriptor import AGENT_DESCRIPTORS
from coffer.domain.agent.types import AgentType


def test_exactly_two_supported_agent_types():
    assert [t.value for t in AgentType] == ["claude_code", "codex"]


def test_every_type_has_a_descriptor():
    assert set(AGENT_DESCRIPTORS) == set(AgentType)
