"""Unit tests for ``AgentModelCatalogueService`` — curated aliases merged with
whatever the agent's own config advertises.

Both collaborators are fakes: the agent lister stands in for the spec-004
registry, the discovery port for the on-disk read.
"""

from __future__ import annotations

import datetime as dt
import pathlib

from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.domain.agent.model_catalogue import AgentModel, curated_for
from coffer.domain.resource import Resource

_NOW = dt.datetime(2026, 9, 9, tzinfo=dt.UTC)


def _agent(name: str, agent_type: str, config_dir: str, *, enabled: bool = True) -> Resource:
    return Resource(
        id=1,
        kind="agent",
        name=name,
        description=None,
        config={"type": agent_type, "config_dir": config_dir},
        enabled=enabled,
        created_at=_NOW,
        updated_at=_NOW,
    )


class _FakeAgents:
    def __init__(self, resources: list[Resource]) -> None:
        self._resources = resources

    async def list(self) -> list[Resource]:
        return list(self._resources)


class _FakeDiscovery:
    """Records the config dir it was asked about and returns a canned list."""

    def __init__(self, models: list[AgentModel] | None = None) -> None:
        self.models = models or []
        self.seen: list[pathlib.Path] = []

    def discover(self, *, agent_key: str, config_dir: pathlib.Path) -> list[AgentModel]:
        self.seen.append(config_dir)
        return list(self.models)


class _RaisingDiscovery:
    def discover(self, *, agent_key: str, config_dir: pathlib.Path) -> list[AgentModel]:
        raise RuntimeError("config file exploded")


async def test_curated_only_when_no_agent_of_that_type_is_registered() -> None:
    discovery = _FakeDiscovery([AgentModel("never-read", source="discovered")])
    svc = AgentModelCatalogueService(agents=_FakeAgents([]), discovery=discovery)

    models = await svc.catalogue("claude_code")

    assert models == list(curated_for("claude_code"))
    # Nothing on disk to read without a registered agent — discovery is skipped.
    assert discovery.seen == []


async def test_curated_list_leads_with_the_newest_tier_alias() -> None:
    svc = AgentModelCatalogueService(agents=_FakeAgents([]), discovery=_FakeDiscovery())

    ids = await svc.suggest("claude_code")

    assert ids == ["fable", "opus", "opusplan", "sonnet", "haiku"]


async def test_discovered_models_append_after_curated_and_dedupe_by_id(
    tmp_path: pathlib.Path,
) -> None:
    discovery = _FakeDiscovery(
        [
            # Already curated — dropped so the curated label survives.
            AgentModel("opus", "Opus (cached)", source="discovered"),
            AgentModel("claude-fable-5-1[1m]", "Fable", "newest", source="discovered"),
            # Repeated within the discovered list — kept once.
            AgentModel("claude-fable-5-1[1m]", "Fable", "newest", source="discovered"),
        ]
    )
    svc = AgentModelCatalogueService(
        agents=_FakeAgents([_agent("cc", "claude_code", str(tmp_path))]),
        discovery=discovery,
    )

    models = await svc.catalogue("claude_code")

    assert [m.id for m in models] == [
        "fable",
        "opus",
        "opusplan",
        "sonnet",
        "haiku",
        "claude-fable-5-1[1m]",
    ]
    assert models[1].label == "Opus"  # curated wins the dedupe
    assert models[-1].source == "discovered"
    assert discovery.seen == [tmp_path]


async def test_disabled_agents_are_skipped(tmp_path: pathlib.Path) -> None:
    enabled_dir = tmp_path / "enabled"
    discovery = _FakeDiscovery()
    svc = AgentModelCatalogueService(
        agents=_FakeAgents(
            [
                _agent("off", "claude_code", str(tmp_path / "disabled"), enabled=False),
                _agent("on", "claude_code", str(enabled_dir)),
            ]
        ),
        discovery=discovery,
    )

    await svc.catalogue("claude_code")

    assert discovery.seen == [enabled_dir]


async def test_other_agent_types_do_not_supply_the_config_dir(tmp_path: pathlib.Path) -> None:
    codex_dir = tmp_path / "codex"
    discovery = _FakeDiscovery()
    svc = AgentModelCatalogueService(
        agents=_FakeAgents(
            [
                _agent("cc", "claude_code", str(tmp_path / "claude")),
                _agent("cx", "codex", str(codex_dir)),
            ]
        ),
        discovery=discovery,
    )

    ids = await svc.suggest("codex")

    assert discovery.seen == [codex_dir]
    assert ids == ["gpt-5-codex", "gpt-5", "o3"]


async def test_a_raising_discovery_degrades_to_the_curated_list(tmp_path: pathlib.Path) -> None:
    svc = AgentModelCatalogueService(
        agents=_FakeAgents([_agent("cc", "claude_code", str(tmp_path))]),
        discovery=_RaisingDiscovery(),
    )

    assert await svc.catalogue("claude_code") == list(curated_for("claude_code"))


async def test_unknown_agent_key_yields_an_empty_catalogue() -> None:
    svc = AgentModelCatalogueService(agents=_FakeAgents([]), discovery=_FakeDiscovery())

    assert await svc.catalogue("hermes") == []
    assert await svc.suggest("hermes") == []
