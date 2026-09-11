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
    models: list[str] | None = None,
) -> Resource:
    return Resource(
        id=1,
        kind="agent",
        name=name,
        description=None,
        config={"type": agent_type, "config_dir": config_dir, "models": models or []},
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


# --- curation ----------------------------------------------------------------
#
# The catalogue an agent reports is cumulative and account-blind: it names models
# this account may not be entitled to run, and nothing local separates those from
# the ones that work. The user ticks the ones that work, and only PICKERS narrow
# to that set — the catalogue itself stays whole, because the curation screen has
# to render the models that are OFF as well as the ones that are on.

_THREE = [
    AgentModel("claude-opus-5", "Opus 5"),
    AgentModel("claude-mythos-5", "Mythos 5"),
    AgentModel("claude-haiku-4-5", "Haiku 4.5"),
]


async def test_an_uncurated_agent_is_offered_everything(tmp_path: pathlib.Path) -> None:
    """The out-of-the-box state. An empty set is "not curated yet", never
    "offer nothing" — someone who never opens the screen must still get a
    working picker."""
    svc = AgentModelCatalogueService(
        agents=_FakeAgents([_agent("cc", "claude_code", str(tmp_path))]),
        discovery=_FakeDiscovery(list(_THREE)),
    )

    assert [m.id for m in await svc.offered("claude_code")] == [m.id for m in _THREE]
    assert await svc.suggest("claude_code") == [m.id for m in _THREE]
    assert await svc.selection("claude_code") == []


async def test_a_curated_agent_offers_only_what_was_ticked(tmp_path: pathlib.Path) -> None:
    svc = AgentModelCatalogueService(
        agents=_FakeAgents(
            [
                _agent(
                    "cc",
                    "claude_code",
                    str(tmp_path),
                    models=["claude-haiku-4-5", "claude-opus-5"],
                )
            ]
        ),
        discovery=_FakeDiscovery(list(_THREE)),
    )

    # Catalogue order, not the order they were ticked in — the picker's order is
    # discovery's (newest first), and curation only removes.
    assert await svc.suggest("claude_code") == ["claude-opus-5", "claude-haiku-4-5"]


async def test_the_catalogue_itself_is_never_narrowed(tmp_path: pathlib.Path) -> None:
    """The curation screen renders ``catalogue()`` and ticks it against
    ``selection()``. If curation narrowed the catalogue too, a model could only
    ever be un-ticked once — never ticked back on."""
    svc = AgentModelCatalogueService(
        agents=_FakeAgents([_agent("cc", "claude_code", str(tmp_path), models=["claude-opus-5"])]),
        discovery=_FakeDiscovery(list(_THREE)),
    )

    assert [m.id for m in await svc.catalogue("claude_code")] == [m.id for m in _THREE]
    assert await svc.selection("claude_code") == ["claude-opus-5"]


async def test_a_curated_id_the_catalogue_dropped_is_simply_not_offered(
    tmp_path: pathlib.Path,
) -> None:
    """A CLI upgrade rewrites the catalogue under a stored selection. The
    catalogue is the truth about what exists; curation only narrows it."""
    svc = AgentModelCatalogueService(
        agents=_FakeAgents(
            [
                _agent(
                    "cc",
                    "claude_code",
                    str(tmp_path),
                    models=["claude-opus-5", "claude-opus-4-0"],
                )
            ]
        ),
        discovery=_FakeDiscovery(list(_THREE)),
    )

    assert await svc.suggest("claude_code") == ["claude-opus-5"]


async def test_the_curated_set_comes_from_the_same_agent_as_the_config_dir(
    tmp_path: pathlib.Path,
) -> None:
    """One resource answers for the type. A disabled agent feeds neither."""
    enabled_dir = tmp_path / "enabled"
    discovery = _FakeDiscovery(list(_THREE))
    svc = AgentModelCatalogueService(
        agents=_FakeAgents(
            [
                _agent(
                    "off",
                    "claude_code",
                    str(tmp_path / "disabled"),
                    enabled=False,
                    models=["claude-mythos-5"],
                ),
                _agent("on", "claude_code", str(enabled_dir), models=["claude-opus-5"]),
            ]
        ),
        discovery=discovery,
    )

    assert await svc.suggest("claude_code") == ["claude-opus-5"]
    assert await svc.selection_owner("claude_code") == "on"
    assert discovery.seen == [enabled_dir]


async def test_no_registered_agent_has_nowhere_to_hold_a_selection() -> None:
    """The set lives in an agent's config row. Without one there is no answer to
    read and no place for a writer to put one — and an unregistered agent is
    still offered everything its CLI reports."""
    svc = AgentModelCatalogueService(agents=_FakeAgents([]), discovery=_FakeDiscovery(list(_THREE)))

    assert await svc.selection("claude_code") == []
    assert await svc.selection_owner("claude_code") is None
    assert await svc.suggest("claude_code") == [m.id for m in _THREE]
