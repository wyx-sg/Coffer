"""FR-003a: the machine-readable capability matrix mirrors the manifest."""

from coffer.domain.agent.capabilities import capabilities_for
from coffer.domain.agent.types import AgentType

# The expected matrix, straight from spec 004 FR-003a: plugins and transcript
# layouts exist upstream only for the two original agents; provider projection
# exists for every type except cursor (locked to Cursor's own backend).
_EXPECTED = {
    AgentType.CLAUDE_CODE: (True, True, True),
    AgentType.CODEX: (True, True, True),
    AgentType.OPENCODE: (False, False, True),
    AgentType.HERMES: (False, False, True),
    AgentType.CURSOR: (False, False, False),
    AgentType.OPENCLAW: (False, False, True),
}


def test_matrix_covers_every_type() -> None:
    assert set(_EXPECTED) == set(AgentType)


def test_capabilities_match_the_spec_matrix() -> None:
    for agent_type, (plugins, transcripts, connections) in _EXPECTED.items():
        caps = capabilities_for(agent_type)
        assert caps.plugins is plugins, agent_type
        assert caps.transcripts is transcripts, agent_type
        assert caps.connections is connections, agent_type
