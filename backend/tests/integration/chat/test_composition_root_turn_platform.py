"""Integration tests verifying the turn platform is wired into the daemon.

Tests boot the **real** FastAPI app (``create_app()`` + Starlette lifespan) so
that ``wire_chat`` runs, the conversation tables exist, and the agent-provider
routes are mounted. Since the web chat page was removed, IM channels are the
platform's only client — so the seams asserted here are the ones a channel
reaches: the registry, the conversation store, and the agent-config validation
a channel binding depends on. Conversation writes go through the wired
``ChatService`` rather than an HTTP route, because there is no longer an HTTP
route that creates one.

There are no live LLM calls in this module.
"""

from __future__ import annotations

import sqlite3

import pytest
from starlette.testclient import TestClient

from coffer.domain.errors import AgentConfigRejected, UnknownAgent
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.turn_dependencies import get_chat_service

_TOKEN = "test-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}


@pytest.fixture()
def app(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Boot a real app instance with an isolated tmp-dir DB."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59300")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59309")
    return create_app()


# ---------------------------------------------------------------------------
# T-0072 verification: chat routers are mounted
# ---------------------------------------------------------------------------


def test_agent_provider_router_mounted(app) -> None:  # type: ignore[no-untyped-def]
    """GET /api/v1/agent-providers returns 200 (not 404), proving it is mounted."""
    with TestClient(app) as client:
        set_active_token(_TOKEN)
        resp = client.get("/api/v1/agent-providers", headers=_HEADERS)
        assert resp.status_code == 200, resp.text
        assert "agents" in resp.json()


def test_chat_db_tables_created_on_startup(app, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Alembic migration creates the chat tables on startup."""
    db_path = tmp_path / "c.db"

    with TestClient(app):
        set_active_token(_TOKEN)
        pass  # just boot the lifespan

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    table_names = {r[0] for r in rows}
    assert "conversations" in table_names, f"tables: {table_names}"
    assert "chat_messages" in table_names, f"tables: {table_names}"
    # The former chat_models registry table is retired (migration 0036): models
    # are now provider connections in the generic ``resources`` table.
    assert "chat_models" not in table_names, f"tables: {table_names}"


# ---------------------------------------------------------------------------
# Agent-provider registry — the platform seam, through real wiring
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="list available agents")
def test_list_agents_via_wired_daemon(app) -> None:  # type: ignore[no-untyped-def]
    """GET /api/v1/agent-providers lists only Coffer-managed agents
    (ADR builtin-agent-is-internal-capability)."""
    with TestClient(app) as client:
        set_active_token(_TOKEN)
        resp = client.get("/api/v1/agent-providers", headers=_HEADERS)
        assert resp.status_code == 200, resp.text
        agents = resp.json()["agents"]
        by_key = {a["agent_key"]: a for a in agents}
        # The built-in chat persona is retired
        # (ADR builtin-agent-is-internal-capability); the registry holds managed
        # agents only.
        assert "builtin" not in by_key
        # The CLI agents are registered; availability tracks whether their
        # binary is on PATH on this host (a bool either way, but present).
        assert {"claude_code", "codex"} <= set(by_key)
        assert by_key["claude_code"]["display_name"] == "Claude Code"
        assert isinstance(by_key["codex"]["available"], bool)


@pytest.mark.acceptance(spec="channels", scenario="choose an agent when starting a conversation")
@pytest.mark.asyncio
async def test_create_conversation_with_agent_via_wired_daemon(app, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Creating a conversation records the chosen managed agent and its config.

    This is what a channel binding does on the peer's first message.
    """
    with TestClient(app):
        set_active_token(_TOKEN)
        svc = get_chat_service()
        conv = await svc.create_conversation(
            agent_key="claude_code", agent_config={"cwd": str(tmp_path)}
        )
        assert conv.agent_key == "claude_code"


@pytest.mark.acceptance(
    spec="channels",
    scenario="reject an unknown agent or invalid agent configuration",
)
@pytest.mark.asyncio
async def test_create_conversation_rejects_unknown_agent_and_bad_config(app) -> None:  # type: ignore[no-untyped-def]
    """An unknown agent_key, or an agent_config the agent rejects, raises — and
    nothing is persisted. (An *absent* cwd is no longer invalid: it defaults to
    the Coffer-managed workspace. Only an explicitly-bad cwd is rejected.)

    A channel bound to an agent that was since removed hits the first path; a
    binding carrying a stale working directory hits the second.
    """
    with TestClient(app):
        set_active_token(_TOKEN)
        svc = get_chat_service()

        with pytest.raises(UnknownAgent):
            await svc.create_conversation(agent_key="no-such-agent")

        # An explicitly-supplied cwd that is not an existing directory is still
        # rejected (a defaulted/absent cwd would instead fall back silently).
        with pytest.raises(AgentConfigRejected):
            await svc.create_conversation(
                agent_key="claude_code", agent_config={"cwd": "/no/such/dir/xyz"}
            )

        assert await svc.list_conversations() == []


def test_builtin_agent_supervisor_stays_in_eviction_registry(app) -> None:  # type: ignore[no-untyped-def]
    """The built-in agent session's supervisor must stay in the session_supervisors
    registry: the mcp_server Kind's on_delete hook walks that registry to
    evict the deleted server's connection from every live session. Popping
    the built-in agent's entry at startup would leave its upstream
    subprocesses running (stale config/credentials) after a delete.
    Double-dispose is not a risk — the session's on_dispose callback removes
    the entry, and SubprocessSupervisor.dispose() is idempotent."""
    with TestClient(app):
        supervisors = app.state.mcp_session_supervisors
        assert "coffer-builtin-agent" in supervisors
