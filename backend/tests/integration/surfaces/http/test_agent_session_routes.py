"""HTTP coverage for /api/v1/agents/{uid}/sessions.

Boots the real app and registers a Claude Code and a Codex agent. The Agent SDK
functions are replaced with fakes and the Codex source is handed a fake
sessions source, so the route, the service, the cursor and the join with the conversations run
for real while the agents' own stores stay out of it.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import claude_agent_sdk
import pytest
from starlette.testclient import TestClient

from coffer.application.agent.native_session_service import SourcePage
from coffer.application.chat import turn_state
from coffer.domain.agent.native_sessions import NativeSession
from coffer.domain.agent.types import AgentType
from coffer.domain.chat.agent_config import AgentConfig
from coffer.surfaces.http import workspace_dependencies
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.dependencies import get_chat_service

TOKEN = "test-token-agent-sessions"
SID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "61900")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "61909")
    set_active_token(TOKEN)
    with TestClient(create_app(), headers={"X-Coffer-Token": TOKEN}) as c:
        yield c


def _register(c: TestClient, agent_type: str, config_dir: pathlib.Path) -> str:
    config_dir.mkdir(parents=True, exist_ok=True)
    r = c.post(
        "/api/v1/agents",
        json={"type": agent_type, "name": agent_type, "config_dir": str(config_dir)},
    )
    assert r.status_code == 201, r.text
    return r.json()["uid"]


def _info(session_id: str, ms: int, **extra: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "session_id": session_id,
        "summary": f"task {session_id}",
        "last_modified": ms,
        "custom_title": None,
        "first_prompt": None,
        "cwd": "/work/repo",
        "created_at": ms - 500,
    }
    fields.update(extra)
    return SimpleNamespace(**fields)


def _audit_types(c: TestClient, uid: str) -> list[str]:
    r = c.get("/api/v1/audit", params={"resource_uid": uid, "limit": 200})
    assert r.status_code == 200, r.text
    return [e["event_type"] for e in r.json()["entries"]]


def _conversation(c: TestClient, session_id: str, *, title: str = "Chat") -> str:
    """A channel conversation (a Telegram-style one) pointing at ``session_id``."""
    chat = get_chat_service()

    async def make() -> str:
        conv = await chat.create_conversation(
            agent_key="claude_code", channel_uid="chan-1", peer_chat_id="chat-9"
        )
        await chat.rename_conversation(conv.id, new_title=title)
        await chat.set_agent_config(conv.id, AgentConfig(cwd="/work/repo", session_id=session_id))
        return conv.id

    return c.portal.call(make)  # type: ignore[union-attr]


def _conversation_ids(c: TestClient) -> list[str]:
    r = c.get("/api/v1/agent-sessions", params={"source": "chan-1"})
    assert r.status_code == 200, r.text
    return [x["conversation_id"] for x in r.json()["sessions"]]


@pytest.mark.acceptance(
    spec="agent-registry", scenario="browse an agent's native sessions with title and search"
)
def test_list_searches_pages_and_audits_nothing(
    client: TestClient, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        claude_agent_sdk,
        "list_sessions",
        lambda: [_info(f"s{i}", 1000 + i, cwd=f"/work/p{i % 2}") for i in range(5)],
    )
    uid = _register(client, "claude_code", tmp_path / ".claude")
    before = _audit_types(client, uid)

    first = client.get(f"/api/v1/agents/{uid}/sessions", params={"limit": 2})
    assert first.status_code == 200, first.text
    body = first.json()
    assert [s["session_id"] for s in body["sessions"]] == ["s4", "s3"]
    assert body["sessions"][0]["conversation_id"] is None
    assert body["sessions"][0]["channel_binding"] is None
    assert body["total"] == 5 and body["next_cursor"]
    row = body["sessions"][0]
    assert row["title"] == "task s4" and row["cwd"] == "/work/p0"
    assert row["created_at"] and row["last_activity_at"]

    second = client.get(
        f"/api/v1/agents/{uid}/sessions", params={"limit": 2, "cursor": body["next_cursor"]}
    )
    assert [s["session_id"] for s in second.json()["sessions"]] == ["s2", "s1"]

    # Search matches the working directory too, and addresses the agent by type.
    found = client.get("/api/v1/agents/claude-code/sessions", params={"q": "P1"})
    assert [s["session_id"] for s in found.json()["sessions"]] == ["s3", "s1"]
    assert found.json()["next_cursor"] is None and found.json()["total"] == 2

    # A cursor issued for one search is refused for another.
    stale = client.get(
        f"/api/v1/agents/{uid}/sessions",
        params={"q": "p1", "cursor": body["next_cursor"]},
    )
    assert stale.status_code == 400 and stale.json()["error"]["code"] == "CURSOR_INVALID"

    assert _audit_types(client, uid) == before


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="list Codex sessions through thread/list"
)
def test_codex_pages_with_the_servers_cursor_and_no_total(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    uid = _register(client, "codex", tmp_path / ".codex")
    seen: list[tuple[str | None, str | None]] = []

    class FakeCodex:
        async def list(
            self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
        ) -> SourcePage:
            seen.append((q, position[0] if position else None))
            row = NativeSession("t1", "Fix login", "/work", None, datetime(2026, 1, 1, tzinfo=UTC))
            return SourcePage([row], None if position else ["server-cursor"], None)

    service = workspace_dependencies.get_native_session_service()
    service._sources[AgentType.CODEX] = FakeCodex()  # type: ignore[index]

    first = client.get(f"/api/v1/agents/{uid}/sessions", params={"q": "login"}).json()
    assert first["total"] is None and first["next_cursor"]
    assert first["sessions"][0]["created_at"] is None
    last = client.get(
        f"/api/v1/agents/{uid}/sessions", params={"q": "login", "cursor": first["next_cursor"]}
    ).json()

    assert last["next_cursor"] is None
    assert seen == [("login", None), ("login", "server-cursor")]


@pytest.mark.acceptance(spec="agent-registry", scenario="rename a native session")
def test_rename_changes_the_agents_store_and_the_conversations_title(
    client: TestClient, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(claude_agent_sdk, "list_sessions", lambda: [])
    monkeypatch.setattr(
        claude_agent_sdk, "rename_session", lambda sid, title: calls.append((sid, title))
    )
    uid = _register(client, "claude_code", tmp_path / ".claude")
    conv_id = _conversation(client, SID)
    before = _audit_types(client, uid)

    renamed = client.patch(f"/api/v1/agents/{uid}/sessions/{SID}", json={"title": "Better"})

    assert renamed.status_code == 204
    assert calls == [(SID, "Better")]
    assert client.get(f"/api/v1/chat/conversations/{conv_id}").json()["title"] == "Better"
    assert _audit_types(client, uid) == before


@pytest.mark.acceptance(spec="agent-registry", scenario="delete a native session permanently")
def test_delete_cancels_the_turn_and_removes_the_conversations_row(
    client: TestClient, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(claude_agent_sdk, "delete_session", lambda sid: calls.append((sid,)))
    uid = _register(client, "claude_code", tmp_path / ".claude")
    conv_id = _conversation(client, SID)
    other = _conversation(client, "another-session")
    turn_state.state_for(conv_id).active = turn_state.ActiveTurn()
    before = _audit_types(client, uid)

    deleted = client.delete(f"/api/v1/agents/{uid}/sessions/{SID}")

    assert deleted.status_code == 204
    assert calls == [(SID,)]
    assert not turn_state.is_running(conv_id)
    assert _conversation_ids(client) == [other]
    assert _audit_types(client, uid) == before


@pytest.mark.acceptance(
    spec="agent-registry", scenario="a refused operation changes nothing in Coffer"
)
def test_a_refused_delete_keeps_the_conversation(
    client: TestClient, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(sid: str) -> None:
        raise ValueError("the agent will not delete this one")

    monkeypatch.setattr(claude_agent_sdk, "delete_session", refuse)
    uid = _register(client, "claude_code", tmp_path / ".claude")
    conv_id = _conversation(client, SID)

    refused = client.delete(f"/api/v1/agents/{uid}/sessions/{SID}")

    assert refused.status_code == 400, refused.text
    assert "will not delete" in refused.text
    assert _conversation_ids(client) == [conv_id]


@pytest.mark.acceptance(
    spec="agent-registry", scenario="a channel conversation's session carries its conversation"
)
def test_a_listed_session_carries_the_conversation_pointing_at_it(
    client: TestClient, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        claude_agent_sdk, "list_sessions", lambda: [_info(SID, 2000), _info("plain", 1000)]
    )
    uid = _register(client, "claude_code", tmp_path / ".claude")
    conv_id = _conversation(client, SID)
    turn_state.state_for(conv_id).active = turn_state.ActiveTurn()

    rows = client.get(f"/api/v1/agents/{uid}/sessions").json()["sessions"]
    linked, plain = rows

    assert linked["session_id"] == SID
    assert linked["conversation_id"] == conv_id
    assert linked["running"] is True and linked["needs_you"] is False
    assert linked["channel_binding"]["channel_uid"] == "chan-1"
    assert linked["channel_binding"]["chat_id"] == "chat-9"
    assert plain["conversation_id"] is None and plain["running"] is False
    assert plain["needs_you"] is False and plain["channel_binding"] is None


@pytest.mark.acceptance(spec="agent-registry", scenario="an unknown session is not found")
def test_bad_ids_unknown_sessions_and_unknown_agents(
    client: TestClient, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(sid: str) -> None:
        raise FileNotFoundError(sid)

    monkeypatch.setattr(claude_agent_sdk, "delete_session", missing)
    uid = _register(client, "claude_code", tmp_path / ".claude")

    bad = client.delete(f"/api/v1/agents/{uid}/sessions/not.valid")
    gone = client.delete(f"/api/v1/agents/{uid}/sessions/{SID}")
    empty = client.patch(f"/api/v1/agents/{uid}/sessions/{SID}", json={"title": "   "})
    no_agent = client.get("/api/v1/agents/8c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f/sessions")

    assert bad.status_code == 400, bad.text
    assert gone.status_code == 404, gone.text
    assert empty.status_code == 400, empty.text
    assert no_agent.status_code == 404, no_agent.text
