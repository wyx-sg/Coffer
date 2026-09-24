"""Attachments from the web Chat page, end to end over HTTP (spec chat "Upload a
file for a web message", "Send uploaded files with a web message", "Prune
uploaded chat media on the retention cadence").

A real FastAPI app with the upload, conversation and turn routes, the real
file-backed store under ``tmp_path``, and the in-memory chat services with a
scripted agent adapter — so an upload lands on disk, a send persists the
reference, and the adapter is handed exactly what a channel's media hands it.
"""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.audit_service import AuditService
from coffer.application.chat.attachments import ChatAttachmentService
from coffer.application.chat.turn_orchestrator import clear_active_turns
from coffer.domain.chat.attachment import MAX_ATTACHMENT_BYTES, Attachment
from coffer.infrastructure.chat import persistence_models as _chat_models  # noqa: F401
from coffer.infrastructure.chat.media_store import FileChatMediaStore
from coffer.infrastructure.persistence import models as _models  # noqa: F401  (registers tables)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.app_mcp_composition import build_retention_service
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.attachment_routes import MULTIPART_OVERHEAD_BYTES
from coffer.surfaces.http.chat.attachment_routes import router as attachment_router
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.dependencies import (
    get_agent_registry,
    get_attachment_service,
    get_chat_service,
    get_turn_orchestrator,
)
from coffer.surfaces.http.chat.turn_routes import router as turn_router
from coffer.surfaces.http.dependencies import get_resource_service
from tests.unit.chat.conftest import FakeAgentAdapter, FakeAgentProvider, make_chat_services

_TOKEN = "test-token"
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture(autouse=True)
def _reset_turns() -> Generator[None, None, None]:
    clear_active_turns()
    set_active_token(_TOKEN)
    yield
    set_active_token(None)
    clear_active_turns()


class _NoChannels:
    """The resource service the conversation routes read channel names from."""

    async def list(self, **_: object) -> list[Any]:
        return []


class _Env:
    def __init__(self, tmp_path: Path) -> None:
        from coffer.domain.chat.events import TextDelta, TurnDone, TurnStarted

        self.adapter = FakeAgentAdapter(
            [
                TurnStarted(),
                TextDelta(text="ok"),
                TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn"),
            ]
        )
        chat_svc, orchestrator, registry = make_chat_services(
            provider=FakeAgentProvider(self.adapter, agent_key="builtin")
        )
        self.orchestrator = orchestrator
        self.media = tmp_path / "chat-media"
        attachments = ChatAttachmentService(FileChatMediaStore(self.media))
        app = FastAPI()
        err_handlers.register(app)
        app.include_router(attachment_router)
        app.include_router(conversation_router)
        app.include_router(turn_router)
        app.dependency_overrides[get_chat_service] = lambda: chat_svc
        app.dependency_overrides[get_turn_orchestrator] = lambda: orchestrator
        app.dependency_overrides[get_agent_registry] = lambda: registry
        app.dependency_overrides[get_attachment_service] = lambda: attachments
        app.dependency_overrides[get_resource_service] = lambda: _NoChannels()
        self.app = app


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    return _Env(tmp_path)


def _client(env: _Env) -> TestClient:
    return TestClient(env.app, headers={"X-Coffer-Token": _TOKEN})


def _upload(client: TestClient, name: str, data: bytes, mime: str) -> Any:
    return client.post("/api/v1/chat/attachments", files={"file": (name, data, mime)})


def _conversation(client: TestClient) -> str:
    resp = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"})
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


def _messages_when_settled(client: TestClient, conv_id: str) -> list[dict[str, Any]]:
    """Poll until the turn's assistant reply is committed, then return every row."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        rows = client.get(f"/api/v1/chat/conversations/{conv_id}/messages").json()["messages"]
        if any(r["role"] == "assistant" and r["status"] == "complete" for r in rows):
            return list(rows)
        time.sleep(0.02)
    raise AssertionError("the turn never settled")


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="chat", scenario="an uploaded file is stored and named by an opaque id"
)
def test_upload_stores_the_bytes_and_returns_an_opaque_id(env: _Env) -> None:
    with _client(env) as client:
        resp = _upload(client, "screen shot.png", _PNG, "image/png")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == {"id", "filename", "mime", "size"}
    assert len(body["id"]) == 32 and all(c in "0123456789abcdef" for c in body["id"])
    assert (body["filename"], body["mime"], body["size"]) == ("screen shot.png", "image/png", 40)
    # The bytes are on disk under chat-media, keeping the extension …
    stored = env.media / f"{body['id']}.png"
    assert stored.read_bytes() == _PNG
    # … and the local path never reaches the wire.
    assert str(env.media) not in resp.text


@pytest.mark.acceptance(spec="chat", scenario="an oversized upload is refused naming the limit")
def test_oversized_upload_is_413_and_stores_nothing(env: _Env) -> None:
    with _client(env) as client:
        resp = _upload(client, "huge.png", b"\x00" * (20 * 1024 * 1024 + 1), "image/png")

    assert resp.status_code == 413
    error = resp.json()["error"]
    assert error["code"] == "ATTACHMENT_TOO_LARGE"
    assert "20 MB" in error["message"]
    assert not env.media.exists() or list(env.media.iterdir()) == []


class _SpyAttachments:
    """An attachment service that records whether the handler ever reached it."""

    def __init__(self) -> None:
        self.uploads = 0

    async def upload(self, **_: object) -> Any:
        self.uploads += 1
        raise AssertionError("the handler must not run for an oversized body")


@pytest.mark.acceptance(
    spec="chat", scenario="an upload declaring an oversized body is refused before it is read"
)
def test_a_declared_oversized_body_is_413_before_the_handler_runs(env: _Env) -> None:
    spy = _SpyAttachments()
    env.app.dependency_overrides[get_attachment_service] = lambda: spy
    body = b"\x00" * (MAX_ATTACHMENT_BYTES + MULTIPART_OVERHEAD_BYTES + 1)
    with _client(env) as client:
        resp = _upload(client, "huge.png", body, "image/png")
    with TestClient(env.app) as anonymous:
        unauthenticated = _upload(anonymous, "huge.png", body, "image/png")

    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "ATTACHMENT_TOO_LARGE"
    assert spy.uploads == 0
    assert not env.media.exists()
    # The token is checked first: a stranger learns nothing about the limit.
    assert unauthenticated.status_code == 401


def test_a_form_with_more_than_one_file_is_refused(env: _Env) -> None:
    with _client(env) as client:
        resp = client.post(
            "/api/v1/chat/attachments",
            files=[("file", ("a.png", _PNG, "image/png")), ("file", ("b.png", _PNG, "image/png"))],
        )

    assert resp.status_code == 400
    assert not env.media.exists()


@pytest.mark.acceptance(spec="chat", scenario="an image is stored under the type its bytes prove")
def test_an_image_is_stored_under_the_type_its_bytes_prove(env: _Env) -> None:
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
    with _client(env) as client:
        mislabelled = _upload(client, "photo.png", jpeg, "image/png")
        not_an_image = _upload(client, "fake.png", b"just some text", "image/png")

    assert mislabelled.status_code == 201, mislabelled.text
    assert mislabelled.json()["mime"] == "image/jpeg"
    assert not_an_image.status_code == 201, not_an_image.text
    assert not_an_image.json()["mime"] == "application/octet-stream"


@pytest.mark.acceptance(spec="chat", scenario="an upload of a type no agent can use is refused")
def test_unusable_type_is_415_and_stores_nothing(env: _Env) -> None:
    with _client(env) as client:
        resp = _upload(client, "clip.mp4", b"\x00\x00\x00\x18ftypmp42\x00", "video/mp4")

    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "ATTACHMENT_TYPE_UNSUPPORTED"
    assert not env.media.exists() or list(env.media.iterdir()) == []


def test_upload_requires_the_token(env: _Env) -> None:
    with TestClient(env.app) as client:
        resp = _upload(client, "a.png", _PNG, "image/png")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="chat", scenario="a web message carries its uploaded files as references"
)
def test_send_persists_the_uploads_as_references_after_the_text(env: _Env) -> None:
    with _client(env) as client:
        conv_id = _conversation(client)
        png = _upload(client, "shot.png", _PNG, "image/png").json()
        notes = _upload(client, "notes.md", b"# notes\n", "text/markdown").json()
        resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"text": "what is in these?", "attachment_ids": [png["id"], notes["id"]]},
        )
        assert resp.status_code == 202, resp.text
        rows = _messages_when_settled(client, conv_id)
        raw = client.get(f"/api/v1/chat/conversations/{conv_id}/messages").text

    user = next(r for r in rows if r["role"] == "user")
    assert [b["type"] for b in user["content"]] == ["text", "attachment", "attachment"]
    assert user["content"][0]["text"] == "what is in these?"
    assert [(b["filename"], b["mime"]) for b in user["content"][1:]] == [
        ("shot.png", "image/png"),
        ("notes.md", "text/markdown"),
    ]
    assert all("path" not in b for b in user["content"])
    assert str(env.media) not in raw


@pytest.mark.acceptance(
    spec="chat", scenario="a web-attached image reaches the agent the way a channel's does"
)
def test_the_adapter_receives_the_upload_rematerialised_from_history(env: _Env) -> None:
    with _client(env) as client:
        conv_id = _conversation(client)
        png = _upload(client, "shot.png", _PNG, "image/png").json()
        client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"text": "look", "attachment_ids": [png["id"]]},
        )
        _messages_when_settled(client, conv_id)

    assert env.adapter.recorded_attachments == [
        [
            Attachment(
                path=str(env.media / f"{png['id']}.png"), mime="image/png", filename="shot.png"
            )
        ]
    ]


@pytest.mark.acceptance(
    spec="chat", scenario="a message with files and no text is persisted with a stand-in"
)
def test_attachment_only_message_gets_a_stand_in_and_empty_is_refused(env: _Env) -> None:
    with _client(env) as client:
        conv_id = _conversation(client)
        png = _upload(client, "shot.png", _PNG, "image/png").json()
        resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"attachment_ids": [png["id"]]},
        )
        assert resp.status_code == 202, resp.text
        rows = _messages_when_settled(client, conv_id)
        title = client.get(f"/api/v1/chat/conversations/{conv_id}").json()["title"]
        empty = client.post(f"/api/v1/chat/conversations/{conv_id}/messages", json={})
        blank = client.post(f"/api/v1/chat/conversations/{conv_id}/messages", json={"text": "  "})

    user = next(r for r in rows if r["role"] == "user")
    assert user["content"][0] == {**user["content"][0], "type": "text"}
    assert user["content"][0]["text"] == "(sent 1 image: shot.png)"
    assert title == "shot.png"
    assert empty.status_code == 422
    assert blank.status_code == 422


@pytest.mark.acceptance(spec="chat", scenario="a message naming an unknown attachment is refused")
def test_unknown_attachment_id_is_422_and_nothing_is_persisted(env: _Env) -> None:
    with _client(env) as client:
        conv_id = _conversation(client)
        unknown = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"text": "see file", "attachment_ids": ["f" * 32]},
        )
        traversal = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"text": "see file", "attachment_ids": ["../../../etc/passwd"]},
        )
        rows = client.get(f"/api/v1/chat/conversations/{conv_id}/messages").json()["messages"]

    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "ATTACHMENT_NOT_FOUND"
    assert traversal.status_code == 422
    assert traversal.json()["error"]["code"] == "ATTACHMENT_NOT_FOUND"
    assert rows == []
    assert env.orchestrator.pending(conv_id) == []


def test_a_send_to_a_missing_conversation_is_404_before_its_attachments(env: _Env) -> None:
    with _client(env) as client:
        resp = client.post(
            "/api/v1/chat/conversations/nope/messages",
            json={"text": "hi", "attachment_ids": ["f" * 32]},
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_more_than_ten_attachments_is_refused(env: _Env) -> None:
    with _client(env) as client:
        conv_id = _conversation(client)
        resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"text": "many", "attachment_ids": ["f" * 32] * 11},
        )
    assert resp.status_code == 422


def test_a_pruned_upload_no_longer_resolves(env: _Env) -> None:
    with _client(env) as client:
        conv_id = _conversation(client)
        png = _upload(client, "shot.png", _PNG, "image/png").json()
        (env.media / f"{png['id']}.png").unlink()
        resp = client.post(
            f"/api/v1/chat/conversations/{conv_id}/messages",
            json={"text": "look", "attachment_ids": [png["id"]]},
        )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "ATTACHMENT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="chat", scenario="the chat-media prune deletes stale uploads and keeps fresh ones"
)
async def test_full_prune_sweeps_chat_media_by_age(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The composition root resolves both media dirs from HOME.
    monkeypatch.setenv("HOME", str(tmp_path))
    store = FileChatMediaStore(tmp_path / ".coffer" / "chat-media")
    stale = await store.save(data=b"old", filename="old.txt", mime="text/plain")
    fresh = await store.save(data=b"new", filename="new.txt", mime="text/plain")
    now = datetime.now(tz=UTC)
    old_ts = (now - timedelta(days=31)).timestamp()
    for name in (f"{stale.id}.txt", f"{stale.id}.json"):
        os.utime(store.root / name, (old_ts, old_ts))

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        svc = build_retention_service(
            session_maker(engine), audit=AuditService(SqlAlchemyAuditRepo(session_maker(engine)))
        )
        await svc.initialize_defaults()
        result = await svc.prune(now=now)
    finally:
        await engine.dispose()

    # The upload's two files (bytes + record) go; the fresh upload stays whole.
    assert result["chat_media"] == 2
    assert result["channel_media"] == 0
    assert await store.resolve(stale.id) is None
    assert await store.resolve(fresh.id) is not None
