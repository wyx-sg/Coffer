"""One agent per type, named by it (spec agent-registry "Keep one agent per
type, named by it", "Report every supported type's detection state",
"Register each agent as an agent resource identified by its uid").

Through the full app: the type stands in for the uid on every
``/api/v1/agents/{uid}/...`` route — which ``resolve_agent_path``, a
router-level dependency, does by rewriting the path parameter before the route
reads it, so the sub-routes are exercised as well as the record itself — the
name, title and description cannot be set, every supported type is listed
whether added or not, and a moved directory keeps the uid.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ConfigValidationError
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.surfaces.http.agent_dependencies import get_agent_service, get_auto_detect_service
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.facets import agent_catalog, installed

TOKEN = "test-token-one-per-type"


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59940")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59949")
    # The types' own environment variables would name a second directory.
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return tmp_path


def _app() -> FastAPI:
    return create_app()


def _client_for(app: FastAPI) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _client() -> TestClient:
    return _client_for(_app())


def _register(c: TestClient, agent_type: str, config_dir: pathlib.Path) -> str:
    config_dir.mkdir(parents=True, exist_ok=True)
    r = c.post("/api/v1/agents", json={"type": agent_type, "config_dir": str(config_dir)})
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


@pytest.mark.acceptance(spec="agent-registry", scenario="address an agent by its type")
def test_address_an_agent_by_its_type(home: pathlib.Path) -> None:
    with _client() as c:
        uid = _register(c, "claude_code", home / ".claude")
        (home / ".claude" / "settings.json").write_text("{}", encoding="utf-8")

        for ref in ("claude-code", "claude_code", uid):
            r = c.get(f"/api/v1/agents/{ref}")
            assert r.status_code == 200, (ref, r.text)
            assert (r.json()["uid"], r.json()["name"]) == (uid, "claude-code"), ref

        # The sub-routes read the rewritten path parameter too: the type
        # answers exactly as the uid does.
        for sub in ("config-files", "coffer-connection"):
            by_uid = c.get(f"/api/v1/agents/{uid}/{sub}")
            by_type = c.get(f"/api/v1/agents/claude_code/{sub}")
            assert by_uid.status_code == 200, (sub, by_uid.text)
            assert by_type.status_code == 200, (sub, by_type.text)
            assert by_type.json() == by_uid.json(), sub

        # A write through the type lands on the same agent.
        patched = c.patch("/api/v1/agents/claude-code", json={"model": "opus"})
        assert patched.status_code == 200, patched.text
        assert c.get(f"/api/v1/agents/{uid}").json()["model"] == "opus"

        # A type with no agent registered reads as not found, on the record
        # and on its sub-routes alike.
        for path in ("/api/v1/agents/codex", "/api/v1/agents/codex/config-files"):
            missing = c.get(path)
            assert missing.status_code == 404, (path, missing.text)
            assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.acceptance(
    spec="agent-registry", scenario="an agent's name, title and description cannot be set"
)
def test_an_agents_name_title_and_description_cannot_be_set(home: pathlib.Path) -> None:
    with _client() as c:
        uid = _register(c, "claude_code", home / ".claude")

        renamed = c.patch(f"/api/v1/resources/{uid}", json={"name": "work-claude"})
        assert renamed.status_code == 409, renamed.text
        error = renamed.json()["error"]
        assert error["code"] == "NAME_IMMUTABLE"
        assert "is its type" in error["message"]

        titled = c.patch(f"/api/v1/resources/{uid}", json={"title": "Work laptop Claude"})
        assert titled.status_code == 422, titled.text

        # A description has no field to travel in on the agent's own update.
        c.patch(f"/api/v1/agents/{uid}", json={"description": "work box"})
        after = c.get(f"/api/v1/agents/{uid}").json()
        assert "description" not in after
        assert "title" not in after
        resource = c.get(f"/api/v1/resources/{uid}").json()
        assert (resource["name"], resource["title"]) == ("claude-code", None)
        assert not resource.get("description")

        # The generic create route never makes an agent at all (a lifecycle
        # kind); the registration below is the service-level half.
        refused = c.post(
            "/api/v1/resources",
            json={"kind": "agent", "name": "work-claude", "config": {"type": "claude_code"}},
        )
        assert refused.status_code >= 400, refused.text
        assert [a["name"] for a in c.get("/api/v1/agents").json()["items"]] == ["claude-code"]


@pytest.mark.acceptance(
    spec="agent-registry", scenario="an agent's name, title and description cannot be set"
)
async def test_registering_an_agent_under_another_name_is_refused(tmp_path) -> None:
    """The real agent kind derives the name from the type: registering it under
    any other name — even through the lifecycle path its own service uses — is
    a validation error, and so is a title."""
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    svc = ResourceService(
        kinds={"agent": make_agent_kind(on_delete=None)},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    config = {"type": "codex", "config_dir": str(tmp_path)}
    try:
        with pytest.raises(ConfigValidationError):
            await svc.register(
                kind="agent", name="work", config=config, actor="api", allow_lifecycle_kind=True
            )
        with pytest.raises(ConfigValidationError):
            await svc.register(
                kind="agent",
                name="codex",
                config=config,
                actor="api",
                allow_lifecycle_kind=True,
                title="Work Codex",
            )
        assert await svc.list(kind="agent") == []
        created = await svc.register(
            kind="agent", name="codex", config=config, actor="api", allow_lifecycle_kind=True
        )
        assert (created.name, created.title) == ("codex", None)
    finally:
        await engine.dispose()


@pytest.mark.acceptance(
    spec="agent-registry", scenario="list every supported type whether added or not"
)
def test_list_every_supported_type_whether_added_or_not(home: pathlib.Path) -> None:
    # Codex installed but never run: its program found, ~/.codex absent. The
    # probe answers from a fixed catalogue rather than the machine's PATH — a
    # real `codex --version` writes ~/.codex/tmp itself, which would turn the
    # state this scenario is about into `installed_active` mid-read.
    app = _app()
    with _client_for(app) as c:
        detect = AutoDetectService(
            agent_service=get_agent_service(),
            catalog=agent_catalog({AgentType.CODEX: installed("0.155.1")}),
        )
        app.dependency_overrides[get_auto_detect_service] = lambda: detect
        uid = _register(c, "claude_code", home / "claude-home")
        before = c.get("/api/v1/audit").json()["entries"]

        r = c.get("/api/v1/agents/types")
        assert r.status_code == 200, r.text
        rows = r.json()["types"]
        assert [row["type"] for row in rows] == ["claude_code", "codex"]
        claude, codex = rows

        assert (claude["uid"], claude["name"], claude["config_dir"], claude["addable"]) == (
            uid,
            "claude-code",
            str(home / "claude-home"),
            False,
        )
        assert codex["uid"] is None
        assert codex["name"] == "codex"
        assert (codex["state"], codex["version"]) == ("installed_never_run", "0.155.1")
        assert codex["config_dir"] == codex["standard_config_dir"] == str(home / ".codex")
        assert codex["addable"] is True
        for row in rows:
            assert {"display_name", "default_skill_dir", "other_config_dir"} <= set(row)

        # The read registered, created and audited nothing.
        assert [a["uid"] for a in c.get("/api/v1/agents").json()["items"]] == [uid]
        assert not (home / ".codex").exists()
        assert c.get("/api/v1/audit").json()["entries"] == before


@pytest.mark.acceptance(
    spec="agent-registry", scenario="keep an agent's uid while its directory moves"
)
def test_keep_an_agents_uid_while_its_directory_moves(home: pathlib.Path) -> None:
    with _client() as c:
        uid = _register(c, "codex", home / ".codex")
        moved = home / "codex-elsewhere"
        moved.mkdir()

        r = c.patch(f"/api/v1/agents/{uid}", json={"config_dir": str(moved)})
        assert r.status_code == 200, r.text

        for ref in (uid, "codex"):
            read = c.get(f"/api/v1/agents/{ref}")
            assert read.status_code == 200, (ref, read.text)
            body = read.json()
            assert (body["uid"], body["name"], body["config_dir"]) == (uid, "codex", str(moved))
