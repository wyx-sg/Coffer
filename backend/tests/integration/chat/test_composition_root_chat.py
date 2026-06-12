"""Integration tests verifying the chat feature is wired into the daemon.

Tests boot the **real** FastAPI app (``create_app()`` + Starlette lifespan)
so that ``wire_chat`` runs and all three chat router groups are mounted.
LLM calls are deliberately avoided:
- Model CRUD routes are exercised without actually calling the LLM.
- The ``NoModelConfigured`` path is confirmed with a POST to the turn endpoint.
- Conversation CRUD confirms the DB tables and service were wired correctly.

There are no live LLM calls in this module — the FakeAgentAdapter / FakeChatModel
path lives in the existing ``tests/integration/chat/test_http_routes.py`` suite.
"""

from __future__ import annotations

import sqlite3

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

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


def test_chat_conversation_router_mounted(app) -> None:  # type: ignore[no-untyped-def]
    """GET /api/v1/chat/conversations returns 200 (not 404), proving the router is mounted."""
    with TestClient(app) as client:
        set_active_token(_TOKEN)
        resp = client.get("/api/v1/chat/conversations", headers=_HEADERS)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "conversations" in body
        assert body["conversations"] == []


def test_chat_model_router_mounted(app) -> None:  # type: ignore[no-untyped-def]
    """GET /api/v1/models returns 200, proving the model router is mounted."""
    with TestClient(app) as client:
        set_active_token(_TOKEN)
        resp = client.get("/api/v1/models", headers=_HEADERS)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "models" in body
        assert body["models"] == []


# ---------------------------------------------------------------------------
# Conversation + model CRUD end-to-end through the real wiring
# ---------------------------------------------------------------------------


def test_model_crud_via_wired_daemon(app) -> None:  # type: ignore[no-untyped-def]
    """Create, list, and delete a model through the fully-wired daemon."""
    with TestClient(app) as client:
        set_active_token(_TOKEN)

        resp = client.post(
            "/api/v1/models",
            headers=_HEADERS,
            json={
                "display_name": "Claude Test",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "credential_ref": "my-test-key",
            },
        )
        assert resp.status_code == 201, resp.text
        model_id = resp.json()["id"]
        assert resp.json()["is_default"] is True

        resp = client.get("/api/v1/models", headers=_HEADERS)
        assert resp.status_code == 200
        assert len(resp.json()["models"]) == 1

        resp = client.delete(f"/api/v1/models/{model_id}", headers=_HEADERS)
        assert resp.status_code == 204


def test_conversation_crud_via_wired_daemon(app) -> None:  # type: ignore[no-untyped-def]
    """Create, rename, and delete a conversation through the fully-wired daemon."""
    with TestClient(app) as client:
        set_active_token(_TOKEN)

        resp = client.post("/api/v1/chat/conversations", headers=_HEADERS)
        assert resp.status_code == 201, resp.text
        conv_id = resp.json()["id"]
        assert resp.json()["title"] == "New conversation"

        resp = client.patch(
            f"/api/v1/chat/conversations/{conv_id}",
            headers=_HEADERS,
            json={"title": "Renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Renamed"

        resp = client.delete(f"/api/v1/chat/conversations/{conv_id}", headers=_HEADERS)
        assert resp.status_code == 204

        resp = client.get(f"/api/v1/chat/conversations/{conv_id}", headers=_HEADERS)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# NoModelConfigured path: POST to turn endpoint with no model registered
# ---------------------------------------------------------------------------


def test_no_model_configured_path_via_wired_daemon(app) -> None:  # type: ignore[no-untyped-def]
    """With no model registered, POST to the turn endpoint returns 409 JSON.

    This confirms the TurnOrchestrator + ModelService are wired and the turn
    endpoint is reachable — without needing any LLM call.
    """
    with TestClient(app) as client:
        set_active_token(_TOKEN)

        resp = client.post("/api/v1/chat/conversations", headers=_HEADERS)
        assert resp.status_code == 201
        conv_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            headers=_HEADERS,
            json={"text": "Hello"},
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error"]["code"] == "NO_MODEL_CONFIGURED"
        assert "text/event-stream" not in resp.headers.get("content-type", "")


def test_missing_credential_returns_400_not_500(app) -> None:  # type: ignore[no-untyped-def]
    """A model whose credential is absent from the keychain must fail the turn
    with a mapped 400 (CREDENTIAL_MISSING), keeping the conversation usable —
    not a generic 500 (HOME is a tmp dir, so the keychain has no such entry)."""
    with TestClient(app) as client:
        set_active_token(_TOKEN)

        resp = client.post(
            "/api/v1/models",
            headers=_HEADERS,
            json={
                "display_name": "Claude",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "credential_ref": "no-such-keychain-entry",
            },
        )
        assert resp.status_code == 201, resp.text

        resp = client.post("/api/v1/chat/conversations", headers=_HEADERS)
        assert resp.status_code == 201
        conv_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            headers=_HEADERS,
            json={"text": "Hello"},
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"]["code"] == "CREDENTIAL_MISSING"
        assert "text/event-stream" not in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# DB table creation: chat tables exist after startup
# ---------------------------------------------------------------------------


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
    assert "chat_models" in table_names, f"tables: {table_names}"


# ---------------------------------------------------------------------------
# Agent-provider registry — the platform seam, through real wiring
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="008-agent-chat", scenario="list available agents")
def test_list_agents_via_wired_daemon(app) -> None:  # type: ignore[no-untyped-def]
    """GET /api/v1/chat/agents lists the built-in + CLI agents with availability."""
    with TestClient(app) as client:
        set_active_token(_TOKEN)
        resp = client.get("/api/v1/chat/agents", headers=_HEADERS)
        assert resp.status_code == 200, resp.text
        agents = resp.json()["agents"]
        by_key = {a["agent_key"]: a for a in agents}
        # The built-in agent is always present and available.
        assert by_key["builtin"]["display_name"] == "Coffer Assistant"
        assert by_key["builtin"]["available"] is True
        # The CLI agents are registered; availability tracks whether their
        # binary is on PATH on this host (a bool either way, but present).
        assert {"claude_code", "codex"} <= set(by_key)
        assert by_key["claude_code"]["display_name"] == "Claude Code"
        assert isinstance(by_key["codex"]["available"], bool)


@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="choose an agent when starting a conversation"
)
def test_create_conversation_with_agent_via_wired_daemon(app) -> None:  # type: ignore[no-untyped-def]
    """Creating a conversation records the chosen agent and validates its config."""
    with TestClient(app) as client:
        set_active_token(_TOKEN)
        resp = client.post(
            "/api/v1/chat/conversations",
            headers=_HEADERS,
            json={"agent_key": "builtin", "agent_config": {}},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["agent_key"] == "builtin"


@pytest.mark.acceptance(
    spec="008-agent-chat",
    scenario="reject an unknown agent or invalid agent configuration",
)
def test_create_conversation_rejects_unknown_agent_and_bad_config(app) -> None:  # type: ignore[no-untyped-def]
    """An unknown agent_key, or an agent_config the agent rejects, is a 400 — and
    nothing is persisted."""
    with TestClient(app) as client:
        set_active_token(_TOKEN)

        resp = client.post(
            "/api/v1/chat/conversations",
            headers=_HEADERS,
            json={"agent_key": "no-such-agent"},
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"]["code"] == "UNKNOWN_AGENT"

        resp = client.post(
            "/api/v1/chat/conversations",
            headers=_HEADERS,
            json={"agent_key": "builtin", "agent_config": {"model_id": "ghost"}},
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"]["code"] == "AGENT_CONFIG_REJECTED"

        resp = client.get("/api/v1/chat/conversations", headers=_HEADERS)
        assert resp.json()["conversations"] == []


def test_builtin_agent_supervisor_stays_in_eviction_registry(app) -> None:  # type: ignore[no-untyped-def]
    """The chat session's supervisor must stay in the session_supervisors
    registry: the mcp_server Kind's on_delete hook walks that registry to
    evict the deleted server's connection from every live session. Popping
    the built-in agent's entry at startup would leave its upstream
    subprocesses running (stale config/credentials) after a delete.
    Double-dispose is not a risk — the session's on_dispose callback removes
    the entry, and SubprocessSupervisor.dispose() is idempotent."""
    with TestClient(app):
        supervisors = app.state.mcp_session_supervisors
        assert "coffer-builtin-agent" in supervisors
