"""End-to-end HTTP coverage for /api/v1/conversations/* (spec 008)."""

from __future__ import annotations

import json
import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.domain.chat.runtime import TextDelta
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import set_runtime_factory
from tests.integration.chat.fakes import FakeRuntime, FakeRuntimeFactory

TOKEN = "test-token-008"
SPEC = "008-builtin-agent-chat"


@pytest.fixture
def fake_factory():
    f = FakeRuntimeFactory()
    set_runtime_factory(f)
    yield f
    set_runtime_factory(None)


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int = 59700):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _parse_sse(text: str) -> list[dict]:
    out = []
    for chunk in text.split("\n\n"):
        chunk = chunk.strip()
        if chunk.startswith("data:"):
            out.append(json.loads(chunk[len("data:") :].strip()))
    return out


def test_requires_auth(tmp_path, monkeypatch, fake_factory):
    app = _app(tmp_path, monkeypatch)
    set_active_token(TOKEN)  # token configured, but the request omits the header
    with TestClient(app) as c:
        assert c.get("/api/v1/conversations").status_code == 401


def test_create_list_get_conversation(tmp_path, monkeypatch, fake_factory):
    app = _app(tmp_path, monkeypatch)
    with _client(app) as c:
        r = c.post("/api/v1/conversations", json={"target_ref": "builtin_agent:coffer"})
        assert r.status_code == 201, r.text
        conv = r.json()
        assert conv["target_ref"] == "builtin_agent:coffer"
        assert conv["title"] == "New chat"

        r = c.get("/api/v1/conversations")
        assert r.status_code == 200
        assert [x["id"] for x in r.json()["items"]] == [conv["id"]]

        r = c.get(f"/api/v1/conversations/{conv['id']}")
        assert r.status_code == 200
        assert r.json()["conversation"]["id"] == conv["id"]
        assert r.json()["messages"] == []


def test_create_rejects_non_chat_target(tmp_path, monkeypatch, fake_factory):
    app = _app(tmp_path, monkeypatch)
    with _client(app) as c:
        r = c.post("/api/v1/conversations", json={"target_ref": "mcp_server:foo"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "NOT_A_CHAT_TARGET"


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat", scenario="chat with the built-in agent streams a reply"
)
def test_send_streams_sse_and_persists(tmp_path, monkeypatch, fake_factory):
    fake_factory.runtime = FakeRuntime([TextDelta(text="Hel"), TextDelta(text="lo")])
    app = _app(tmp_path, monkeypatch)
    with _client(app) as c:
        conv = c.post("/api/v1/conversations", json={"target_ref": "builtin_agent:coffer"}).json()
        r = c.post(f"/api/v1/conversations/{conv['id']}/messages", json={"text": "hi"})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(r.text)
        assert events[-1] == {"type": "done"}
        assert "".join(e["text"] for e in events if e["type"] == "text_delta") == "Hello"

        detail = c.get(f"/api/v1/conversations/{conv['id']}").json()
        roles = [(m["role"], m["content"], m["status"]) for m in detail["messages"]]
        assert roles == [("user", "hi", "complete"), ("assistant", "Hello", "complete")]


@pytest.mark.acceptance(
    spec="008-builtin-agent-chat", scenario="send returns 503 when no LLM provider is configured"
)
def test_send_returns_503_when_llm_not_configured(tmp_path, monkeypatch, fake_factory):
    fake_factory.raise_llm_not_configured = True
    app = _app(tmp_path, monkeypatch)
    with _client(app) as c:
        conv = c.post("/api/v1/conversations", json={"target_ref": "builtin_agent:coffer"}).json()
        r = c.post(f"/api/v1/conversations/{conv['id']}/messages", json={"text": "hi"})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
        # Read path still works; nothing was persisted.
        detail = c.get(f"/api/v1/conversations/{conv['id']}").json()
        assert detail["messages"] == []


def test_whitespace_message_rejected(tmp_path, monkeypatch, fake_factory):
    fake_factory.runtime = FakeRuntime([TextDelta(text="x")])
    app = _app(tmp_path, monkeypatch)
    with _client(app) as c:
        conv = c.post("/api/v1/conversations", json={"target_ref": "builtin_agent:coffer"}).json()
        r = c.post(f"/api/v1/conversations/{conv['id']}/messages", json={"text": "    "})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "MESSAGE_REJECTED"


def test_rename_archive_restore_delete(tmp_path, monkeypatch, fake_factory):
    app = _app(tmp_path, monkeypatch)
    with _client(app) as c:
        conv = c.post("/api/v1/conversations", json={"target_ref": "builtin_agent:coffer"}).json()
        cid = conv["id"]
        assert (
            c.patch(f"/api/v1/conversations/{cid}", json={"title": "Renamed"}).json()["title"]
            == "Renamed"
        )
        assert c.post(f"/api/v1/conversations/{cid}/archive").json()["status"] == "archived"
        assert c.get("/api/v1/conversations?status=active").json()["items"] == []
        assert c.post(f"/api/v1/conversations/{cid}/restore").json()["status"] == "active"
        assert c.delete(f"/api/v1/conversations/{cid}").status_code == 204
        assert c.get(f"/api/v1/conversations/{cid}").status_code == 404


def test_stop_no_active_turn_is_noop(tmp_path, monkeypatch, fake_factory):
    app = _app(tmp_path, monkeypatch)
    with _client(app) as c:
        conv = c.post("/api/v1/conversations", json={"target_ref": "builtin_agent:coffer"}).json()
        assert c.post(f"/api/v1/conversations/{conv['id']}/stop").status_code == 204
