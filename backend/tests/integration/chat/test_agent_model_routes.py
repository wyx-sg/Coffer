"""GET /api/v1/chat/agents/{agent_key}/models — the model catalogue route.

Wires the real route against the real ``AgentModelCatalogueService`` and the real
on-disk discovery adapter (only the spec-004 agent registry is faked), so the
whole chain from HTTP down to the agent's own ``.claude.json`` is exercised. The
regression it guards: Coffer used to offer a hardcoded three-model list and
users could not select the newest tier at all.
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
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.dependencies import get_agent_model_catalogue
from coffer.surfaces.http.dependencies import get_agent_registry
from tests.unit.chat.conftest import FakeAgentProvider

_TOKEN = "test-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}
_NOW = dt.datetime(2026, 9, 9, tzinfo=dt.UTC)


class _FakeAgents:
    def __init__(self, resources: list[Resource]) -> None:
        self._resources = resources

    async def list(self) -> list[Resource]:
        return list(self._resources)


def _agent_resource(config_dir: pathlib.Path) -> Resource:
    return Resource(
        id=1,
        kind="agent",
        name="cc",
        description=None,
        config={"type": "claude_code", "config_dir": str(config_dir)},
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
    app.include_router(conversation_router)
    app.dependency_overrides[get_agent_registry] = lambda: registry
    app.dependency_overrides[get_agent_model_catalogue] = lambda: catalogue
    return app


@pytest.fixture()
def client_no_agents() -> Generator[TestClient, None, None]:
    set_active_token(_TOKEN)
    with TestClient(_build_app(_FakeAgents([]))) as client:
        yield client


def test_curated_catalogue_includes_the_newest_alias(client_no_agents: TestClient) -> None:
    """With no agent registered the catalogue is the curated alias list — which
    must carry ``fable``, the tier users previously could not select at all."""
    resp = client_no_agents.get("/api/v1/chat/agents/claude_code/models", headers=_HEADERS)

    assert resp.status_code == 200, resp.text
    models = resp.json()["models"]
    assert [m["id"] for m in models] == ["fable", "opus", "opusplan", "sonnet", "haiku"]
    assert {m["source"] for m in models} == {"alias"}
    assert models[0]["label"] == "Fable"


def test_codex_catalogue(client_no_agents: TestClient) -> None:
    resp = client_no_agents.get("/api/v1/chat/agents/codex/models", headers=_HEADERS)

    assert resp.status_code == 200, resp.text
    assert [m["id"] for m in resp.json()["models"]] == ["gpt-5-codex", "gpt-5", "o3"]


def test_unknown_agent_key_is_404(client_no_agents: TestClient) -> None:
    resp = client_no_agents.get("/api/v1/chat/agents/no-such-agent/models", headers=_HEADERS)

    assert resp.status_code == 404, resp.text


def test_discovered_models_from_the_agents_own_config(tmp_path: pathlib.Path) -> None:
    """A model advertised by the registered agent's ``.claude.json`` appears
    after the curated aliases, tagged ``discovered``."""
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
        resp = client.get("/api/v1/chat/agents/claude_code/models", headers=_HEADERS)

    assert resp.status_code == 200, resp.text
    models = resp.json()["models"]
    assert [m["id"] for m in models[:5]] == ["fable", "opus", "opusplan", "sonnet", "haiku"]
    assert models[5] == {
        "id": "claude-fable-5-1[1m]",
        "label": "Fable",
        "description": "Fable 5.1 · Most capable",
        "source": "discovered",
    }
