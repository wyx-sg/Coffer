"""GET /api/v1/agent-providers/{agent_key}/models — the model catalogue route.

Wires the real route against the real ``AgentModelCatalogueService`` and the real
on-disk discovery adapter (only the agent registry is faked), so the
whole chain from HTTP down to the agent's own ``.claude.json`` is exercised.

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
from coffer.infrastructure.agent.model_discovery import NativeConfigModelDiscovery
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.agent_provider_routes import router as agent_provider_router
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_agent_registry
from coffer.surfaces.http.turn_dependencies import get_agent_model_catalogue
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
        kind="agent",
        name=agent_type,
        description=None,
        config={"type": agent_type, "config_dir": str(config_dir)},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _build_app(agents: _FakeAgents) -> FastAPI:
    registry = AgentProviderRegistry()
    registry.register(FakeAgentProvider(None, agent_key="claude_code"), display_name="Claude Code")
    registry.register(FakeAgentProvider(None, agent_key="codex"), display_name="Codex")
    catalogue = AgentModelCatalogueService(agents=agents, discovery=NativeConfigModelDiscovery())

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_provider_router)
    app.dependency_overrides[get_agent_registry] = lambda: registry
    app.dependency_overrides[get_agent_model_catalogue] = lambda: catalogue
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
        }
    ]
