"""The MCP server page's reads: status detail, 24 h summary, server log, tiering split.

Spec mcp-gateway "Explain a server's state on its page", "Read a server's own
log from its page", "Record invocations without content" and "Forward tools,
resources and prompts".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.capability import MCPInvocation
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.logging.files import upstream_log_path
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceStore,
    MCPInvocationRepo,
    MCPServerHealthRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas, session_maker
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_audit_service, get_resource_service
from coffer.surfaces.http.mcp.capability_routes import router as capability_router
from coffer.surfaces.http.mcp.dependencies import (
    get_health_repo,
    get_invocation_repo,
    get_preferences_repo,
)
from coffer.surfaces.http.mcp.page_routes import router as page_router
from coffer.surfaces.http.secret_composition import get_secret_store
from tests.support.vault_stores import derived_sm, make_resource_repo

NOW = datetime.now(tz=UTC)


class _Store:
    def __init__(self, present: set[str]) -> None:
        self.present = present
        self.asked: list[str] = []

    def exists(self, ref: str) -> bool:
        self.asked.append(ref)
        return ref in self.present


class _Ctx:
    def __init__(self, client, rsvc, prefs, invocations, store, health) -> None:
        self.client = client
        self.rsvc = rsvc
        self.prefs = prefs
        self.invocations = invocations
        self.store = store
        self.health = health

    async def server(self, name: str, config: dict[str, Any], *, enabled: bool = True):
        r = await self.rsvc.register(kind="mcp_server", name=name, config=config, actor="test")
        if not enabled:
            await self.rsvc.set_enabled(r.uid, False, actor="test")
        return r

    async def tools(self, resource, *names: str, seen: datetime = NOW, off: tuple = ()):
        for n in names:
            await self.prefs.insert(resource.uid, "tool", n, n not in off, seen, seen)

    async def call(self, uid: str, tool: str, status: str = "ok", *, ago: int = 60, **kw):
        await self.invocations.insert(
            MCPInvocation(
                id=None,
                timestamp=NOW - timedelta(seconds=ago),
                resource_uid=uid,
                capability_type="tool",
                capability_key=tool,
                duration_ms=5,
                status=status,  # type: ignore[arg-type]
                **kw,
            )
        )


def _stdio(**extra: Any) -> dict[str, Any]:
    return {"transport": {"type": "stdio", "command": "echo", "args": ["hi"], **extra}}


@pytest.fixture
async def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path / "logs"))
    for var in ("COFFER_TOOL_TIERING", "COFFER_TOOL_TIERING_BUDGET"):
        monkeypatch.delenv(var, raising=False)
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    kinds = {
        "mcp_server": Kind(
            name="mcp_server", display_name="MCP Server", config_schema=MCPServerConfig
        )
    }
    repo = make_resource_repo(kinds)
    rsvc = ResourceService(kinds=kinds, repo=repo, audit=audit)
    prefs = MCPCapabilityPreferenceStore(derived_sm())
    invocations = MCPInvocationRepo(sm, name_of=repo.name_of)
    health = MCPServerHealthRepo(derived_sm())
    store = _Store(set())
    set_active_token("tok")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(capability_router)
    app.include_router(page_router)
    app.dependency_overrides[get_resource_service] = lambda: rsvc
    app.dependency_overrides[get_audit_service] = lambda: audit
    app.dependency_overrides[get_preferences_repo] = lambda: prefs
    app.dependency_overrides[get_invocation_repo] = lambda: invocations
    app.dependency_overrides[get_health_repo] = lambda: health
    app.dependency_overrides[get_secret_store] = lambda: store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t", headers={"X-Coffer-Token": "tok"}
    ) as client:
        yield _Ctx(client, rsvc, prefs, invocations, store, health)
    await engine.dispose()


# --- status detail ------------------------------------------------------------


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a failing server says its last error and since when"
)
@pytest.mark.asyncio
async def test_a_failing_server_says_its_last_error_since_when_and_its_last_success(ctx):
    srv = await ctx.server("sentry", _stdio())
    await ctx.call(srv.uid, "list_issues", "ok", ago=600)
    await ctx.call(srv.uid, "get_issue", "error", ago=300, error_message="Connection refused")
    await ctx.call(srv.uid, "get_issue", "denied", ago=200)
    await ctx.call(srv.uid, "list_issues", "timeout", ago=100, error_message="timed out")
    r = await ctx.client.get(f"/api/v1/resources/mcp_server/{srv.uid}/status")
    body = r.json()
    assert body["status"] == "failing"
    assert body["last_error"] == "timed out"
    assert body["last_ok_capability"] == "list_issues"
    since = datetime.fromisoformat(body["failing_since"])
    last = datetime.fromisoformat(body["last_error_at"])
    assert last - since == timedelta(seconds=200)
    assert datetime.fromisoformat(body["last_ok_at"]) < since
    # A server that cites no secret never asks the store.
    assert body["missing_secret"] is None
    assert ctx.store.asked == []


@pytest.mark.asyncio
async def test_a_healthy_server_has_no_failure_detail(ctx):
    srv = await ctx.server("github", _stdio())
    await ctx.call(srv.uid, "create_pull_request", "ok")
    body = (await ctx.client.get(f"/api/v1/resources/mcp_server/{srv.uid}/status")).json()
    assert body["status"] == "healthy"
    assert body["last_error"] is None and body["failing_since"] is None


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a secret missing on this machine is named")
@pytest.mark.asyncio
async def test_a_secret_missing_on_this_machine_is_named_by_key_and_ref(ctx):
    config = {
        "transport": {
            "type": "http",
            "url": "https://mcp.linear.app/mcp",
            "secret_refs": {"Authorization": "LINEAR_API_KEY"},
        }
    }
    srv = await ctx.server("linear", config)
    body = (await ctx.client.get(f"/api/v1/resources/mcp_server/{srv.uid}/status")).json()
    assert body["missing_secret"] == "Authorization"
    assert body["missing_secret_ref"] == "LINEAR_API_KEY"
    ctx.store.present.add("LINEAR_API_KEY")
    body = (await ctx.client.get(f"/api/v1/resources/mcp_server/{srv.uid}/status")).json()
    assert body["missing_secret"] is None


@pytest.mark.asyncio
async def test_a_failed_test_with_no_calls_is_failing_since_the_test(ctx):
    srv = await ctx.server("docs", _stdio())
    await ctx.health.upsert(srv.uid, "failing", NOW)
    body = (await ctx.client.get(f"/api/v1/resources/mcp_server/{srv.uid}/status")).json()
    assert body["status"] == "failing"
    assert body["failing_since"] == body["last_checked_at"] is not None


# --- 24 h summary -------------------------------------------------------------


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a server's page reads its calls counted")
@pytest.mark.asyncio
async def test_the_summary_counts_calls_errors_by_agent_and_by_tool(ctx):
    srv = await ctx.server("github", _stdio())
    other = await ctx.server("other", _stdio())
    await ctx.call(srv.uid, "a", "ok", agent_uid="cc")
    await ctx.call(srv.uid, "a", "error", agent_uid="cc", error_message="x")
    await ctx.call(srv.uid, "b", "ok", agent_uid="codex")
    await ctx.call(srv.uid, "b", "ok")
    await ctx.call(srv.uid, "a", "ok", ago=3 * 24 * 3600)  # outside the window
    await ctx.call(other.uid, "a", "ok")
    body = (
        await ctx.client.get(f"/api/v1/resources/mcp_server/{srv.uid}/invocations/summary")
    ).json()
    assert (body["calls"], body["errors"]) == (4, 1)
    by_agent = {a["agent_uid"]: (a["calls"], a["errors"]) for a in body["by_agent"]}
    assert by_agent == {"cc": (2, 1), "codex": (1, 0), None: (1, 0)}
    by_tool = {t["tool"]: (t["calls"], t["errors"]) for t in body["by_tool"]}
    assert by_tool == {"a": (2, 1), "b": (2, 0)}
    assert body["last_call_at"] is not None


# --- server log ---------------------------------------------------------------


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a server's log tells Coffer's lines from the server's"
)
@pytest.mark.asyncio
async def test_the_server_log_reads_the_newest_lines_and_tells_coffer_from_stderr(ctx):
    srv = await ctx.server("duckdb", _stdio())
    path = upstream_log_path("duckdb")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".log.1").write_text("old stderr line\n")
    path.write_text(
        "2026-09-30T14:02:44+00:00 coffer start uvx mcp-server-duckdb\n"
        "Installed 14 packages\n"
        '2026-09-30T14:02:45+00:00 coffer error launcher "uvx" not found on PATH /usr/bin\n'
    )
    body = (await ctx.client.get(f"/api/v1/resources/mcp_server/{srv.uid}/log")).json()
    assert body["path"] == str(path)
    assert [(line["source"], line["text"]) for line in body["lines"]] == [
        ("coffer", 'error launcher "uvx" not found on PATH /usr/bin'),
        ("stderr", "Installed 14 packages"),
        ("coffer", "start uvx mcp-server-duckdb"),
        ("stderr", "old stderr line"),
    ]
    assert body["lines"][0]["at"].startswith("2026-09-30T14:02:45")
    limited = (
        await ctx.client.get(f"/api/v1/resources/mcp_server/{srv.uid}/log", params={"limit": 2})
    ).json()
    assert len(limited["lines"]) == 2 and limited["truncated"] is True


@pytest.mark.asyncio
async def test_an_http_server_has_no_server_log(ctx):
    srv = await ctx.server("figma", {"transport": {"type": "http", "url": "https://x.dev/mcp"}})
    body = (await ctx.client.get(f"/api/v1/resources/mcp_server/{srv.uid}/log")).json()
    assert body == {"path": None, "lines": [], "truncated": False}


# --- tiering split -------------------------------------------------------------


@pytest.mark.asyncio
async def test_under_budget_every_tool_is_listed(ctx):
    srv = await ctx.server("github", _stdio())
    await ctx.tools(srv, "a", "b", "c", off=("c",))
    body = (await ctx.client.get(f"/api/v1/resources/mcp_server/{srv.uid}/tiering")).json()
    assert body["enabled"] is True
    assert body["tool_count"] == 3
    assert body["listed"] == ["a", "b"] and body["behind_search"] == []
    assert body["catalogue_size"] == body["listed_count"] == 2


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a server's page reads its tiering split")
@pytest.mark.asyncio
async def test_over_budget_the_least_used_tools_are_behind_search(ctx, monkeypatch):
    monkeypatch.setenv("COFFER_TOOL_TIERING_BUDGET", "3")
    big = await ctx.server("smart", _stdio())
    small = await ctx.server("github", _stdio())
    off = await ctx.server("postgres", _stdio(), enabled=False)
    await ctx.tools(big, "t1", "t2", "t3", "t4")
    await ctx.tools(big, "gone", seen=NOW - timedelta(days=5))  # no longer offered
    await ctx.tools(small, "g1")
    await ctx.tools(off, "q1", "q2")
    for _ in range(3):
        await ctx.call(big.uid, "t3")
    await ctx.call(big.uid, "t2")
    body = (await ctx.client.get(f"/api/v1/resources/mcp_server/{big.uid}/tiering")).json()
    assert body["catalogue_size"] == 5  # 4 + 1; the disabled server is not listed to anyone
    assert body["listed_count"] == 3
    assert body["listed"] == ["t2", "t3"]
    assert body["behind_search"] == ["t1", "t4"]
    assert body["tool_count"] == 4
