"""HTTP coverage for GET /api/v1/agents/{name}/transcripts.

HOME is redirected at ``tmp_path``, so the registered agent's config dir — and
every transcript the reader walks — lives inside the test's own temp tree. The
user's real ``~/.claude`` / ``~/.codex`` is never read.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-transcripts"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _write_codex_session(
    sessions_dir: pathlib.Path,
    *,
    sid: str,
    cwd: str,
    ts_start: str,
    ts_end: str,
    user_text: str,
) -> None:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {"timestamp": ts_start, "type": "session_meta", "payload": {"id": sid, "cwd": cwd}}
        ),
        json.dumps(
            {
                "timestamp": ts_start,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}],
                },
            }
        ),
        json.dumps(
            {
                "timestamp": ts_end,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "ok"}],
                },
            }
        ),
    ]
    (sessions_dir / f"rollout-{sid}.jsonl").write_text("\n".join(lines), encoding="utf-8")


def _register_codex_with_transcripts(c: TestClient, tmp_path: pathlib.Path) -> pathlib.Path:
    """Register a codex agent named ``cx`` holding three transcript sessions."""
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir(exist_ok=True)
    (codex_dir / "config.toml").write_text("", encoding="utf-8")
    sessions = codex_dir / "sessions" / "2026" / "05"
    _write_codex_session(
        sessions,
        sid="a",
        cwd="/proj/alpha",
        ts_start="2026-05-01T00:00:00Z",
        ts_end="2026-05-09T00:00:00Z",
        user_text="fix the alpha login bug",
    )
    _write_codex_session(
        sessions,
        sid="b",
        cwd="/proj/beta",
        ts_start="2026-05-02T00:00:00Z",
        ts_end="2026-05-02T02:00:00Z",
        user_text="add beta dashboard",
    )
    _write_codex_session(
        sessions,
        sid="c",
        cwd="/proj/alpha",
        ts_start="2026-05-03T00:00:00Z",
        ts_end="2026-05-03T00:30:00Z",
        user_text="refactor alpha payments",
    )
    r = c.post("/api/v1/agents", json={"type": "codex", "name": "cx"})
    assert r.status_code == 201, r.text
    return sessions


@pytest.fixture
def client(tmp_path: pathlib.Path, monkeypatch) -> TestClient:
    with _client(_app(tmp_path, monkeypatch, 8710)) as c:
        yield c


def test_lists_sessions_newest_activity_first(client: TestClient, tmp_path: pathlib.Path) -> None:
    sessions = _register_codex_with_transcripts(client, tmp_path)
    r = client.get("/api/v1/agents/cx/transcripts")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert [s["session_id"] for s in body["sessions"]] == ["a", "c", "b"]
    first = body["sessions"][0]
    assert first["title"] == "fix the alpha login bug"
    assert first["project_path"] == "/proj/alpha"
    assert first["message_count"] == 2
    assert first["started_at"].startswith("2026-05-01T00:00:00")
    assert first["last_activity_at"].startswith("2026-05-09T00:00:00")
    assert first["source_path"] == str(sessions / "rollout-a.jsonl")


def test_no_message_text_crosses_the_wire(client: TestClient, tmp_path: pathlib.Path) -> None:
    _register_codex_with_transcripts(client, tmp_path)
    body = client.get("/api/v1/agents/cx/transcripts").json()
    assert set(body["sessions"][0]) == {
        "session_id",
        "title",
        "project_path",
        "message_count",
        "started_at",
        "last_activity_at",
        "source_path",
    }


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="browse an agent's transcript history with title, search, and sort",
)
def test_search_filters_by_title_or_project(client: TestClient, tmp_path: pathlib.Path) -> None:
    _register_codex_with_transcripts(client, tmp_path)
    body = client.get("/api/v1/agents/cx/transcripts", params={"q": "beta"}).json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == "b"


def test_project_filter_is_exact(client: TestClient, tmp_path: pathlib.Path) -> None:
    _register_codex_with_transcripts(client, tmp_path)
    body = client.get("/api/v1/agents/cx/transcripts", params={"project": "/proj/alpha"}).json()
    assert {s["session_id"] for s in body["sessions"]} == {"a", "c"}


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="browse an agent's transcript history with title, search, and sort",
)
def test_sort_and_order_are_honoured(client: TestClient, tmp_path: pathlib.Path) -> None:
    _register_codex_with_transcripts(client, tmp_path)
    body = client.get(
        "/api/v1/agents/cx/transcripts", params={"sort": "started_at", "order": "asc"}
    ).json()
    assert [s["session_id"] for s in body["sessions"]] == ["a", "b", "c"]


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="browse an agent's transcript history with title, search, and sort",
)
def test_pagination_pages_against_the_matched_total(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    _register_codex_with_transcripts(client, tmp_path)
    body = client.get(
        "/api/v1/agents/cx/transcripts",
        params={"sort": "started_at", "order": "asc", "limit": 1, "offset": 1},
    ).json()
    assert body["total"] == 3
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert [s["session_id"] for s in body["sessions"]] == ["b"]


def test_agent_with_no_transcripts_lists_empty(client: TestClient, tmp_path: pathlib.Path) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir(exist_ok=True)
    (codex_dir / "config.toml").write_text("", encoding="utf-8")
    assert client.post("/api/v1/agents", json={"type": "codex", "name": "cx"}).status_code == 201
    body = client.get("/api/v1/agents/cx/transcripts").json()
    assert body == {"sessions": [], "total": 0, "limit": 100, "offset": 0}


def test_unknown_agent_is_404(client: TestClient) -> None:
    r = client.get("/api/v1/agents/nope/transcripts")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_bad_sort_value_is_422(client: TestClient, tmp_path: pathlib.Path) -> None:
    _register_codex_with_transcripts(client, tmp_path)
    r = client.get("/api/v1/agents/cx/transcripts", params={"sort": "title"})
    assert r.status_code == 422


def test_requires_a_token(tmp_path: pathlib.Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch, 8720)
    set_active_token(TOKEN)
    with TestClient(app) as anon:
        r = anon.get("/api/v1/agents/cx/transcripts")
    assert r.status_code == 401
