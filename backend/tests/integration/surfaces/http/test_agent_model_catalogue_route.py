"""GET /api/v1/agent-providers/{agent_key}/models, from the agent registry's side.

The real route over the real ``AgentModelCatalogueService`` and the real
config-file discovery source; only the agent lister is a fake. The binary and
RPC sources are left out on purpose — they read an installed CLI, which would
make the answer differ between a laptop and CI; their own tests cover them.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.model_discovery import NativeConfigModelDiscovery
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.agent_provider_routes import router as agent_provider_router
from coffer.surfaces.http.chat.dependencies import get_agent_registry, get_model_catalog
from tests.unit.chat.conftest import FakeAgentProvider

_TOKEN = "test-token-agent-catalogue"
_HEADERS = {"X-Coffer-Token": _TOKEN}
_NOW = dt.datetime(2026, 9, 9, tzinfo=dt.UTC)


class _Agents:
    def __init__(self, resources: list[Resource]) -> None:
        self._resources = resources

    async def list(self) -> list[Resource]:
        return list(self._resources)


def _codex(config_dir: pathlib.Path) -> Resource:
    return Resource(
        id=1,
        uid="9a1b2c3d4e5f60718293a4b5c6d7e8f9",
        kind="agent",
        name="codex",
        description=None,
        config={"type": "codex", "config_dir": str(config_dir)},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _app(agents: _Agents) -> FastAPI:
    registry = AgentProviderRegistry()
    registry.register(FakeAgentProvider(None, agent_key="claude_code"), display_name="Claude Code")
    registry.register(FakeAgentProvider(None, agent_key="codex"), display_name="Codex")
    catalogue = AgentModelCatalogueService(agents=agents, discovery=NativeConfigModelDiscovery())
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_provider_router)
    app.dependency_overrides[get_agent_registry] = lambda: registry
    app.dependency_overrides[get_model_catalog] = lambda: catalogue
    return app


@pytest.mark.acceptance(spec="agent-registry", scenario="list the models an agent can be put on")
def test_catalogue_route_answers_per_agent_with_every_field(tmp_path: pathlib.Path) -> None:
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text('model = "local-codex-model"\n', encoding="utf-8")

    set_active_token(_TOKEN)
    with TestClient(_app(_Agents([_codex(config_dir)]))) as client:
        resp = client.get("/api/v1/agent-providers/codex/models", headers=_HEADERS)
        unknown = client.get("/api/v1/agent-providers/no-such-agent/models", headers=_HEADERS)

    assert resp.status_code == 200, resp.text
    models = resp.json()["models"]
    assert [m["id"] for m in models] == ["local-codex-model"]
    assert {"id", "label", "description", "efforts", "default_effort"} <= set(models[0])
    assert models[0]["efforts"] == []
    assert models[0]["default_effort"] is None
    assert unknown.status_code == 404, unknown.text
