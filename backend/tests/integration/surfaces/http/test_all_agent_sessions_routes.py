"""HTTP coverage for GET /api/v1/agent-sessions — every agent's sessions in one list.

Boots the real app with a Claude Code and a Codex agent registered; both
agents' session sources are replaced with fakes that page by offset, so the
route, the merge, the cursor and the join with the conversation index run for
real while the agents' own stores stay out of it.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.testclient import TestClient

from coffer.application.agent.native_session_service import SourcePage
from coffer.domain.agent.native_sessions import NativeSession
from coffer.domain.agent.types import AgentType
from coffer.domain.chat.agent_config import AgentConfig
from coffer.surfaces.http import workspace_dependencies
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.dependencies import get_chat_service

TOKEN = "test-token-all-agent-sessions"
SID_LINKED = "550e8400-e29b-41d4-a716-446655440000"
URL = "/api/v1/agent-sessions"


def _at(hour: int) -> datetime:
    return datetime(2026, 9, 1, hour, tzinfo=UTC)


def _row(session_id: str, hour: int) -> NativeSession:
    return NativeSession(session_id, f"task {session_id}", "/work", _at(hour), _at(hour))


class _FakeSource:
    """Pages over ``rows`` by offset; ``fail`` makes every listing raise."""

    def __init__(self, rows: list[NativeSession]) -> None:
        self.rows = rows
        self.fail: Exception | None = None

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        if self.fail is not None:
            raise self.fail
        start = int(position[0]) if position else 0
        rows = sorted(self.rows, key=lambda r: r.last_activity_at, reverse=True)  # type: ignore[arg-type, return-value]
        rows = [r for r in rows if not q or q.lower() in r.title.lower()]
        more = start + limit < len(rows)
        return SourcePage(rows[start : start + limit], [start + limit] if more else None, None)


@pytest.fixture
def client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "61920")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "61929")
    set_active_token(TOKEN)
    with TestClient(create_app(), headers={"X-Coffer-Token": TOKEN}) as c:
        for agent_type in ("claude_code", "codex"):
            config_dir = tmp_path / f".{agent_type}"
            config_dir.mkdir()
            r = c.post(
                "/api/v1/agents",
                json={"type": agent_type, "name": agent_type, "config_dir": str(config_dir)},
            )
            assert r.status_code == 201, r.text
        yield c


def _fake_sources(
    claude: list[NativeSession], codex: list[NativeSession]
) -> tuple[_FakeSource, _FakeSource]:
    service = workspace_dependencies.get_native_session_service()
    fakes = (_FakeSource(claude), _FakeSource(codex))
    service._sources[AgentType.CLAUDE_CODE] = fakes[0]  # type: ignore[index]
    service._sources[AgentType.CODEX] = fakes[1]  # type: ignore[index]
    return fakes


def _conversation(c: TestClient, *, channel_uid: str, session_id: str | None) -> str:
    chat = get_chat_service()

    async def make() -> str:
        conv = await chat.create_conversation(
            agent_key="claude_code", channel_uid=channel_uid, peer_chat_id="chat-9"
        )
        await chat.rename_conversation(conv.id, new_title="From the channel")
        if session_id is not None:
            await chat.set_agent_config(conv.id, AgentConfig(cwd="/work", session_id=session_id))
        return conv.id

    return c.portal.call(make)  # type: ignore[union-attr]


def _ids(body: dict[str, Any]) -> list[str | None]:
    return [s["session_id"] for s in body["sessions"]]


@pytest.mark.acceptance(
    spec="agent-registry", scenario="sessions from two agents are listed in one order"
)
def test_two_agents_are_merged_newest_first_and_paged_by_one_cursor(client: TestClient) -> None:
    _fake_sources([_row("c10", 10), _row("c8", 8)], [_row("x9", 9)])

    first = client.get(URL, params={"limit": 2}).json()
    assert _ids(first) == ["c10", "x9"]
    assert [s["agent_key"] for s in first["sessions"]] == ["claude_code", "codex"]
    assert first["next_cursor"] and "total" not in first and first["unavailable"] == []

    second = client.get(URL, params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert _ids(second) == ["c8"]
    assert second["next_cursor"] is None and "total" not in second


@pytest.mark.acceptance(spec="agent-registry", scenario="the listing narrows by source and agent")
def test_the_listing_narrows_by_source_and_agent_and_binds_its_cursor(client: TestClient) -> None:
    _fake_sources([_row(SID_LINKED, 10), _row("local-c", 7)], [_row("x9", 9)])
    _conversation(client, channel_uid="chan-1", session_id=SID_LINKED)

    assert _ids(client.get(URL, params={"source": "local"}).json()) == ["x9", "local-c"]
    channel = client.get(URL, params={"source": "chan-1"}).json()
    assert _ids(channel) == [SID_LINKED]
    assert channel["sessions"][0]["channel_binding"]["channel_uid"] == "chan-1"
    mixed = client.get(URL, params={"source": "local,chan-1"}).json()
    assert _ids(mixed) == [SID_LINKED, "x9", "local-c"]
    assert _ids(client.get(URL, params={"agent": "codex"}).json()) == ["x9"]
    assert _ids(client.get(URL, params={"agent": "codex", "source": "local"}).json()) == ["x9"]
    assert _ids(client.get(URL, params={"q": "local"}).json()) == ["local-c"]

    paged = client.get(URL, params={"source": "local", "limit": 1}).json()
    assert paged["next_cursor"]
    for other in ({"source": "chan-1"}, {"source": "local", "agent": "codex"}, {"q": "x"}):
        bad = client.get(URL, params={**other, "cursor": paged["next_cursor"]})
        assert bad.status_code == 400
        assert bad.json()["error"]["code"] == "CURSOR_INVALID"
    ok = client.get(URL, params={"source": "local", "limit": 1, "cursor": paged["next_cursor"]})
    assert _ids(ok.json()) == ["local-c"]


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="a channel conversation with no session yet is listed under its channel",
)
def test_a_channel_conversation_without_a_session_is_listed_under_its_channel(
    client: TestClient,
) -> None:
    _fake_sources([_row("c10", 10)], [])
    conv_id = _conversation(client, channel_uid="chan-2", session_id=None)

    body = client.get(URL, params={"source": "chan-2"}).json()

    assert len(body["sessions"]) == 1
    row = body["sessions"][0]
    assert row["session_id"] is None and row["conversation_id"] == conv_id
    assert row["title"] == "From the channel" and row["agent_key"] == "claude_code"
    assert row["channel_binding"]["channel_uid"] == "chan-2"
    assert body["next_cursor"] is None and "total" not in body
    # It is not a local session, so it is not listed without its channel.
    assert _ids(client.get(URL).json()) == ["c10"]


@pytest.mark.acceptance(
    spec="agent-registry", scenario="one agent failing leaves the others listed"
)
def test_one_agent_failing_leaves_the_others_listed(client: TestClient) -> None:
    _claude, codex = _fake_sources([_row("c10", 10)], [_row("x9", 9)])
    codex.fail = RuntimeError("codex app-server did not start")

    body = client.get(URL).json()

    assert _ids(body) == ["c10"]
    assert body["unavailable"] == [{"agent": "codex", "reason": "codex app-server did not start"}]
    assert body["next_cursor"]  # Codex's position is kept for a retry

    codex.fail = None
    retry = client.get(URL, params={"cursor": body["next_cursor"]}).json()
    assert _ids(retry) == ["x9"] and retry["unavailable"] == []
