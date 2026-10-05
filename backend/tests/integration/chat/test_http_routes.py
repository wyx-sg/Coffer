"""Integration tests for the chat HTTP surface — the single-conversation routes.

Tests the routes through a real FastAPI app wired with:
- Real ChatService over in-memory fake repos.
- Real TurnOrchestrator with FakeAgentAdapter from the unit conftest.

Coverage:
- Conversation get / rename / delete round-trip; the list route is gone.
- The conversation index (what the cross-agent listing pages for a channel-only
  source) holds channel conversations only, searched by title and directory,
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

from coffer.application.chat.conversation_repo import Narrowing
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.pagination import CursorInvalid
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


def test_conversation_get_rename_delete_roundtrip() -> None:
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
        assert client.post(base, json={"agent_key": "builtin"}).status_code == 404
        # The list is the cross-agent one (GET /api/v1/agent-sessions).
        assert client.get(base).status_code == 404
        assert client.post(f"{base}/{conv_id}/archive").status_code == 404
        assert client.get(f"{base}/{conv_id}/messages").status_code == 404
        assert client.post(f"{base}/{conv_id}/messages", json={"text": "hi"}).status_code == 404

    set_active_token(None)


def _page(chat_svc: ChatService, **kw: Any) -> Any:
    return asyncio.run(chat_svc.page_conversations(**kw))


def test_the_conversation_index_pages_by_cursor() -> None:
    chat_svc, _ = _make_services()
    made = [_conversation(chat_svc) for _ in range(3)]
    base = datetime(2026, 9, 1, tzinfo=UTC)
    for minutes, conv_id in enumerate(made):
        _touch(chat_svc, conv_id, base + timedelta(minutes=minutes))

    first = _page(chat_svc, limit=2)
    assert [c.id for c in first.items] == [made[2], made[1]]
    assert first.next_cursor
    rest = _page(chat_svc, limit=2, cursor=first.next_cursor)
    assert [c.id for c in rest.items] == [made[0]]
    assert rest.next_cursor is None


def test_the_conversation_index_searches_narrows_and_binds_its_cursor() -> None:
    chat_svc, _ = _make_services()
    titles = ["Deploy plan", "lunch", "deploy notes", "DEPLOY 100%", "other"]
    made = [_conversation(chat_svc, title=title) for title in titles]
    base = datetime(2026, 9, 1, tzinfo=UTC)
    for minutes, conv_id in enumerate(made):
        _touch(chat_svc, conv_id, base + timedelta(minutes=minutes))

    first = _page(chat_svc, q="deploy", limit=2)
    assert [c.title for c in first.items] == ["DEPLOY 100%", "deploy notes"]
    rest = _page(chat_svc, q="deploy", limit=2, cursor=first.next_cursor)
    assert [c.title for c in rest.items] == ["Deploy plan"]
    assert rest.next_cursor is None
    # A wildcard is text, not a pattern; blank q is no filter.
    assert [c.title for c in _page(chat_svc, q="100%").items] == ["DEPLOY 100%"]
    assert len(_page(chat_svc, q="  ").items) == 5

    by_dir = _conversation(chat_svc, title="untitled", cwd="/Work/Billing-Service")
    assert [c.id for c in _page(chat_svc, q="billing-service").items] == [by_dir]

    stranger = _conversation(chat_svc, channel_uid="chan-2")
    assert [c.id for c in _page(chat_svc, narrow=Narrowing.of(sources=["chan-2"])).items] == [
        stranger
    ]
    assert _page(chat_svc, narrow=Narrowing.of(agents=["codex"])).items == []
    by_agent = _page(chat_svc, limit=2, narrow=Narrowing.of(agents=["builtin"]))
    assert by_agent.next_cursor
    with pytest.raises(CursorInvalid):
        _page(chat_svc, cursor=by_agent.next_cursor, narrow=Narrowing.of(agents=["codex"]))
    with pytest.raises(CursorInvalid):
        _page(chat_svc, cursor=first.next_cursor, q="lunch")


def test_a_conversation_no_channel_owns_is_not_indexed() -> None:
    chat_svc, _ = _make_services()
    _conversation(chat_svc, channel_uid=None)
    owned = _conversation(chat_svc)

    assert [c.id for c in _page(chat_svc).items] == [owned]


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
        resp = client.get("/api/v1/chat/conversations/some-id")
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
