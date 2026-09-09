"""The supported agent types — exactly two, both fully faceted (FR-003/FR-003a)."""

from coffer.domain.agent.descriptor import AGENT_DESCRIPTORS, native_memory_disable_target
from coffer.domain.agent.types import AgentType


def test_exactly_two_supported_agent_types():
    assert [t.value for t in AgentType] == ["claude_code", "codex"]


def test_every_type_has_a_descriptor():
    assert set(AGENT_DESCRIPTORS) == set(AgentType)


def test_every_type_can_disable_native_memory():
    for agent_type in AgentType:
        assert native_memory_disable_target(agent_type) is not None
