"""An MCP server's hand-offs on the wire: the status read, a failed test, and
the attention items that carry the same prompt (spec mcp-gateway "Name a
missing stdio launcher", "Hand a failing MCP server's diagnosis to an agent").

The app is the capability-route test's app (real resource service, real health
repo, real probe); the attention source is composed over the same services the
way ``attention_wiring`` composes it.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from coffer.application.mcp import runner_detect
from coffer.application.mcp.attention import McpAttentionSource
from coffer.application.resource_service import ResourceService
from coffer.infrastructure.mcp.persistence import MCPServerHealthRepo
from coffer.surfaces.http.mcp.dependencies import get_health_repo
from coffer.surfaces.http.mcp.handoff_views import McpHandoffs
from tests.integration.surfaces.http.mcp.test_capability_routes import (
    _build_app,
    _with_in_memory,
)

TOKEN_VALUE = "tok_4f9a8b7c6d5e"
ENV_VALUE = "https://jira.internal.example"
BEARER = "Bearer abcdefghijklmnopqrstuvwxyz"


class _NoSecrets:
    def exists(self, ref: str) -> bool:
        return True


@pytest.fixture
async def ctx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[AsyncClient, ResourceService, MCPServerHealthRepo]]:
    _with_in_memory(monkeypatch)
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path / "logs"))
    app, engine, rsvc, _prefs, supervisor, _uid = await _build_app(tmp_path)
    health: MCPServerHealthRepo = app.dependency_overrides[get_health_repo]()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Coffer-Token": "test-token"},
    ) as client:
        yield client, rsvc, health
    await supervisor.dispose()
    with suppress(BaseException):
        await engine.dispose()


def _attention(rsvc: ResourceService, health: MCPServerHealthRepo, **kw: Any) -> McpAttentionSource:
    return McpAttentionSource(
        resources=rsvc, health=health, secrets=_NoSecrets(), handoffs=McpHandoffs(), **kw
    )


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="the launcher hand-off names the launcher, the server and its command",
)
async def test_the_launcher_hand_off_names_launcher_server_and_redacted_command(
    ctx: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, rsvc, _health = ctx
    monkeypatch.setattr(runner_detect.shutil, "which", lambda _c: None)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    server = await rsvc.register(
        kind="mcp_server",
        name="jira",
        config={
            "transport": {
                "type": "stdio",
                "command": "uvx",
                "args": ["mcp-atlassian", "--api-token", TOKEN_VALUE],
                "env": {"JIRA_URL": ENV_VALUE},
            }
        },
        actor="test",
    )
    r = await client.get(f"/api/v1/resources/mcp_server/{server.uid}/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["missing_runner"] == "uvx"
    prompt = body["handoff"]["prompt"]
    assert "`uvx`" in prompt and "MCP server jira" in prompt
    assert "`uvx mcp-atlassian --api-token '<secret>'`" in prompt
    assert "/usr/bin:/bin" in prompt
    assert "coffer mcp test jira" in prompt
    assert "brew" not in prompt
    assert TOKEN_VALUE not in prompt and ENV_VALUE not in prompt


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="the missing launcher attention item carries the same hand-off"
)
async def test_the_missing_launcher_item_carries_the_status_hand_off(
    ctx: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, rsvc, health = ctx
    server = await rsvc.register(
        kind="mcp_server",
        name="duck",
        config={"transport": {"type": "stdio", "command": "uvx", "args": ["mcp-server-duckdb"]}},
        actor="test",
    )
    monkeypatch.setattr(runner_detect.shutil, "which", lambda _c: None)
    status = (await client.get(f"/api/v1/resources/mcp_server/{server.uid}/status")).json()
    items = [i for i in await _attention(rsvc, health).items() if i.uid == server.uid]
    [item] = items
    assert item.reason_code == "mcp_missing_launcher"
    assert item.handoff == status["handoff"]["prompt"]
    assert "coffer" not in item.reason and "brew" not in item.reason


_NOISY = (
    "import sys\n"
    "for i in range(25):\n"
    "    print(f'stderr line {i}', file=sys.stderr)\n"
    f"print('Authorization: {BEARER}', file=sys.stderr)\n"
    "sys.exit(3)\n"
)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a failed test hands over its error and its stderr"
)
async def test_a_failed_test_hands_over_its_error_and_newest_stderr(ctx: Any) -> None:
    client, rsvc, _health = ctx
    server = await rsvc.register(
        kind="mcp_server",
        name="noisy",
        config={"transport": {"type": "stdio", "command": sys.executable, "args": ["-c", _NOISY]}},
        actor="test",
    )
    r = await client.post(f"/api/v1/resources/mcp_server/{server.uid}/test")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    prompt = body["handoff"]["prompt"]
    assert "MCP server noisy" in prompt
    assert "Transport: stdio" in prompt
    assert body["error_message"] and body["error_message"][:40] in prompt
    assert "stderr line 24" in prompt and "stderr line 5" not in prompt
    assert "abcdefghijklmnopqrstuvwxyz" not in prompt
    assert "coffer mcp test noisy" in prompt


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a failing server's status and attention item carry the diagnosis"
)
async def test_a_failing_server_status_and_item_carry_the_diagnosis(ctx: Any) -> None:
    client, rsvc, health = ctx
    server = await rsvc.register(
        kind="mcp_server",
        name="broken",
        config={
            "transport": {"type": "stdio", "command": sys.executable, "args": ["-c", "exit(1)"]}
        },
        actor="test",
    )
    await client.post(f"/api/v1/resources/mcp_server/{server.uid}/test")
    status = (await client.get(f"/api/v1/resources/mcp_server/{server.uid}/status")).json()
    assert status["status"] == "failing"
    prompt = status["handoff"]["prompt"]
    assert "find out why the MCP server broken" in prompt
    assert "Do not read or change the secrets Coffer stores" in prompt
    items = [i for i in await _attention(rsvc, health).items() if i.uid == server.uid]
    [item] = items
    assert item.reason_code == "mcp_failing"
    assert item.handoff == prompt
    assert "coffer" not in item.reason


async def test_a_healthy_server_has_no_hand_off(ctx: Any) -> None:
    client, rsvc, _health = ctx
    [server] = await rsvc.list(kind="mcp_server")
    r = await client.get(f"/api/v1/resources/mcp_server/{server.uid}/status")
    assert r.json()["handoff"] is None
