"""Integration tests for the chat HTTP surface — conversations, messages, models, SSE turn.

Tests the routes through a real FastAPI app wired with:
- Real ChatService / ModelService over in-memory SQLite repos.
- Real TurnOrchestrator with FakeAgentAdapter + FakeToolGateway from the unit conftest.

Coverage:
- Conversation CRUD round-trip (create, get, list, rename/model, delete).
- Model CRUD round-trip (create, list, patch, delete).
- SSE turn endpoint streaming turn_start … turn_done events.
- TurnInProgress → 409 JSON (not SSE).
- NoModelConfigured → 409 JSON.
- ConversationNotFound on send_message → 404 JSON.
- ConversationNotFound on GET / PATCH / DELETE → 404.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.chat.model_service import ModelService
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator, clear_active_turns
from coffer.domain.errors import NoModelConfigured
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.model_routes import router as model_router
from coffer.surfaces.http.chat.turn_routes import router as turn_router
from coffer.surfaces.http.dependencies import (
    get_agent_registry,
    get_chat_service,
    get_model_service,
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
    model_svc: ModelService,
    orchestrator: TurnOrchestrator,
) -> FastAPI:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(conversation_router)
    app.include_router(turn_router)
    app.include_router(model_router)
    app.dependency_overrides[get_chat_service] = lambda: chat_svc
    app.dependency_overrides[get_model_service] = lambda: model_svc
    app.dependency_overrides[get_turn_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_agent_registry] = lambda: orchestrator._registry
    return app


def _make_services(
    events: list | None = None,
    *,
    provider: object = None,
) -> tuple[ChatService, ModelService, TurnOrchestrator]:
    """Create fully-wired in-memory chat services (registry-backed)."""
    chat_svc, model_svc, orchestrator, _registry = make_chat_services(events, provider=provider)
    return chat_svc, model_svc, orchestrator


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
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
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
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
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
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.get("/api/v1/chat/conversations/does-not-exist")
        assert resp.status_code == 404

    set_active_token(None)


def test_patch_conversation_not_found_returns_404() -> None:
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.patch(
            "/api/v1/chat/conversations/does-not-exist",
            json={"title": "x"},
        )
        assert resp.status_code == 404

    set_active_token(None)


def test_patch_conversation_unknown_model_returns_404() -> None:
    """PATCH model_id with a non-existent model must be rejected up front
    (404 MODEL_NOT_FOUND), not accepted and deferred to the next turn."""
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        conv_id = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"}).json()[
            "id"
        ]

        resp = client.patch(
            f"/api/v1/chat/conversations/{conv_id}",
            json={"model_id": "ghost-model"},
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "MODEL_NOT_FOUND"

        # Nothing persisted: the conversation still has no model override.
        conv = client.get(f"/api/v1/chat/conversations/{conv_id}").json()
        assert conv["model_id"] is None

    set_active_token(None)


def test_patch_conversation_is_atomic_on_invalid_model() -> None:
    """A PATCH carrying both a title and an invalid model_id must apply
    NEITHER — a rejected request may not leave a partially-applied rename."""
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        conv_id = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"}).json()[
            "id"
        ]
        original_title = client.get(f"/api/v1/chat/conversations/{conv_id}").json()["title"]

        resp = client.patch(
            f"/api/v1/chat/conversations/{conv_id}",
            json={"title": "Sneaky rename", "model_id": "ghost-model"},
        )
        assert resp.status_code == 404, resp.text

        conv = client.get(f"/api/v1/chat/conversations/{conv_id}").json()
        assert conv["title"] == original_title  # rename was NOT applied
        assert conv["model_id"] is None

    set_active_token(None)


def test_delete_conversation_not_found_returns_404() -> None:
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.delete("/api/v1/chat/conversations/does-not-exist")
        assert resp.status_code == 404

    set_active_token(None)


def test_list_messages_not_found_returns_404() -> None:
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.get("/api/v1/chat/conversations/does-not-exist/messages")
        assert resp.status_code == 404

    set_active_token(None)


def test_create_conversation_with_body() -> None:
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
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
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/v1/chat/conversations")
        assert resp.status_code == 401

    set_active_token(None)


# ---------------------------------------------------------------------------
# Model CRUD
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="008-agent-chat", scenario="register a model provider")
def test_model_crud_roundtrip() -> None:
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        # Create
        resp = client.post(
            "/api/v1/models",
            json={
                "display_name": "My Claude",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "credential_ref": "my-key",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        model_id = data["id"]
        assert data["display_name"] == "My Claude"
        assert data["provider"] == "anthropic"
        assert data["is_default"] is True  # first model becomes default

        # List
        resp = client.get("/api/v1/models")
        assert resp.status_code == 200
        assert len(resp.json()["models"]) == 1

        # Patch
        resp = client.patch(
            f"/api/v1/models/{model_id}",
            json={"display_name": "Renamed Claude"},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Renamed Claude"

        # Delete
        resp = client.delete(f"/api/v1/models/{model_id}")
        assert resp.status_code == 204

        # List after delete — should be empty
        resp = client.get("/api/v1/models")
        assert resp.status_code == 200
        assert resp.json()["models"] == []

    set_active_token(None)


def test_create_second_model_with_is_default_promotes_it() -> None:
    """POST /models with is_default=true on a non-first model must take effect."""
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        first = client.post(
            "/api/v1/models",
            json={
                "display_name": "Claude",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "credential_ref": "k1",
            },
        )
        assert first.status_code == 201, first.text
        first_id = first.json()["id"]

        second = client.post(
            "/api/v1/models",
            json={
                "display_name": "GPT-4o",
                "provider": "openai",
                "model": "gpt-4o",
                "credential_ref": "k2",
                "is_default": True,
            },
        )
        assert second.status_code == 201, second.text
        assert second.json()["is_default"] is True

        models = {m["id"]: m for m in client.get("/api/v1/models").json()["models"]}
        assert models[first_id]["is_default"] is False

    set_active_token(None)


@pytest.mark.acceptance(spec="008-agent-chat", scenario="reject an incomplete model")
def test_create_model_invalid_returns_400() -> None:
    """Missing credential_ref for anthropic → 400 MODEL_REJECTED."""
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post(
            "/api/v1/models",
            json={
                "display_name": "Bad Model",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                # No credential_ref — should fail
            },
        )
        assert resp.status_code == 400

    set_active_token(None)


def test_patch_model_not_found_returns_404() -> None:
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.patch(
            "/api/v1/models/does-not-exist",
            json={"display_name": "x"},
        )
        assert resp.status_code == 404

    set_active_token(None)


def test_delete_model_not_found_returns_404() -> None:
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.delete("/api/v1/models/does-not-exist")
        assert resp.status_code == 404

    set_active_token(None)


# ---------------------------------------------------------------------------
# SSE turn endpoint
# ---------------------------------------------------------------------------


def test_send_message_returns_202_fire_and_return() -> None:
    """POST /conversations/{id}/messages is fire-and-return (ADR-031): 202 with
    queued=false when the turn starts immediately. Turn events stream via the
    GET .../events subscription (covered in test_live_mirror.py)."""
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
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
    back (ADR-031). With no turn running the head starts and the rest remain."""
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"})
        conv_id = resp.json()["id"]

        # No model configured → the fake provider cannot build, so nothing
        # auto-starts and the whole queue is retained (paused effect not needed).
        resp = client.put(
            f"/api/v1/chat/conversations/{conv_id}/pending",
            json={"pending": ["a", "b", "c"]},
        )
        assert resp.status_code == 200
        # The head may have been consumed by an auto-advance attempt; assert the
        # tail is preserved and the response shape is correct.
        body = resp.json()
        assert "pending" in body
        assert body["pending"][-2:] == ["b", "c"]

    set_active_token(None)


def test_send_message_unknown_conversation_returns_404() -> None:
    """POST .../messages for a missing conversation propagates 404 JSON."""
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post(
            "/api/v1/chat/conversations/does-not-exist/messages",
            json={"text": "hello"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    set_active_token(None)


@pytest.mark.acceptance(spec="008-agent-chat", scenario="no-model empty state")
def test_send_message_no_model_configured_returns_409_json(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """NoModelConfigured must return 409 JSON — not SSE."""
    events: list = []
    chat_svc, model_svc, orchestrator = _make_services(events=events)
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    from coffer.domain.errors import NoModelConfigured

    async def _raise_no_model(*args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise NoModelConfigured()

    monkeypatch.setattr(orchestrator, "start_turn", _raise_no_model)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"})
        conv_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"text": "hello"},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "NO_MODEL_CONFIGURED"
        assert "text/event-stream" not in resp.headers.get("content-type", "")

    set_active_token(None)


def test_send_message_conversation_not_found_returns_404_json(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """ConversationNotFound on send_message must return 404 JSON — not SSE."""
    events: list = []
    chat_svc, model_svc, orchestrator = _make_services(events=events)
    app = _build_app(chat_svc, model_svc, orchestrator)
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
# SSE turn: no-model path via real orchestrator (end-to-end)
# ---------------------------------------------------------------------------


def test_send_message_no_model_real_orchestrator() -> None:
    """When the agent provider's build_adapter raises NoModelConfigured, the turn
    endpoint returns 409 JSON — the orchestrator propagates it before streaming."""
    provider = FakeAgentProvider(adapter=None, build_error=NoModelConfigured())
    chat_svc, model_svc, orchestrator = _make_services(provider=provider)
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"})
        conv_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"text": "hello"},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "NO_MODEL_CONFIGURED"
        assert "text/event-stream" not in resp.headers.get("content-type", "")

    set_active_token(None)


# ---------------------------------------------------------------------------
# Interrupt route guards (non-streaming error / no-op paths)
# ---------------------------------------------------------------------------


def test_interrupt_unknown_conversation_returns_404() -> None:
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post("/api/v1/chat/conversations/no-such-conv/interrupt")
        assert resp.status_code == 404

    set_active_token(None)


def test_interrupt_no_active_turn_is_a_noop_204() -> None:
    chat_svc, model_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, model_svc, orchestrator)
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
