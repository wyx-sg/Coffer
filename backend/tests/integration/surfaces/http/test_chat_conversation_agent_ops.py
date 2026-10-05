"""PATCH / DELETE /api/v1/chat/conversations/{id} act on the agent's own session.

Boots the real app with a Claude Code agent registered and the Agent SDK's
session functions replaced, so the route, the chat service, the port at the
composition root and the sessions service run for real (spec chat "Rename and
delete a conversation through its agent").
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import claude_agent_sdk
import pytest
from starlette.testclient import TestClient

from coffer.application.chat import turn_state
from coffer.domain.chat.agent_config import AgentConfig
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.dependencies import get_chat_service

TOKEN = "test-token-chat-agent-ops"
SID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "61910")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "61919")
    set_active_token(TOKEN)
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    with TestClient(create_app(), headers={"X-Coffer-Token": TOKEN}) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "claude_code", "config_dir": str(config_dir)},
        )
        assert r.status_code == 201, r.text
        yield c


def _conversation(c: TestClient, session_id: str | None, *, title: str = "Chat") -> str:
    chat = get_chat_service()

    async def make() -> str:
        conv = await chat.create_conversation(
            agent_key="claude_code", channel_uid="chan-1", peer_chat_id="chat-9"
        )
        await chat.rename_conversation(conv.id, new_title=title)
        if session_id is not None:
            await chat.set_agent_config(
                conv.id, AgentConfig(cwd="/work/repo", session_id=session_id)
            )
        return conv.id

    return c.portal.call(make)  # type: ignore[union-attr]


def _title(c: TestClient, conv_id: str) -> str:
    return str(c.get(f"/api/v1/chat/conversations/{conv_id}").json()["title"])


def _ids(c: TestClient) -> list[str]:
    return [
        x["conversation_id"]
        for x in c.get("/api/v1/agent-sessions", params={"source": "chan-1"}).json()["sessions"]
    ]


@pytest.mark.acceptance(spec="chat", scenario="rename a conversation in place")
def test_rename_goes_through_the_agent_then_the_index(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        claude_agent_sdk, "rename_session", lambda sid, title: calls.append((sid, title))
    )
    conv_id = _conversation(client, SID)

    r = client.patch(f"/api/v1/chat/conversations/{conv_id}", json={"title": "Better"})

    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Better"
    assert calls == [(SID, "Better")]
    assert _title(client, conv_id) == "Better"


@pytest.mark.acceptance(spec="chat", scenario="a refused rename leaves the index alone")
def test_a_refused_rename_keeps_the_title_and_returns_the_agents_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(sid: str, title: str) -> None:
        raise ValueError("the agent will not rename this one")

    monkeypatch.setattr(claude_agent_sdk, "rename_session", refuse)
    conv_id = _conversation(client, SID, title="Old")

    r = client.patch(f"/api/v1/chat/conversations/{conv_id}", json={"title": "New"})

    assert r.status_code == 400, r.text
    assert "will not rename" in r.text
    assert _title(client, conv_id) == "Old"


@pytest.mark.acceptance(spec="chat", scenario="delete removes the native session and the index row")
def test_delete_cancels_the_turn_deletes_the_session_then_the_row(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(claude_agent_sdk, "delete_session", lambda sid: calls.append(sid))
    conv_id = _conversation(client, SID)
    other = _conversation(client, "another-session")
    turn_state.state_for(conv_id).active = turn_state.ActiveTurn()

    r = client.delete(f"/api/v1/chat/conversations/{conv_id}")

    assert r.status_code == 204, r.text
    assert calls == [SID]
    assert not turn_state.is_running(conv_id)
    assert _ids(client) == [other]


@pytest.mark.acceptance(
    spec="chat", scenario="a conversation with no session is deleted from the index only"
)
def test_a_conversation_with_no_session_is_renamed_and_deleted_in_the_index_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(*_: object) -> None:
        raise AssertionError("the agent must not be asked")

    monkeypatch.setattr(claude_agent_sdk, "rename_session", never)
    monkeypatch.setattr(claude_agent_sdk, "delete_session", never)
    conv_id = _conversation(client, None)

    renamed = client.patch(f"/api/v1/chat/conversations/{conv_id}", json={"title": "Fresh"})
    deleted = client.delete(f"/api/v1/chat/conversations/{conv_id}")

    assert renamed.status_code == 200 and renamed.json()["title"] == "Fresh"
    assert deleted.status_code == 204
    assert _ids(client) == []


def test_a_refused_delete_keeps_the_index_row(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(sid: str) -> None:
        raise ValueError("the agent will not delete this one")

    monkeypatch.setattr(claude_agent_sdk, "delete_session", refuse)
    conv_id = _conversation(client, SID)

    r = client.delete(f"/api/v1/chat/conversations/{conv_id}")

    assert r.status_code == 400, r.text
    assert _ids(client) == [conv_id]


@pytest.mark.acceptance(spec="chat", scenario="an unknown conversation is rejected")
def test_an_unknown_conversation_is_rejected(client: TestClient) -> None:
    renamed = client.patch("/api/v1/chat/conversations/nope", json={"title": "x"})
    deleted = client.delete("/api/v1/chat/conversations/nope")

    assert renamed.status_code == 404
    assert deleted.status_code == 404
