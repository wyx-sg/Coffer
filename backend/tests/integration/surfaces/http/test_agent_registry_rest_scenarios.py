"""The agent registry's REST routes, one scenario each (spec agent-registry).

The management operations an agent has are REST routes and the Agents page; the
command line carries none. Each test boots ``create_app`` under a throwaway HOME
with a deterministic shim path and drives the route the scenario names, then
reads what landed in the agent's own files and in the audit log.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient as FastApiClient
from starlette.testclient import TestClient

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.domain.agent.model_catalogue import AgentModel
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.daemon import config as daemon_config
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http import feature_dependencies
from coffer.surfaces.http.agent_dependencies import get_agent_service, get_auto_detect_service
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.agent_provider_routes import router as agent_provider_router
from coffer.surfaces.http.chat.dependencies import get_agent_registry, get_model_catalog
from tests.support.facets import agent_catalog, installed
from tests.support.features import enable_all_in_config
from tests.unit.chat.conftest import FakeAgentProvider

_TOKEN = "test-token-agent-rest-scenarios"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[pathlib.Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59870")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59879")
    monkeypatch.delenv(daemon_config.FEATURES_ENV, raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    enable_all_in_config()
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    (tmp_path / ".coffer").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude").mkdir()
    prior = feature_dependencies._feature_service
    yield tmp_path
    feature_dependencies._feature_service = prior


def _client(app: FastAPI | None = None) -> TestClient:
    set_active_token(_TOKEN)
    return TestClient(app or create_app(), base_url="http://localhost", headers=_HEADERS)


def _register(c: TestClient, agent_type: str = "claude_code") -> str:
    r = c.post("/api/v1/agents", json={"type": agent_type})
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def _claude_json(home: pathlib.Path) -> dict[str, Any]:
    path = home / ".claude.json"
    return json.loads(path.read_text()) if path.is_file() else {}  # type: ignore[no-any-return]


def _audit_types(c: TestClient, uid: str) -> list[str]:
    r = c.get("/api/v1/audit", params={"resource_uid": uid, "limit": 200})
    assert r.status_code == 200, r.text
    return [e["event_type"] for e in r.json()["entries"]]


def _mcp_entries(c: TestClient, uid: str) -> dict[str, dict[str, Any]]:
    r = c.get(f"/api/v1/agents/{uid}/mcp-entries")
    assert r.status_code == 200, r.text
    return {e["name"]: e for e in r.json()["items"]}


def _add_direct_entry(home: pathlib.Path, name: str) -> None:
    data = _claude_json(home)
    data.setdefault("mcpServers", {})[name] = {"command": "uvx", "args": [f"{name}-server"]}
    (home / ".claude.json").write_text(json.dumps(data), encoding="utf-8")


# --- lifecycle ----------------------------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry", scenario="move an agent to a different config directory"
)
def test_move_an_agent_to_a_different_config_directory(home: pathlib.Path) -> None:
    other = home / "work-claude"
    other.mkdir()
    with _client() as c:
        uid = _register(c)
        before = c.get("/api/v1/agents/claude-code").json()
        assert before["config_dir"] == str(home / ".claude")

        r = c.patch("/api/v1/agents/claude-code", json={"config_dir": str(other)})
        assert r.status_code == 200, r.text

        after = c.get("/api/v1/agents/claude-code").json()
        assert after["config_dir"] == str(other)
        assert (after["uid"], after["name"]) == (uid, "claude-code")
        # The route carries no name, title or description to change.
        assert not {"title", "description"} & set(after)


@pytest.mark.acceptance(spec="agent-registry", scenario="refuse a title on the update route")
def test_refuse_a_title_on_the_update_route(home: pathlib.Path) -> None:
    with _client() as c:
        uid = _register(c)

        r = c.patch(f"/api/v1/resources/{uid}", json={"title": "Work laptop Claude"})
        assert r.status_code == 422, r.text

        shown = c.get("/api/v1/agents/claude-code").json()
        assert (shown["uid"], shown["name"]) == (uid, "claude-code")
        assert "title" not in shown
        assert c.get(f"/api/v1/resources/{uid}").json()["title"] is None


@pytest.mark.acceptance(spec="agent-registry", scenario="bind a model to an agent over REST")
def test_bind_a_model_to_an_agent_over_rest(home: pathlib.Path) -> None:
    with _client() as c:
        uid = _register(c)

        first = c.patch(
            f"/api/v1/agents/{uid}",
            json={"model": "opus", "tier_models": {"haiku": "claude-haiku-x"}},
        )
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["model"] == "opus"
        assert "effort" not in body
        assert body["tier_models"] == {"haiku": "claude-haiku-x"}
        assert "fast_model" not in body

        second = c.patch(f"/api/v1/agents/{uid}", json={"tier_models": None})
        assert second.status_code == 200, second.text
        assert second.json()["tier_models"] is None
        assert second.json()["model"] == "opus"


# --- Coffer connection --------------------------------------------------------


@pytest.mark.acceptance(spec="agent-registry", scenario="connect an agent to Coffer over REST")
def test_connect_an_agent_to_coffer_over_rest(home: pathlib.Path) -> None:
    with _client() as c:
        uid = _register(c)
        assert "coffer" not in _claude_json(home).get("mcpServers", {})

        r = c.post(f"/api/v1/agents/{uid}/coffer-connection")
        assert r.status_code == 200, r.text
        parts = {p["key"]: p["installed"] for p in r.json()["parts"]}
        assert parts["mcp"] is True
        assert _claude_json(home)["mcpServers"]["coffer"]["args"] == ["--agent-uid", uid]
        assert "agent_mcp_installed" in _audit_types(c, uid)


@pytest.mark.acceptance(spec="agent-registry", scenario="report the Coffer MCP status per agent")
def test_report_the_coffer_mcp_status_per_agent(home: pathlib.Path) -> None:
    (home / ".codex").mkdir()
    with _client() as c:
        connected = _register(c)
        bare = _register(c, "codex")
        assert c.post(f"/api/v1/agents/{connected}/coffer-connection").status_code == 200

        first = c.get(f"/api/v1/agents/{connected}/coffer-connection").json()
        second = c.get(f"/api/v1/agents/{bare}/coffer-connection").json()

        assert {p["key"]: p["installed"] for p in first["parts"]}["mcp"] is True
        assert second["state"] == "disconnected"
        for body in (first, second):
            assert "mcp" in {p["key"] for p in body["parts"]}
        assert {p["key"]: p["installed"] for p in second["parts"]}["mcp"] is False


@pytest.mark.acceptance(spec="agent-registry", scenario="disconnect an agent from Coffer over REST")
def test_disconnect_an_agent_from_coffer_over_rest(home: pathlib.Path) -> None:
    with _client() as c:
        uid = _register(c)
        assert c.post(f"/api/v1/agents/{uid}/coffer-connection").status_code == 200
        assert "coffer" in _claude_json(home)["mcpServers"]

        r = c.delete(f"/api/v1/agents/{uid}/coffer-connection")
        assert r.status_code == 200, r.text

        assert "coffer" not in _claude_json(home).get("mcpServers", {})
        assert c.get(f"/api/v1/agents/{uid}/coffer-connection").json()["state"] == "disconnected"


# --- config files -------------------------------------------------------------


# --- direct MCP entries -------------------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry", scenario="list an agent's direct MCP entries apart from Coffer's"
)
def test_list_an_agents_direct_mcp_entries_apart_from_coffers(home: pathlib.Path) -> None:
    with _client() as c:
        uid = _register(c)
        assert c.post(f"/api/v1/agents/{uid}/coffer-connection").status_code == 200
        _add_direct_entry(home, "github")

        entries = _mcp_entries(c, uid)

        assert entries["github"]["is_coffer"] is False
        assert entries["coffer"]["is_coffer"] is True
        assert [n for n, e in entries.items() if e["is_coffer"]] == ["coffer"]


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="remove a direct MCP entry over REST and refuse the coffer entry",
)
def test_remove_a_direct_mcp_entry_over_rest_and_refuse_the_coffer_entry(
    home: pathlib.Path,
) -> None:
    with _client() as c:
        uid = _register(c)
        assert c.post(f"/api/v1/agents/{uid}/coffer-connection").status_code == 200
        _add_direct_entry(home, "github")
        prior = (home / ".claude.json").read_text(encoding="utf-8")

        r = c.delete("/api/v1/agents/claude-code/mcp-entries/github")
        assert r.status_code == 204, r.text
        assert "github" not in _claude_json(home)["mcpServers"]
        backup = ConfigFileStore().latest_backup(home / ".claude.json")
        assert backup is not None and backup.read_text(encoding="utf-8") == prior
        assert "agent_mcp_entry_removed" in _audit_types(c, uid)

        kept = (home / ".claude.json").read_text(encoding="utf-8")
        refused = c.delete("/api/v1/agents/claude-code/mcp-entries/coffer")
        assert refused.status_code >= 400, refused.text
        assert (home / ".claude.json").read_text(encoding="utf-8") == kept


@pytest.mark.acceptance(spec="agent-registry", scenario="adopt a direct MCP entry under a new name")
def test_adopt_a_direct_mcp_entry_under_a_new_name(home: pathlib.Path) -> None:
    with _client() as c:
        uid = _register(c)
        _add_direct_entry(home, "github")
        made = c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "github",
                "config": {"transport": {"type": "stdio", "command": "other-cmd"}},
            },
        )
        assert made.status_code == 201, made.text

        r = c.post(
            "/api/v1/agents/claude-code/mcp-entries/github/adopt",
            json={"new_name": "github-work"},
        )
        assert r.status_code == 201, r.text
        assert (r.json()["kind"], r.json()["name"]) == ("mcp_server", "github-work")

        assert "github" not in _claude_json(home).get("mcpServers", {})
        names = {
            x["name"]
            for x in c.get("/api/v1/resources", params={"kind": "mcp_server"}).json()["resources"]
        }
        assert {"github", "github-work"} <= names
        assert "agent_mcp_entry_adopted" in _audit_types(c, uid)


# --- files, models -----------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry", scenario="report the absolute locations of an agent's files"
)
def test_report_the_absolute_locations_of_an_agents_files(home: pathlib.Path) -> None:
    project = home / ".claude" / "projects" / "-work-repo"
    (project / "memory").mkdir(parents=True)
    (project / "memory" / "fact.md").write_text("a fact", encoding="utf-8")
    with _client() as c:
        uid = _register(c)
        before = _audit_types(c, uid)

        files = c.get(f"/api/v1/agents/{uid}/config-files").json()["items"]
        stores = c.get(f"/api/v1/agents/{uid}/native-memory").json()["items"]

        settings = next(f for f in files if f["key"] == "settings")
        assert settings["path"] == str(home / ".claude" / "settings.json")
        assert stores[0]["memory_dir"] == str(project / "memory")
        assert not (home / ".claude" / "settings.json").exists()
        assert _audit_types(c, uid) == before


class _NoAgents:
    async def list(self) -> list[Any]:
        return []


class _Discovery:
    async def discover(
        self, *, agent_key: str, config_dir: pathlib.Path | None
    ) -> list[AgentModel]:
        if agent_key != "codex":
            return []
        return [
            AgentModel(id="gpt-big", label="GPT Big"),
            AgentModel(id="gpt-small", label="GPT Small"),
        ]


@pytest.mark.acceptance(spec="agent-registry", scenario="list an agent's models")
def test_list_an_agents_models() -> None:
    registry = AgentProviderRegistry()
    registry.register(FakeAgentProvider(None, agent_key="codex"), display_name="Codex")
    catalogue = AgentModelCatalogueService(agents=_NoAgents(), discovery=_Discovery())
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_provider_router)
    app.dependency_overrides[get_agent_registry] = lambda: registry
    app.dependency_overrides[get_model_catalog] = lambda: catalogue
    set_active_token(_TOKEN)
    with FastApiClient(app) as client:
        r = client.get("/api/v1/agent-providers/codex/models", headers=_HEADERS)
        unknown = client.get("/api/v1/agent-providers/no-such-agent/models", headers=_HEADERS)

    assert r.status_code == 200, r.text
    big, small = r.json()["models"]
    assert (big["id"], big["label"]) == ("gpt-big", "GPT Big")
    assert "efforts" not in big and "default_effort" not in big
    assert small["id"] == "gpt-small"
    assert unknown.status_code == 404, unknown.text


# --- discovery ----------------------------------------------------------------


def _with_detection(app: FastAPI, *programs: tuple[AgentType, str]) -> None:
    detect = AutoDetectService(
        agent_service=get_agent_service(),
        catalog=agent_catalog({kind: installed(version) for kind, version in programs}),
    )
    app.dependency_overrides[get_auto_detect_service] = lambda: detect


@pytest.mark.acceptance(spec="agent-registry", scenario="list discovery candidates over REST")
def test_list_discovery_candidates_over_rest(home: pathlib.Path) -> None:
    app = create_app()
    with _client(app) as c:
        _with_detection(app, (AgentType.CLAUDE_CODE, "2.1.0"))

        r = c.get("/api/v1/agents/candidates")

        assert r.status_code == 200, r.text
        claude = next(x for x in r.json()["candidates"] if x["type"] == "claude_code")
        assert claude["config_dir"] == str(home / ".claude")
        assert claude["state"] == "installed_active"
        assert claude["version"] == "2.1.0"
        assert c.get("/api/v1/agents").json()["items"] == []


@pytest.mark.acceptance(spec="agent-registry", scenario="register a discovered agent over REST")
def test_register_a_discovered_agent_over_rest(home: pathlib.Path) -> None:
    (home / ".codex").mkdir()
    app = create_app()
    with _client(app) as c:
        _with_detection(app, (AgentType.CODEX, "0.155.1"))

        listed = c.get("/api/v1/agents/candidates").json()["candidates"]
        codex = next(x for x in listed if x["type"] == "codex")
        assert codex["addable"] is True
        assert c.get("/api/v1/agents").json()["items"] == []

        r = c.post("/api/v1/agents", json={"type": "codex"})
        assert r.status_code == 201, r.text
        assert (r.json()["name"], r.json()["config_dir"]) == ("codex", str(home / ".codex"))
        assert "resource_created" in _audit_types(c, str(r.json()["uid"]))
        for operation in ("adopt", "discard"):
            assert c.post(f"/api/v1/agents/candidates/codex/{operation}").status_code >= 400


@pytest.mark.acceptance(spec="agent-registry", scenario="add an agent that has never run")
def test_add_an_agent_that_has_never_run(home: pathlib.Path) -> None:
    standard = home / ".codex"
    assert not standard.exists()
    app = create_app()
    with _client(app) as c:
        _with_detection(app, (AgentType.CODEX, "0.155.1"))

        listed = c.get("/api/v1/agents/candidates").json()["candidates"]
        codex = next(x for x in listed if x["type"] == "codex")
        assert codex["state"] == "installed_never_run"

        r = c.post("/api/v1/agents", json={"type": "codex"})
        assert r.status_code == 201, r.text
        assert [p.name for p in standard.iterdir()] == ["skills"]
        assert "resource_created" in _audit_types(c, str(r.json()["uid"]))


@pytest.mark.acceptance(
    spec="agent-registry", scenario="carry the install prompt on the type listing"
)
def test_carry_the_install_prompt_on_the_type_listing(home: pathlib.Path) -> None:
    app = create_app()
    with _client(app) as c:
        _with_detection(app, (AgentType.CODEX, "0.155.1"))

        rows = {row["type"]: row for row in c.get("/api/v1/agents/types").json()["types"]}

        claude_prompt = rows["claude_code"]["install_handoff"]["prompt"]
        assert "Claude Code" in claude_prompt
        assert rows["codex"]["install_handoff"] is None
