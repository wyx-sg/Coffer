"""Integration tests for the chat HTTP surface — the channel conversations list.

Tests the routes through a real FastAPI app wired with:
- Real ChatService over in-memory fake repos.
- Real TurnOrchestrator with FakeAgentAdapter from the unit conftest.

Coverage:
- Conversation get / list / rename / delete round-trip.
- The list is channel conversations only, searched by title and directory,
  paged by cursor and narrowed by source and agent.
- ConversationNotFound on GET / PATCH / DELETE / interrupt → 404.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.domain.chat.agent_config import AgentConfig
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.dependencies import (
    get_agent_registry,
    get_chat_service,
    get_turn_orchestrator,
)
from coffer.surfaces.http.chat.turn_routes import router as turn_router
from coffer.surfaces.http.dependencies import get_resource_service

# Reuse the in-memory fakes + wiring helper from the unit conftest.
from tests.unit.chat.conftest import make_chat_services

_TOKEN = "test-token"


# ---------------------------------------------------------------------------
# Infrastructure helpers
# ---------------------------------------------------------------------------


class _NoChannels:
    """The resource service the conversation routes read channel names from.

    Overridden rather than inherited: the module-level resource service is only
    set when some earlier test in the same process happened to boot the full
    app, so relying on it made these tests pass serially and fail alone (or on
    an xdist worker that ran them first)."""

    async def list(self, **_: object) -> list[Any]:
        return []


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
    app.dependency_overrides[get_resource_service] = lambda: _NoChannels()
    return app


def _make_services() -> tuple[ChatService, TurnOrchestrator]:
    """Create fully-wired in-memory chat services (registry-backed)."""
    chat_svc, orchestrator, _registry = make_chat_services()
    return chat_svc, orchestrator


def _conversation(
    chat_svc: ChatService,
    *,
    title: str | None = None,
    channel_uid: str | None = "chan-1",
    cwd: str | None = None,
) -> str:
    """Create a conversation (a channel's, unless ``channel_uid`` is None)."""

    async def make() -> str:
        conv = await chat_svc.create_conversation(
            agent_key="builtin", channel_uid=channel_uid, peer_chat_id="peer"
        )
        if title is not None:
            await chat_svc.rename_conversation(conv.id, new_title=title)
        if cwd is not None:
            await chat_svc.set_agent_config(conv.id, AgentConfig(cwd=cwd, session_id="sess-1"))
        return conv.id

    return asyncio.run(make())


def _touch(chat_svc: ChatService, conv_id: str, at: datetime) -> None:
    asyncio.run(chat_svc._conversations.touch(conv_id, at))


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------


def test_conversation_get_list_rename_delete_roundtrip() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)
    conv_id = _conversation(chat_svc, cwd="/work/app")

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        # Get — the row carries its directory and native session id, no text.
        resp = client.get(f"/api/v1/chat/conversations/{conv_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == conv_id
        assert data["title"] == "New conversation"
        assert (data["cwd"], data["session_id"]) == ("/work/app", "sess-1")
        assert data["channel_binding"]["channel_uid"] == "chan-1"
        assert (data["running"], data["needs_you"]) == (False, False)
        assert "preview" not in data and "archived_at" not in data

        # List
        resp = client.get("/api/v1/chat/conversations")
        assert resp.status_code == 200
        assert len(resp.json()["conversations"]) == 1

        # Patch — rename
        resp = client.patch(f"/api/v1/chat/conversations/{conv_id}", json={"title": "Renamed"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Renamed"

        # Delete
        resp = client.delete(f"/api/v1/chat/conversations/{conv_id}")
        assert resp.status_code == 204

        # Get after delete → 404
        resp = client.get(f"/api/v1/chat/conversations/{conv_id}")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    set_active_token(None)


def test_the_web_has_no_route_to_create_archive_or_read_messages() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)
    conv_id = _conversation(chat_svc)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        base = "/api/v1/chat/conversations"
        assert client.post(base, json={"agent_key": "builtin"}).status_code == 405
        assert client.post(f"{base}/{conv_id}/archive").status_code == 404
        assert client.get(f"{base}/{conv_id}/messages").status_code == 404
        assert client.post(f"{base}/{conv_id}/messages", json={"text": "hi"}).status_code == 404

    set_active_token(None)


@pytest.mark.acceptance(spec="chat", scenario="the conversation list pages by cursor")
@pytest.mark.acceptance(
    spec="chat", scenario="the conversation list narrows by source and agent on the server"
)
def test_the_conversation_list_pages_by_cursor() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)
    made = [_conversation(chat_svc) for _ in range(3)]
    # Pin distinct activity times so "latest activity" is unambiguous.
    base = datetime(2026, 9, 1, tzinfo=UTC)
    for minutes, conv_id in enumerate(made):
        _touch(chat_svc, conv_id, base + timedelta(minutes=minutes))

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        first = client.get("/api/v1/chat/conversations", params={"limit": 2}).json()
        assert [c["id"] for c in first["conversations"]] == [made[2], made[1]]
        assert first["next_cursor"]
        rest = client.get(
            "/api/v1/chat/conversations", params={"limit": 2, "cursor": first["next_cursor"]}
        ).json()
        assert first["total"] == rest["total"] == 3
        assert [c["id"] for c in rest["conversations"]] == [made[0]]
        assert rest["next_cursor"] is None

    set_active_token(None)


@pytest.mark.acceptance(spec="chat", scenario="the conversation list pages by cursor")
def test_the_conversation_list_searches_titles_and_directories_and_pages_the_matches() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)
    titles = ["Deploy plan", "lunch", "deploy notes", "DEPLOY 100%", "other"]
    made = [_conversation(chat_svc, title=title) for title in titles]
    base = datetime(2026, 9, 1, tzinfo=UTC)
    for minutes, conv_id in enumerate(made):
        _touch(chat_svc, conv_id, base + timedelta(minutes=minutes))

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:

        def get(**params: object) -> dict:
            return client.get("/api/v1/chat/conversations", params=params).json()

        first = get(q="deploy", limit=2)
        assert [c["title"] for c in first["conversations"]] == ["DEPLOY 100%", "deploy notes"]
        assert first["next_cursor"]
        assert first["total"] == 3  # the matches, not the page
        assert get(q="lunch")["total"] == 1
        rest = get(q="deploy", limit=2, cursor=first["next_cursor"])
        assert [c["title"] for c in rest["conversations"]] == ["Deploy plan"]
        assert rest["next_cursor"] is None

        # A wildcard is text, not a pattern; blank q is no filter.
        assert [c["title"] for c in get(q="100%")["conversations"]] == ["DEPLOY 100%"]
        assert len(get(q="%")["conversations"]) == 1
        assert len(get(q="  ")["conversations"]) == 5

        # A directory is searched too, case-insensitively.
        by_dir = _conversation(chat_svc, title="untitled", cwd="/Work/Billing-Service")
        assert [c["id"] for c in get(q="billing-service")["conversations"]] == [by_dir]

        # Source (a channel uid) and agent filters: server-side, on page and total,
        # bound into the cursor.
        stranger = _conversation(chat_svc, channel_uid="chan-2")
        assert get()["total"] == 7
        assert [c["id"] for c in get(source="chan-2")["conversations"]] == [stranger]
        assert get(source="nope")["total"] == 0
        assert get(source=" , ")["total"] == 7
        assert get(agent="builtin")["total"] == 7
        assert get(agent="codex,claude_code")["total"] == 0
        by_agent = get(agent="builtin", limit=2)
        assert by_agent["next_cursor"] and by_agent["total"] == 7
        mismatched = client.get(
            "/api/v1/chat/conversations",
            params={"agent": "codex", "cursor": by_agent["next_cursor"]},
        )
        assert mismatched.status_code == 400
        assert mismatched.json()["error"]["code"] == "CURSOR_INVALID"
        assert (
            client.get(
                "/api/v1/chat/conversations",
                params={"source": "chan-1", "cursor": by_agent["next_cursor"]},
            ).status_code
            == 400
        )

        # A cursor issued for one q does not page another.
        refused = client.get(
            "/api/v1/chat/conversations", params={"q": "lunch", "cursor": first["next_cursor"]}
        )
        assert refused.status_code == 400
        assert refused.json()["error"]["code"] == "CURSOR_INVALID"

    set_active_token(None)


def test_a_conversation_no_channel_owns_is_not_listed() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)
    _conversation(chat_svc, channel_uid=None)
    owned = _conversation(chat_svc)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        listing = client.get("/api/v1/chat/conversations").json()

    assert [c["id"] for c in listing["conversations"]] == [owned]
    assert listing["total"] == 1
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
        resp = client.patch("/api/v1/chat/conversations/does-not-exist", json={"title": "x"})
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


def test_unauthenticated_request_returns_401() -> None:
    chat_svc, orchestrator = _make_services()
    app = _build_app(chat_svc, orchestrator)
    set_active_token(_TOKEN)

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/api/v1/chat/conversations")
        assert resp.status_code == 401

    set_active_token(None)


# ---------------------------------------------------------------------------
# Interrupt route guards
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
    conv_id = _conversation(chat_svc)

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        resp = client.post(f"/api/v1/chat/conversations/{conv_id}/interrupt")
        assert resp.status_code == 204

    set_active_token(None)
