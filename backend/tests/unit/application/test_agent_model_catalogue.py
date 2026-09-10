"""Unit tests for ``AgentModelCatalogueService``.

The service names no model of its own — it decides WHICH config dir discovery is
pointed at and dedupes what comes back. Both collaborators are fakes: the agent
lister stands in for the agent registry, the discovery port for the sources
that interrogate the installed CLIs.
"""

from __future__ import annotations

import datetime as dt
import pathlib

from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.domain.agent.model_catalogue import AgentModel
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
        self.seen: list[pathlib.Path | None] = []

    async def discover(
        self, *, agent_key: str, config_dir: pathlib.Path | None
    ) -> list[AgentModel]:
        self.seen.append(config_dir)
        return list(self.models)


class _RaisingDiscovery:
    async def discover(
        self, *, agent_key: str, config_dir: pathlib.Path | None
    ) -> list[AgentModel]:
        raise RuntimeError("the CLI exploded")


async def test_the_catalogue_is_whatever_discovery_reports(tmp_path: pathlib.Path) -> None:
    """No curated table sits in front of discovery any more — order and content
    both come from the agent."""
    discovery = _FakeDiscovery(
        [
            AgentModel("opus", source="alias"),
            AgentModel("claude-opus-9", "Opus 9", "Knowledge cutoff May 2026", source="discovered"),
        ]
    )
    svc = AgentModelCatalogueService(
        agents=_FakeAgents([_agent("cc", "claude_code", str(tmp_path))]), discovery=discovery
    )

    models = await svc.catalogue("claude_code")

    assert [(m.id, m.source) for m in models] == [
        ("opus", "alias"),
        ("claude-opus-9", "discovered"),
    ]
    assert models[1].label == "Opus 9"
    assert discovery.seen == [tmp_path]


async def test_discovery_still_runs_without_a_registered_agent() -> None:
    """The CLI can be installed without being registered as a managed agent, and
    the sources that read the binary answer either way — so discovery is asked
    with ``config_dir=None`` rather than skipped."""
    discovery = _FakeDiscovery([AgentModel("from-the-binary", source="alias")])
    svc = AgentModelCatalogueService(agents=_FakeAgents([]), discovery=discovery)

    assert await svc.suggest("claude_code") == ["from-the-binary"]
    assert discovery.seen == [None]


async def test_duplicate_ids_collapse_and_the_first_source_wins(tmp_path: pathlib.Path) -> None:
    discovery = _FakeDiscovery(
        [
            AgentModel("dup", "From the binary", source="discovered"),
            AgentModel("dup", "From the config", source="discovered"),
            AgentModel("other", source="discovered"),
        ]
    )
    svc = AgentModelCatalogueService(
        agents=_FakeAgents([_agent("cc", "claude_code", str(tmp_path))]), discovery=discovery
    )

    models = await svc.catalogue("claude_code")

    assert [(m.id, m.label) for m in models] == [("dup", "From the binary"), ("other", "")]


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

    await svc.suggest("codex")

    assert discovery.seen == [codex_dir]


async def test_a_raising_discovery_degrades_to_an_empty_catalogue(tmp_path: pathlib.Path) -> None:
    """A picker must never 500 because a CLI is odd today."""
    svc = AgentModelCatalogueService(
        agents=_FakeAgents([_agent("cc", "claude_code", str(tmp_path))]),
        discovery=_RaisingDiscovery(),
    )

    assert await svc.catalogue("claude_code") == []


async def test_an_agent_nothing_can_discover_yields_an_empty_catalogue() -> None:
    svc = AgentModelCatalogueService(agents=_FakeAgents([]), discovery=_FakeDiscovery())

    assert await svc.catalogue("hermes") == []
    assert await svc.suggest("hermes") == []
