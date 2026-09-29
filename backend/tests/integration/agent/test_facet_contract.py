"""One facet contract, run against a fake config directory for every shipped
agent (ADR agent-mechanisms-are-optional-facets-on-the-descriptor).

Whatever an agent's facets are, they must honour the same promises: every
projection entry lands inside the agent's own directory through the
config-file allowlist; a provider projection round-trips (apply, detect,
remove) and leaves the user's own keys alone; the delivery hook installs,
finds and removes only Coffer's marked entry, and what it writes is what the
hooks reader reports as Coffer's own; the memory reader reads an empty
directory without failing; the driver and the probe name the agent they serve.
A new agent passes this file before it ships.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.detection import DetectionState, ProgramInfo, classify
from coffer.domain.agent.facets import AgentCatalog, AssetType
from coffer.domain.agent.hooks import parse_hooks
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.agent_projection import ProviderProjectionRequest
from tests.support.facets import agent_catalog
from tests.support.homes import FakeAgentDir, IsolatedHome, fake_agent_dir

_UID = "c0ffee00c0ffee00c0ffee00c0ffee00"


@pytest.fixture(params=list(AgentType), ids=lambda t: t.value)
def agent(request: pytest.FixtureRequest, isolated_home: IsolatedHome) -> FakeAgentDir:
    return fake_agent_dir(isolated_home, request.param)


@pytest.fixture
def catalog() -> AgentCatalog:
    return agent_catalog()


def _inside(path: pathlib.Path, home: IsolatedHome) -> bool:
    return home.root in path.parents


def test_every_projection_entry_lands_through_the_allowlist(
    agent: FakeAgentDir, catalog: AgentCatalog
) -> None:
    projection = catalog.projection(agent.agent_type)
    assert projection is not None
    for entry in projection.entries:
        if entry.config_key is not None:
            path = spec_for(agent.agent_type, entry.config_key, agent.config_dir).path
            assert path == agent.path(entry.config_key)
        else:
            assert entry.subpath is not None
            path = agent.config_dir / entry.subpath
            assert path.is_dir(), "a directory landing exists in a laid-out agent dir"
        assert _inside(path, agent.home)


def test_the_provider_projection_round_trips_and_keeps_user_keys(
    agent: FakeAgentDir, catalog: AgentCatalog
) -> None:
    facet = catalog.provider_projection(agent.agent_type)
    assert facet is not None
    entry = catalog.projection(agent.agent_type).entry(AssetType.PROVIDER)  # type: ignore[union-attr]
    assert entry is not None and entry.config_key == facet.config_key
    path = agent.path(facet.config_key)
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    request = ProviderProjectionRequest(
        connection_uid=_UID,
        connection_name="gw",
        base_url="https://gw.example/v1",
        model=None,
        fast_model=None,
        wire_api=None,
        text_models=("m-1",),
        coffer_cli="/opt/coffer/bin/coffer",
    )
    plan = facet.apply(original, request, path)
    for side in plan.before:
        assert side.path.parent == path.parent, "side files sit beside the main file"
    assert facet.is_present(plan.text)
    removed = facet.remove(plan.text, path)
    assert not facet.is_present(removed.text)
    assert not facet.is_present(original)


def test_the_delivery_hook_is_marked_and_read_back_as_coffers_own(
    agent: FakeAgentDir, catalog: AgentCatalog
) -> None:
    hook = catalog.delivery_hook(agent.agent_type)
    assert hook is not None
    assert agent.agent_type in (AgentType(hook.agent_type),)
    foreign = {"hooks": {hook.event: [{"hooks": [{"type": "command", "command": "other"}]}]}}
    path = agent.write(hook.config_key, json.dumps(foreign))
    installed = hook.install(path.read_text(encoding="utf-8"), _UID)
    assert hook.find_command(installed) == hook.command_for(_UID)
    rows = parse_hooks(installed)
    assert [r.command for r in rows if hook.is_coffer_command(r.command)] == [
        hook.command_for(_UID)
    ]
    assert "other" in [r.command for r in rows]
    assert hook.config_key in agent.descriptor.hook_source_keys, (
        "the file Coffer writes its hook into is one the hooks reader reads"
    )
    removed = hook.remove(installed)
    assert hook.find_command(removed) is None
    assert [r.command for r in parse_hooks(removed)] == ["other"]


def test_the_memory_reader_reads_an_empty_directory(
    agent: FakeAgentDir, catalog: AgentCatalog
) -> None:
    reader = catalog.memory_reader(agent.agent_type)
    assert reader is not None
    assert reader.agent_type == agent.agent_type.value
    assert reader.sources(str(agent.config_dir)) == ()


def test_the_driver_and_probe_name_the_agent_they_serve(
    agent: FakeAgentDir, catalog: AgentCatalog
) -> None:
    driver = catalog.driver(agent.agent_type)
    assert driver is not None and driver.agent_key == agent.agent_type.value
    assert driver.display_name
    probe = catalog.dependency_probe(agent.agent_type)
    assert probe is not None and probe.program == agent.descriptor.program


def test_detection_reads_the_laid_out_directory_as_installed_or_left_over(
    agent: FakeAgentDir,
) -> None:
    exists = agent.config_dir.is_dir()
    assert classify(ProgramInfo(path="/bin/x"), config_dir_exists=exists) is (
        DetectionState.INSTALLED_ACTIVE
    )
    assert classify(ProgramInfo(), config_dir_exists=exists) is DetectionState.CONFIG_ONLY
