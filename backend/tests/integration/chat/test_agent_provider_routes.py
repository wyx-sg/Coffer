"""GET /api/v1/agent-providers/{agent_key}/models — the model catalogue route.

Wires the real route against the real ``AgentModelCatalogueService`` and the real
on-disk discovery adapter (only the agent registry is faked), so the
whole chain from HTTP down to the agent's own ``.claude.json`` is exercised.
The agent service reaches the route the way the composition root hands it
over: published as the chat kind's ``ModelCatalogPort``.

Only the config-file source is wired here, deliberately: the other two sources
read an installed CLI, which would make this test say different things on a
developer's laptop and on CI. Their own unit tests cover them against fixtures.

The regression it guards: Coffer used to answer this route from a list written
into its own source, which named models that did not exist on the machine and
omitted the ones that did.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.claude_effort import claude_effort_levels
from coffer.infrastructure.agent.model_discovery import NativeConfigModelDiscovery
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.agent_provider_routes import router as agent_provider_router
from coffer.surfaces.http.chat.dependencies import get_agent_registry, get_model_catalog
from tests.unit.chat.conftest import FakeAgentProvider

_TOKEN = "test-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}
_NOW = dt.datetime(2026, 9, 9, tzinfo=dt.UTC)


class _FakeAgents:
    def __init__(self, resources: list[Resource]) -> None:
        self._resources = resources

    async def list(self) -> list[Resource]:
        return list(self._resources)


def _agent_resource(config_dir: pathlib.Path, *, agent_type: str = "claude_code") -> Resource:
    return Resource(
        id=1,
        uid="5d1c9b3e7a2f4086b15c8e0d3f7a2b64",
        kind="agent",
        name=agent_type,
        description=None,
        config={"type": agent_type, "config_dir": str(config_dir)},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


class _FakeActiveConnection:
    """The provider kind narrowed to the one question the catalogue asks it.

    ``None`` = no active connection reaches this agent; ``[]`` = one is active
    but curates nothing; a list = exactly the ids ticked on its detail page.
    """

    def __init__(self, curated: list[str] | None) -> None:
        self._curated = curated

    async def curated_models(self, agent_key: str) -> list[str] | None:
        return None if self._curated is None else list(self._curated)


def _build_app(agents: _FakeAgents, curated: list[str] | None = None) -> FastAPI:
    registry = AgentProviderRegistry()
    registry.register(FakeAgentProvider(None, agent_key="claude_code"), display_name="Claude Code")
    registry.register(FakeAgentProvider(None, agent_key="codex"), display_name="Codex")
    catalogue = AgentModelCatalogueService(
        agents=agents,
        discovery=NativeConfigModelDiscovery(),
        provider_models=_FakeActiveConnection(curated),
    )

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_provider_router)
    app.dependency_overrides[get_agent_registry] = lambda: registry
    app.dependency_overrides[get_model_catalog] = lambda: catalogue
    return app


@pytest.fixture()
def client_no_agents() -> Generator[TestClient, None, None]:
    set_active_token(_TOKEN)
    with TestClient(_build_app(_FakeAgents([]))) as client:
        yield client


def test_no_registered_agent_means_nothing_to_read(client_no_agents: TestClient) -> None:
    """Coffer invents nothing: with no agent registered and only the config-file
    source wired, the route answers 200 with an empty catalogue rather than a
    list of names it made up."""
    resp = client_no_agents.get("/api/v1/agent-providers/claude_code/models", headers=_HEADERS)

    assert resp.status_code == 200, resp.text
    assert resp.json()["models"] == []


def test_codex_catalogue_comes_from_the_agents_own_config(tmp_path: pathlib.Path) -> None:
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        'model = "some-codex-model"\n\n[profiles.deep]\nmodel = "some-other-model"\n',
        encoding="utf-8",
    )

    set_active_token(_TOKEN)
    agents = _FakeAgents([_agent_resource(config_dir, agent_type="codex")])
    with TestClient(_build_app(agents)) as client:
        resp = client.get("/api/v1/agent-providers/codex/models", headers=_HEADERS)

    assert resp.status_code == 200, resp.text
    assert [m["id"] for m in resp.json()["models"]] == ["some-codex-model", "some-other-model"]


@pytest.mark.acceptance(spec="chat", scenario="an unknown agent is a missing path, not a bad turn")
def test_unknown_agent_key_is_404(client_no_agents: TestClient) -> None:
    resp = client_no_agents.get("/api/v1/agent-providers/no-such-agent/models", headers=_HEADERS)

    assert resp.status_code == 404, resp.text


def test_discovered_models_from_the_agents_own_config(tmp_path: pathlib.Path) -> None:
    """A model the registered agent cached in its own ``.claude.json`` reaches
    the wire verbatim, tagged ``discovered``."""
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    (tmp_path / ".claude.json").write_text(
        json.dumps(
            {
                "additionalModelOptionsCache": [
                    {
                        "value": "claude-fable-5-1[1m]",
                        "label": "Fable",
                        "description": "Fable 5.1 · Most capable",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    set_active_token(_TOKEN)
    with TestClient(_build_app(_FakeAgents([_agent_resource(config_dir)]))) as client:
        resp = client.get("/api/v1/agent-providers/claude_code/models", headers=_HEADERS)

    assert resp.status_code == 200, resp.text
    assert resp.json()["models"] == [
        {
            "id": "claude-fable-5-1[1m]",
            "label": "Fable",
            "description": "Fable 5.1 · Most capable",
            # Claude Code's reasoning levels come from the SDK that will run the
            # turn, not from a list written down here — asserted against that
            # same source so an SDK release adding a level is not a test failure.
            "efforts": list(claude_effort_levels()),
            # None on purpose: the SDK exposes no machine-readable default, and
            # a picker naming the wrong one is worse than one naming none.
            "default_effort": None,
        }
    ]


# --- the retired per-agent selection -----------------------------------------
#
# Model curation lives on the provider connection now (spec provider-switching
# "Curate the models a connection offers"), not on the agent. The agent answers
# one question — what can this agent be put on — and
# these pin that the second question no longer has a route to ask it from.


def _claude_json(tmp_path: pathlib.Path, *ids: str) -> pathlib.Path:
    """A ``.claude`` config dir whose sibling ``.claude.json`` names ``ids``."""
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    (tmp_path / ".claude.json").write_text(
        json.dumps({"additionalModelOptionsCache": [{"value": i} for i in ids]}),
        encoding="utf-8",
    )
    return config_dir


def test_the_selection_route_is_gone(tmp_path: pathlib.Path) -> None:
    """Neither verb answers any more: FastAPI has no such path at all, so both
    are 404 even with an agent of that type registered."""
    config_dir = _claude_json(tmp_path, "claude-opus-5", "claude-mythos-5")
    set_active_token(_TOKEN)

    with TestClient(_build_app(_FakeAgents([_agent_resource(config_dir)]))) as client:
        got = client.get("/api/v1/agent-providers/claude_code/models/selection", headers=_HEADERS)
        put = client.put(
            "/api/v1/agent-providers/claude_code/models/selection",
            headers=_HEADERS,
            json={"models": ["claude-opus-5"]},
        )

    assert got.status_code == 404, got.text
    assert put.status_code == 404, put.text


def test_the_catalogue_is_never_narrowed_by_anything_on_the_agent(
    tmp_path: pathlib.Path,
) -> None:
    """What the CLI reports is what the route answers. There is no stored
    ticked set left to subtract, so both models come back."""
    config_dir = _claude_json(tmp_path, "claude-opus-5", "claude-mythos-5")
    set_active_token(_TOKEN)

    with TestClient(_build_app(_FakeAgents([_agent_resource(config_dir)]))) as client:
        resp = client.get("/api/v1/agent-providers/claude_code/models", headers=_HEADERS)

    assert resp.status_code == 200, resp.text
    assert [m["id"] for m in resp.json()["models"]] == [
        "claude-opus-5",
        "claude-mythos-5",
    ]


# ---------------------------------------------------------------------------
# One list, everywhere.
#
# This route is what the web Chat page's model and effort pickers read; a
# channel's `/model` card reads `offered()` in-process. They must answer the
# same question, and they did not: the route served `catalogue()` — the agent's
# own login — so with a connection active the page offered models the endpoint
# would reject, while the chat card offered the curated ones.
#
# The harness above wires no provider layer by default, which is why every test
# written before this one passes either way: `catalogue()` and `offered()` agree
# exactly when no connection is active.
# ---------------------------------------------------------------------------


def _claude_agent_with_own_model(tmp_path: pathlib.Path) -> _FakeAgents:
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    (tmp_path / ".claude.json").write_text(
        json.dumps(
            {
                "additionalModelOptionsCache": [
                    {
                        "value": "claude-fable-5-1[1m]",
                        "label": "Fable",
                        "description": "Most capable",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return _FakeAgents([_agent_resource(config_dir)])


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="every surface offers the same models",
)
def test_an_active_curated_connection_replaces_the_agents_own_catalogue(
    tmp_path: pathlib.Path,
) -> None:
    """The curated ids ARE the list — the agent's own login is not mixed in.

    Mixing them offers ids the endpoint would reject: an active connection means
    the turns do not go to the account the agent's catalogue describes.
    """
    agents = _claude_agent_with_own_model(tmp_path)

    set_active_token(_TOKEN)
    with TestClient(_build_app(agents, curated=["gw/big", "gw/small"])) as client:
        resp = client.get("/api/v1/agent-providers/claude_code/models", headers=_HEADERS)

    assert resp.status_code == 200, resp.text
    ids = [m["id"] for m in resp.json()["models"]]
    assert ids == ["gw/big", "gw/small"], ids
    assert "claude-fable-5-1[1m]" not in ids, (
        "the agent's own model survived an active connection — that id does not "
        "exist on the endpoint the turns now go to"
    )


def test_an_id_the_agent_also_knows_keeps_its_reasoning_levels(tmp_path: pathlib.Path) -> None:
    """Levels are not the endpoint's to answer — they are a setting on the
    agent's own runtime, and the turn still goes through that runtime. So a
    curated id the agent also reports keeps its effort menu; the effort picker
    beside the model must not empty the moment a connection goes active."""
    agents = _claude_agent_with_own_model(tmp_path)

    set_active_token(_TOKEN)
    with TestClient(_build_app(agents, curated=["claude-fable-5-1[1m]", "gw/unknown"])) as client:
        resp = client.get("/api/v1/agent-providers/claude_code/models", headers=_HEADERS)

    by_id = {m["id"]: m for m in resp.json()["models"]}
    assert by_id["claude-fable-5-1[1m]"]["efforts"] == list(claude_effort_levels()), by_id
    assert by_id["gw/unknown"]["efforts"] == [], "an id the agent never heard of reports no levels"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="every surface offers the same models",
)
def test_a_connection_that_curates_nothing_falls_back_to_the_agents_catalogue(
    tmp_path: pathlib.Path,
) -> None:
    """``[]`` means "no restriction": Coffer knows where the turns go, not what
    that endpoint serves, and this read must not ask over the network."""
    agents = _claude_agent_with_own_model(tmp_path)

    set_active_token(_TOKEN)
    with TestClient(_build_app(agents, curated=[])) as client:
        resp = client.get("/api/v1/agent-providers/claude_code/models", headers=_HEADERS)

    assert [m["id"] for m in resp.json()["models"]] == ["claude-fable-5-1[1m]"]


def test_with_no_active_connection_the_agents_own_catalogue_is_the_list(
    tmp_path: pathlib.Path,
) -> None:
    """The built-in-login case, unchanged."""
    agents = _claude_agent_with_own_model(tmp_path)

    set_active_token(_TOKEN)
    with TestClient(_build_app(agents, curated=None)) as client:
        resp = client.get("/api/v1/agent-providers/claude_code/models", headers=_HEADERS)

    assert [m["id"] for m in resp.json()["models"]] == ["claude-fable-5-1[1m]"]
