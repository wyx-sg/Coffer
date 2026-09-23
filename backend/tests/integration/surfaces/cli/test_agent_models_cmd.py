"""Integration tests for ``coffer agent models <agent_key>``.

The CLI counterpart of the web model picker: it reads
``GET /api/v1/agent-providers/{agent_key}/models`` — the real route, with a
real provider registry, over the error handlers the daemon registers. Only the
catalogue behind the route is a stub, so the answer does not depend on which
agent CLIs this machine has installed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC
from datetime import datetime as dt

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.agent_provider_routes import router as agent_provider_router
from coffer.surfaces.http.chat.dependencies import get_agent_registry, get_model_catalog
from tests.unit.chat.conftest import FakeAgentProvider

_runner = CliRunner()
_TOKEN = "test-token-agent-models"


@dataclass(frozen=True)
class _Model:
    id: str
    label: str
    description: str = ""
    efforts: Sequence[str] = field(default_factory=tuple)
    default_effort: str | None = None


class _Catalogue:
    async def offered(self, agent_key: str) -> Sequence[_Model]:
        if agent_key == "codex":
            return [
                _Model(
                    id="gpt-5.5-codex",
                    label="GPT-5.5 Codex",
                    efforts=("low", "medium", "high"),
                    default_effort="medium",
                ),
                _Model(id="gpt-5.5-mini", label="gpt-5.5-mini"),
            ]
        return []


@pytest.fixture
def models_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = AgentProviderRegistry()
    registry.register(FakeAgentProvider(None, agent_key="codex"), display_name="Codex")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_provider_router)
    app.dependency_overrides[get_agent_registry] = lambda: registry
    app.dependency_overrides[get_model_catalog] = lambda: _Catalogue()
    set_active_token(_TOKEN)
    client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN},
        raise_server_exceptions=False,
    )
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=8000,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, info))


@pytest.mark.acceptance(spec="agent-registry", scenario="the command line lists an agent's models")
def test_models_lists_one_line_per_model_with_efforts(models_daemon: None) -> None:
    result = _runner.invoke(cli_app, ["agent", "models", "codex"])
    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 2
    first, second = lines
    # The label rides beside the id only when it says something the id does not.
    assert first.startswith("gpt-5.5-codex") and "GPT-5.5 Codex" in first
    # Effort levels in the agent's own order, the default one marked.
    assert "low, medium*, high" in first
    assert second.strip() == "gpt-5.5-mini"


def test_models_json_prints_the_route_response(models_daemon: None) -> None:
    result = _runner.invoke(cli_app, ["agent", "models", "codex", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "models": [
            {
                "id": "gpt-5.5-codex",
                "label": "GPT-5.5 Codex",
                "description": "",
                "efforts": ["low", "medium", "high"],
                "default_effort": "medium",
            },
            {
                "id": "gpt-5.5-mini",
                "label": "gpt-5.5-mini",
                "description": "",
                "efforts": [],
                "default_effort": None,
            },
        ]
    }


def test_unknown_agent_key_exits_not_found_with_the_message(models_daemon: None) -> None:
    result = _runner.invoke(cli_app, ["agent", "models", "no-such-agent"])
    assert result.exit_code == int(_cli_client.ExitCode.NOT_FOUND)
    assert "unknown agent: 'no-such-agent'" in result.output
