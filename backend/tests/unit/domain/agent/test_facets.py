"""The facet ports on the descriptor and the projection registry (ADR
agent-mechanisms-are-optional-facets-on-the-descriptor)."""

from __future__ import annotations

import dataclasses

import pytest

from coffer.domain.agent.descriptor import AGENT_DESCRIPTORS
from coffer.domain.agent.detection import ProgramInfo
from coffer.domain.agent.facets import (
    AgentProjection,
    AssetType,
    Landing,
    ProjectionEntry,
    bind_facets,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.agent_projection import PROVIDER_PROJECTIONS
from tests.support.facets import agent_catalog


@dataclasses.dataclass(frozen=True)
class _Reader:
    agent_type: str


@dataclasses.dataclass(frozen=True)
class _Driver:
    agent_key: str
    display_name: str = "x"

    def build(self, deps: object) -> object:
        return deps


def test_the_pure_table_carries_no_mechanism() -> None:
    for d in AGENT_DESCRIPTORS.values():
        assert d.projection is None
        assert d.driver is None
        assert d.memory_reader is None
        assert d.dependency_probe is None


def test_binding_groups_implementations_by_the_agent_they_declare() -> None:
    catalog = bind_facets(
        AGENT_DESCRIPTORS,
        providers=PROVIDER_PROJECTIONS,
        drivers=[_Driver("codex")],
        memory_readers=[_Reader("claude_code")],
    )
    assert catalog.driver(AgentType.CODEX) == _Driver("codex")
    assert catalog.driver(AgentType.CLAUDE_CODE) is None
    assert catalog.memory_readers() == {"claude_code": _Reader("claude_code")}
    for d in catalog:
        provider = catalog.provider_projection(d.type)
        assert provider is not None and provider.agent_type == d.type


def test_two_implementations_for_one_agent_are_refused() -> None:
    with pytest.raises(ValueError, match="two driver implementations"):
        bind_facets(AGENT_DESCRIPTORS, drivers=[_Driver("codex"), _Driver("codex")])


def test_an_implementation_for_an_unknown_agent_is_refused() -> None:
    with pytest.raises(ValueError):
        bind_facets(AGENT_DESCRIPTORS, drivers=[_Driver("gemini_cli")])


def test_a_missing_facet_is_none_and_consumers_can_ask() -> None:
    catalog = bind_facets(AGENT_DESCRIPTORS)
    for d in catalog:
        assert catalog.driver(d.type) is None
        assert catalog.provider_projection(d.type) is None
        assert catalog.dependency_probe(d.type) is None


def test_an_agent_with_nothing_to_receive_has_no_projection_facet() -> None:
    bare = {
        t: dataclasses.replace(d, mcp=None, skill_subpath=None)  # type: ignore[arg-type]
        for t, d in AGENT_DESCRIPTORS.items()
    }
    catalog = bind_facets(bare)
    assert all(d.projection is None for d in catalog)


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_the_registry_lists_every_asset_the_shipped_agent_receives(agent_type: AgentType) -> None:
    projection = agent_catalog().projection(agent_type)
    assert projection is not None
    assets = [e.asset for e in projection.entries]
    assert assets == [
        AssetType.MCP_SERVER,
        AssetType.SKILL,
        AssetType.PROVIDER,
    ]
    # Every entry the shipped agents have lands in the agent's own directory,
    # in exactly one of a file or a directory.
    for entry in projection.entries:
        assert entry.landing is Landing.USER
        assert (entry.config_key is None) != (entry.subpath is None)


def test_registry_entries_name_the_file_each_asset_lands_in() -> None:
    catalog = agent_catalog()
    claude = catalog.projection(AgentType.CLAUDE_CODE)
    codex = catalog.projection(AgentType.CODEX)
    assert claude is not None and codex is not None
    assert claude.entry(AssetType.MCP_SERVER) == ProjectionEntry(
        AssetType.MCP_SERVER, Landing.USER, "global"
    )
    assert claude.entry(AssetType.PROVIDER) == ProjectionEntry(
        AssetType.PROVIDER, Landing.USER, "settings"
    )
    assert codex.entry(AssetType.PROVIDER) == ProjectionEntry(
        AssetType.PROVIDER, Landing.USER, "config"
    )
    assert codex.entry(AssetType.SKILL) == ProjectionEntry(
        AssetType.SKILL, Landing.USER, subpath="skills"
    )


def test_an_empty_projection_accepts_nothing() -> None:
    empty = AgentProjection()
    assert empty.entries == ()
    assert empty.entry(AssetType.MCP_SERVER) is None


def test_the_probe_is_built_from_the_record_program_name() -> None:
    seen: list[str] = []

    class _Probe:
        def __init__(self, program: str) -> None:
            self.program = program
            seen.append(program)

        def probe(self) -> ProgramInfo:
            return ProgramInfo()

    catalog = bind_facets(AGENT_DESCRIPTORS, probe_for=lambda d: _Probe(d.program))
    assert sorted(seen) == ["claude", "codex"]
    probe = catalog.dependency_probe(AgentType.CODEX)
    assert probe is not None and probe.program == "codex"
