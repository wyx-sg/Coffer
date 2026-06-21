"""Integration tests for the chat HTTP surface — conversations, messages, SSE turn.

Tests the routes through a real FastAPI app wired with:
- Real ChatService over in-memory SQLite repos.
- Real TurnOrchestrator with FakeAgentAdapter + FakeToolGateway from the unit conftest.

Coverage:
- Conversation CRUD round-trip (create, get, list, rename/model, delete).
- SSE turn endpoint streaming turn_start … turn_done events.
- TurnInProgress → 409 JSON (not SSE).
- A build-adapter domain error → mapped JSON status (not SSE).
- ConversationNotFound on send_message → 404 JSON.
- ConversationNotFound on GET / PATCH / DELETE → 404.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator, clear_active_turns
from coffer.domain.errors import AgentConfigRejected
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.turn_routes import router as turn_router
from coffer.surfaces.http.dependencies import (
    get_agent_registry,
    get_chat_service,
    get_turn_orchestrator,
)

# Reuse the in-memory fakes + wiring helper from the unit conftest.
from tests.unit.chat.conftest import FakeAgentProvider, make_chat_services

_TOKEN = "test-token"


# ---------------------------------------------------------------------------
# Infrastructure helpers
# ---------------------------------------------------------------------------


def _build_app(
    chat_svc: ChatService,
    orchestrator: TurnOrchestrator,
) -> FastAPI:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(conversation_router)
    app.include_router(turn_router)
    app.dependency_overrides[get_chat_service] = lambda: chat_svc
    app.dependency_overrides[get_turn_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_agent_registry] = lambda: orchestrator._registry
    return app


def _make_services(
    events: list | None = None,
    *,
    provider: object = None,
) -> tuple[ChatService, TurnOrchestrator]:
    """Create fully-wired in-memory chat services (registry-backed)."""
    chat_svc, orchestrator, _registry = make_chat_services(events, provider=provider)
    return chat_svc, orchestrator


@pytest.fixture(autouse=True)
def _reset_turns() -> Generator[None, None, None]:
    """Clear any lingering active turns between tests."""
    clear_active_turns()
    yield
    clear_active_turns()


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="008-agent-chat", scenario="manage conversations")
def test_conversation_crud_roundtrip() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        # Create
        resp = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"})
        assert resp.status_code == 201, resp.text
        data = resp.json()
        conv_id = data["id"]
        assert data["agent_key"] == "builtin"
        assert data["title"] == "New conversation"
        assert data["model_id"] is None

        # Get
        resp = client.get(f"/api/v1/chat/conversations/{conv_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == conv_id

        # List
        resp = client.get("/api/v1/chat/conversations")
        assert resp.status_code == 200
        assert len(resp.json()["conversations"]) == 1

        # Patch — rename
        resp = client.patch(
            f"/api/v1/chat/conversations/{conv_id}",
            json={"title": "Renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Renamed"

        # Delete
        resp = client.delete(f"/api/v1/chat/conversations/{conv_id}")
        assert resp.status_code == 204

        # Get after delete → 404
        resp = client.get(f"/api/v1/chat/conversations/{conv_id}")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "CONVERSATION_NOT_FOUND"

    set_active_token(None)


@pytest.mark.acceptance(spec="008-agent-chat", scenario="archive and restore a conversation")
def test_archive_and_unarchive_filter_the_list() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        conv_id = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"}).json()[
            "id"
        ]

        # Active by default; archived list empty.
        assert len(client.get("/api/v1/chat/conversations").json()["conversations"]) == 1
        assert client.get("/api/v1/chat/conversations?archived=true").json()["conversations"] == []

        # Archive → leaves the active list, appears in the archived list.
        resp = client.post(f"/api/v1/chat/conversations/{conv_id}/archive")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None
        assert client.get("/api/v1/chat/conversations").json()["conversations"] == []
        archived = client.get("/api/v1/chat/conversations?archived=true").json()["conversations"]
        assert [c["id"] for c in archived] == [conv_id]

        # Unarchive → back to active.
        resp = client.post(f"/api/v1/chat/conversations/{conv_id}/unarchive")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is None
        active = client.get("/api/v1/chat/conversations").json()["conversations"]
        assert [c["id"] for c in active] == [conv_id]

        # Archiving a missing conversation → 404.
        resp = client.post("/api/v1/chat/conversations/nope/archive")
        assert resp.status_code == 404

    set_active_token(None)


def test_get_conversation_not_found_returns_404() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.get("/api/v1/chat/conversations/does-not-exist")
        assert resp.status_code == 404

    set_active_token(None)


def test_patch_conversation_not_found_returns_404() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.patch(
            "/api/v1/chat/conversations/does-not-exist",
            json={"title": "x"},
        )
        assert resp.status_code == 404

    set_active_token(None)


def test_delete_conversation_not_found_returns_404() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.delete("/api/v1/chat/conversations/does-not-exist")
        assert resp.status_code == 404

    set_active_token(None)


def test_list_messages_not_found_returns_404() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.get("/api/v1/chat/conversations/does-not-exist/messages")
        assert resp.status_code == 404

    set_active_token(None)


def test_create_conversation_with_body() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post(
            "/api/v1/chat/conversations",
            json={"agent_key": "builtin", "agent_config": {}},
        )
        assert resp.status_code == 201
        assert resp.json()["id"]
        assert resp.json()["agent_key"] == "builtin"

    set_active_token(None)


def test_unauthenticated_request_returns_401() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/v1/chat/conversations")
        assert resp.status_code == 401

    set_active_token(None)


# ---------------------------------------------------------------------------
# Agent-config (per-conversation managed-agent model, ADR-024 -> ADR-032)
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="set a managed agent's model per conversation"
)
def test_agent_config_set_and_get_model_roundtrip() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        conv_id = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"}).json()[
            "id"
        ]

        # Empty by default — inherits the global default.
        before = client.get(f"/api/v1/chat/conversations/{conv_id}/agent-config")
        assert before.status_code == 200, before.text
        assert before.json() == {"cwd": None, "model": None}

        # Set the agent's own model (free-text passthrough).
        resp = client.patch(
            f"/api/v1/chat/conversations/{conv_id}/agent-config",
            json={"model": "claude-opus-4-8"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"cwd": None, "model": "claude-opus-4-8"}

        # Reads back.
        after = client.get(f"/api/v1/chat/conversations/{conv_id}/agent-config").json()
        assert after["model"] == "claude-opus-4-8"

    set_active_token(None)


def test_agent_config_clear_model_with_empty_string() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        conv_id = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"}).json()[
            "id"
        ]
        client.patch(
            f"/api/v1/chat/conversations/{conv_id}/agent-config",
            json={"model": "gpt-5-codex"},
        )
        # An empty/whitespace model clears the override back to the default.
        resp = client.patch(
            f"/api/v1/chat/conversations/{conv_id}/agent-config",
            json={"model": "  "},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["model"] is None

    set_active_token(None)


def test_agent_config_get_not_found_returns_404() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        assert client.get("/api/v1/chat/conversations/nope/agent-config").status_code == 404
        resp = client.patch(
            "/api/v1/chat/conversations/nope/agent-config",
            json={"model": "x"},
        )
        assert resp.status_code == 404

    set_active_token(None)


async def test_agent_config_set_model_preserves_cwd_and_session() -> None:
    """Setting (and clearing) the model must never clobber cwd/session_id —
    otherwise an existing CLI session would be lost on the next turn."""
    from coffer.domain.chat.agent_config import AgentConfig
    from coffer.surfaces.http.chat.conversation_routes import (
        get_agent_config as get_agent_config_route,
    )
    from coffer.surfaces.http.chat.conversation_routes import (
        set_agent_config as set_agent_config_route,
    )
    from coffer.surfaces.http.chat.schemas import AgentConfigPatch

    chat_svc, _orchestrator = _make_services()
    conv = await chat_svc.create_conversation(agent_key="builtin", agent_config={})
    await chat_svc.set_agent_config(conv.id, AgentConfig(cwd="/work", session_id="sess-1"))

    out = await set_agent_config_route(
        conv.id, AgentConfigPatch(model="claude-opus-4-8"), svc=chat_svc
    )
    assert out.model == "claude-opus-4-8"
    assert out.cwd == "/work"
    stored = await chat_svc.get_agent_config(conv.id)
    assert stored.session_id == "sess-1"  # preserved

    cleared = await set_agent_config_route(conv.id, AgentConfigPatch(model=""), svc=chat_svc)
    assert cleared.model is None
    again = await get_agent_config_route(conv.id, svc=chat_svc)
    assert again.cwd == "/work"
    assert (await chat_svc.get_agent_config(conv.id)).session_id == "sess-1"


# ---------------------------------------------------------------------------
# SSE turn endpoint
# ---------------------------------------------------------------------------


def test_send_message_returns_202_fire_and_return() -> None:
    """POST /conversations/{id}/messages is fire-and-return (ADR-031): 202 with
    queued=false when the turn starts immediately. Turn events stream via the
    GET .../events subscription (covered in test_live_mirror.py)."""
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        # A default model so the (builtin-mimicking) fake provider builds.
        client.post(
            "/api/v1/models",
            json={
                "display_name": "Test Model",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "credential_ref": "ref",
            },
        )
        resp = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"})
        conv_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"text": "Hi"},
        )
        assert resp.status_code == 202
        assert resp.json() == {"queued": False}

    set_active_token(None)


def test_set_pending_replaces_queue() -> None:
    """PUT /conversations/{id}/pending replaces the pending queue and echoes it
    back (ADR-031). When the head's turn cannot start, the whole queue is kept."""
    # A provider whose build_adapter fails → the head's turn cannot start. The
    # orchestrator re-inserts the head and pauses rather than dropping it, so the
    # WHOLE queue is preserved (regression test for the lost-head bug).
    provider = FakeAgentProvider(
        adapter=None, build_error=AgentConfigRejected("missing_credential", "no credential")
    )
    chat_svc, orchestrator = _make_services(provider=provider)
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"})
        conv_id = resp.json()["id"]

        resp = client.put(
            f"/api/v1/chat/conversations/{conv_id}/pending",
            json={"pending": ["a", "b", "c"]},
        )
        assert resp.status_code == 200
        assert resp.json()["pending"] == ["a", "b", "c"]

    set_active_token(None)


def test_send_message_unknown_conversation_returns_404() -> None:
    """POST .../messages for a missing conversation propagates 404 JSON."""
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post(
            "/api/v1/chat/conversations/does-not-exist/messages",
            json={"text": "hello"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    set_active_token(None)


def test_send_message_conversation_not_found_returns_404_json(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """ConversationNotFound on send_message must return 404 JSON — not SSE."""
    events: list = []
    chat_svc, orchestrator = _make_services(events=events)
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    from coffer.domain.errors import ConversationNotFound

    async def _raise_not_found(*args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise ConversationNotFound("no-such-conv")

    monkeypatch.setattr(orchestrator, "start_turn", _raise_not_found)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post(
            "/api/v1/chat/conversations/no-such-conv/messages",
            json={"text": "hello"},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "CONVERSATION_NOT_FOUND"
        assert "text/event-stream" not in resp.headers.get("content-type", "")

    set_active_token(None)


# ---------------------------------------------------------------------------
# SSE turn: build-adapter error via real orchestrator (end-to-end)
# ---------------------------------------------------------------------------


def test_send_message_build_adapter_error_real_orchestrator() -> None:
    """When the agent provider's build_adapter raises a domain error, the turn
    endpoint returns the mapped status as JSON — the orchestrator propagates it
    before streaming, so the client never gets a half-open SSE stream."""
    provider = FakeAgentProvider(
        adapter=None, build_error=AgentConfigRejected("missing_credential", "no credential")
    )
    chat_svc, orchestrator = _make_services(provider=provider)
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"})
        conv_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"text": "hello"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "AGENT_CONFIG_REJECTED"
        assert "text/event-stream" not in resp.headers.get("content-type", "")

    set_active_token(None)


# ---------------------------------------------------------------------------
# Interrupt route guards (non-streaming error / no-op paths)
# ---------------------------------------------------------------------------


def test_interrupt_unknown_conversation_returns_404() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post("/api/v1/chat/conversations/no-such-conv/interrupt")
        assert resp.status_code == 404

    set_active_token(None)


def test_interrupt_no_active_turn_is_a_noop_204() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        conv_id = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"}).json()[
            "id"
        ]
        resp = client.post(f"/api/v1/chat/conversations/{conv_id}/interrupt")
        assert resp.status_code == 204

    set_active_token(None)


# ---------------------------------------------------------------------------
# m3: SSE turn_error event reaches the client when agent yields TurnError
# ---------------------------------------------------------------------------


# The deep streaming, queueing, interrupt-pauses-queue, and cross-surface
# observation behaviours are covered by the async orchestrator tests in
# test_live_mirror.py (sync TestClient cannot observe a detached turn task nor
# hold the long-lived GET .../events stream).
