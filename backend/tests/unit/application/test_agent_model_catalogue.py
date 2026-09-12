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


def _agent(
    name: str,
    agent_type: str,
    config_dir: str,
    *,
    enabled: bool = True,
) -> Resource:
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
            AgentModel("claude-opus-8", "Opus 4.8"),
            AgentModel("claude-opus-9", "Opus 9", "Knowledge cutoff May 2026"),
        ]
    )
    svc = AgentModelCatalogueService(
        agents=_FakeAgents([_agent("cc", "claude_code", str(tmp_path))]), discovery=discovery
    )

    models = await svc.catalogue("claude_code")

    assert [m.id for m in models] == ["claude-opus-8", "claude-opus-9"]
    assert models[1].label == "Opus 9"
    assert discovery.seen == [tmp_path]


async def test_discovery_still_runs_without_a_registered_agent() -> None:
    """The CLI can be installed without being registered as a managed agent, and
    the sources that read the binary answer either way — so discovery is asked
    with ``config_dir=None`` rather than skipped."""
    discovery = _FakeDiscovery([AgentModel("from-the-binary")])
    svc = AgentModelCatalogueService(agents=_FakeAgents([]), discovery=discovery)

    assert await svc.suggest("claude_code") == ["from-the-binary"]
    assert discovery.seen == [None]


async def test_duplicate_ids_collapse_and_the_first_source_wins(tmp_path: pathlib.Path) -> None:
    discovery = _FakeDiscovery(
        [
            AgentModel("dup", "From the binary"),
            AgentModel("dup", "From the config"),
            AgentModel("other"),
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


# --- what a picker is offered ------------------------------------------------
#
# Nothing on the AGENT narrows its catalogue: the agent answers "what can this
# agent be put on", full stop. Curation for an audience belongs to the surface
# that has one — a channel's allowed range (spec channels FR-071) — and this
# service knows nothing about it.

_THREE = [
    AgentModel("claude-opus-5", "Opus 5"),
    AgentModel("claude-mythos-5", "Mythos 5"),
    AgentModel("claude-haiku-4-5", "Haiku 4.5"),
]


async def test_an_agent_offers_its_whole_catalogue(tmp_path: pathlib.Path) -> None:
    """The only state there is now. What a picker shows is what the agent
    reports — a surface that wants less says so on its own side."""
    svc = AgentModelCatalogueService(
        agents=_FakeAgents([_agent("cc", "claude_code", str(tmp_path))]),
        discovery=_FakeDiscovery(list(_THREE)),
    )

    assert [m.id for m in await svc.offered("claude_code")] == [m.id for m in _THREE]
    assert await svc.suggest("claude_code") == [m.id for m in _THREE]


async def test_the_agent_resource_carries_no_model_curation(tmp_path: pathlib.Path) -> None:
    """``AgentConfig`` forbids extra keys, so a stored ``models`` key would fail
    to validate — and ``_agent()`` skipping it is not an oversight. This pins
    the retirement: there is no per-agent ticked set to read back."""
    from coffer.domain.agent.config import AgentConfig

    assert "models" not in AgentConfig.model_fields


async def test_an_unregistered_agent_is_still_offered_what_its_cli_reports() -> None:
    """Nothing here needs an agent ROW any more: discovery interrogates the
    installed CLI, and there is no stored set to look up alongside it."""
    svc = AgentModelCatalogueService(agents=_FakeAgents([]), discovery=_FakeDiscovery(list(_THREE)))

    assert await svc.suggest("claude_code") == [m.id for m in _THREE]


async def test_a_disabled_agent_does_not_answer_for_the_type(tmp_path: pathlib.Path) -> None:
    """One resource answers for a type, and a disabled one is not it — the user
    told Coffer to leave it alone, so its config dir must not feed discovery."""
    enabled_dir = tmp_path / "enabled"
    discovery = _FakeDiscovery(list(_THREE))
    svc = AgentModelCatalogueService(
        agents=_FakeAgents(
            [
                _agent("off", "claude_code", str(tmp_path / "disabled"), enabled=False),
                _agent("on", "claude_code", str(enabled_dir)),
            ]
        ),
        discovery=discovery,
    )

    assert await svc.suggest("claude_code") == [m.id for m in _THREE]
    assert discovery.seen == [enabled_dir]
