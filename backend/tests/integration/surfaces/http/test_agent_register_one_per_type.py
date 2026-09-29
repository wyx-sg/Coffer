"""POST /api/v1/agents under the one-agent-per-type rule (spec agent-registry).

Registration takes only the type (and optionally a directory). A type whose
program is installed but has never run here has no config directory yet, and
registering it at the standard location creates that directory; a second agent
of a registered type is refused, and nothing is written for it.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.detection import ProgramInfo
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.infrastructure.platform import HostPlatform
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.agent_dependencies import get_agent_service, get_auto_detect_service
from coffer.surfaces.http.agent_routes import router as agent_router
from coffer.surfaces.http.auth import set_active_token
from tests.support.facets import agent_catalog, installed

_TOKEN = "test-token-one-per-type"


@dataclass
class _Env:
    client: AsyncClient
    agents: AgentService
    audit: AuditService
    home: pathlib.Path


@pytest.fixture
def programs() -> dict[AgentType, ProgramInfo]:
    """Which programs the fake dependency probe reports on PATH: Codex only."""
    return {AgentType.CODEX: installed("0.155.1")}


@pytest.fixture
async def env(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    programs: Mapping[AgentType, ProgramInfo],
) -> AsyncIterator[_Env]:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={"agent": make_agent_kind(on_delete=None)},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    agents = AgentService(platform=HostPlatform(), resource_service=resources, audit=audit)
    detect = AutoDetectService(
        agent_service=agents, catalog=agent_catalog(programs), environ=lambda: {}
    )
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_router)
    app.dependency_overrides[get_agent_service] = lambda: agents
    app.dependency_overrides[get_auto_detect_service] = lambda: detect
    set_active_token(_TOKEN)
    client = AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    )
    try:
        async with client:
            yield _Env(client=client, agents=agents, audit=audit, home=home)
    finally:
        await engine.dispose()


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="register an installed agent whose config directory is not created yet",
)
async def test_an_installed_never_run_type_registers_and_creates_its_directory(env: _Env) -> None:
    standard = env.home / ".codex"
    assert not standard.exists()

    r = await env.client.post("/api/v1/agents", json={"type": "codex"})

    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["name"], body["type"], body["config_dir"]) == ("codex", "codex", str(standard))
    # The directory holds only what Coffer needs: its skills leaf.
    assert [p.name for p in standard.iterdir()] == ["skills"]
    assert (standard / "skills").is_dir()

    # A type whose program is NOT installed, on a missing directory, is refused
    # with nothing created and nothing persisted.
    claude = env.home / ".claude"
    refused = await env.client.post("/api/v1/agents", json={"type": "claude_code"})
    assert refused.status_code == 422, refused.text
    assert not claude.exists()
    assert [a.name for a in await env.agents.list()] == ["codex"]


async def test_a_missing_directory_other_than_the_standard_one_is_never_created(
    env: _Env,
) -> None:
    """Only the standard location of an installed-never-run type is created:
    a mistyped custom directory is refused even when the program is there."""
    elsewhere = env.home / "typo" / ".codex"
    r = await env.client.post(
        "/api/v1/agents", json={"type": "codex", "config_dir": str(elsewhere)}
    )
    assert r.status_code == 422, r.text
    assert not elsewhere.exists()
    assert not (env.home / ".codex").exists()
    assert await env.agents.list() == []


@pytest.mark.acceptance(
    spec="agent-registry", scenario="register a second agent of a registered type"
)
async def test_a_second_agent_of_a_registered_type_is_refused(env: _Env) -> None:
    standard = env.home / ".codex"
    standard.mkdir()
    first = await env.client.post("/api/v1/agents", json={"type": "codex"})
    assert first.status_code == 201, first.text
    uid = first.json()["uid"]
    other = env.home / "another"
    other.mkdir()

    for config_dir in (None, str(standard), str(other)):
        payload: dict[str, str] = {"type": "codex"}
        if config_dir is not None:
            payload["config_dir"] = config_dir
        r = await env.client.post("/api/v1/agents", json=payload)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "AGENT_TYPE_REGISTERED"

    # Nothing persisted, nothing created on disk for the refused registrations.
    assert list(other.iterdir()) == []
    [kept] = await env.agents.list()
    assert (kept.uid, kept.name) == (uid, "codex")
    created = await env.audit.query(event_type=AuditEventType.RESOURCE_CREATED.value)
    assert len(created) == 1
