"""HTTP coverage for GET /api/v1/agents/{name}/transcripts and .../session.

HOME is redirected at ``tmp_path``, so the registered agent's config dir — and
every transcript the reader walks — lives inside the test's own temp tree. The
user's real ``~/.claude`` / ``~/.codex`` is never read.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.agent import paths
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


# ---------------------------------------------------------------------------
# The boot-time warm pass (FR-047) — the first visit must not be the slow one
# ---------------------------------------------------------------------------


def test_warm_pass_fills_the_sidecar_and_audits_nothing(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    """The worker is wired into the lifespan, warms the reader the listing uses,
    and stays a cache pass: FR-011 lets no workspace listing audit, this one
    included."""
    _register_codex_with_transcripts(client, tmp_path)
    sidecar = paths.transcript_summaries_path()
    # The worker's loop is already running — it swept once at startup, when no
    # agent existed, and sweeps again on its interval. Racing that schedule is
    # not what this test is about, so it starts from a known-empty sidecar
    # instead of asserting one: what is under test is the pass FILLING it.
    sidecar.unlink(missing_ok=True)
    before = len(client.get("/api/v1/audit").json()["entries"])

    worker = client.app.state.background_workers.warm_worker  # type: ignore[attr-defined]
    client.portal.call(worker.run_once)  # type: ignore[union-attr]

    stored = json.loads(sidecar.read_text(encoding="utf-8"))
    assert len(stored) == 3
    assert all("message_count" in entry for entry in stored.values())
    assert len(client.get("/api/v1/audit").json()["entries"]) == before

    # The listing is served from what the warm pass parsed — same reader, one cache.
    body = client.get("/api/v1/agents/cx/transcripts").json()
    assert [s["session_id"] for s in body["sessions"]] == ["a", "c", "b"]


# ---------------------------------------------------------------------------
# Reading ONE session — the first surface that puts a transcript body on the wire
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="read one of the agent's conversations",
)
def test_reads_one_session_as_turns(client: TestClient, tmp_path: pathlib.Path) -> None:
    """The summary the row showed, plus the turns that row deliberately omitted."""
    sessions = _register_codex_with_transcripts(client, tmp_path)
    path = str(sessions / "rollout-a.jsonl")

    r = client.get("/api/v1/agents/cx/transcripts/session", params={"path": path})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == "a"
    assert body["title"] == "fix the alpha login bug"
    assert body["project_path"] == "/proj/alpha"
    assert body["source_path"] == path
    assert [(m["role"], m["text"]) for m in body["messages"]] == [
        ("user", "fix the alpha login bug"),
        ("assistant", "ok"),
    ]
    # The window and the whole are separate numbers, so "200 of 812" is sayable.
    assert body["message_count"] == 2
    assert body["offset"] == 0


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="read one of the agent's conversations",
)
def test_session_read_scrubs_secrets_and_bounds_the_window(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    """A prompt is exactly where a pasted key would be, and a file is huge."""
    sessions = _register_codex_with_transcripts(client, tmp_path)
    _write_codex_session(
        sessions,
        sid="s",
        cwd="/proj/secret",
        ts_start="2026-05-04T00:00:00Z",
        ts_end="2026-05-04T00:01:00Z",
        user_text="deploy with sk-abcdefghijklmnopqrstuvwx please",
    )
    path = str(sessions / "rollout-s.jsonl")

    body = client.get(
        "/api/v1/agents/cx/transcripts/session", params={"path": path, "limit": 1}
    ).json()
    assert "sk-abcdefghijklmnopqrstuvwx" not in body["messages"][0]["text"]
    assert "[redacted]" in body["messages"][0]["text"]
    # limit=1 returns the first turn only, while the count still says there are 2.
    assert len(body["messages"]) == 1
    assert body["message_count"] == 2

    # …and offset walks the rest of them.
    rest = client.get(
        "/api/v1/agents/cx/transcripts/session", params={"path": path, "offset": 1}
    ).json()
    assert [m["role"] for m in rest["messages"]] == ["assistant"]
    assert rest["offset"] == 1


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="read one of the agent's conversations",
)
def test_session_read_refuses_a_path_outside_the_agents_transcripts(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    """The listing's source_path is the only authority the caller has."""
    _register_codex_with_transcripts(client, tmp_path)
    outsider = tmp_path / "elsewhere.jsonl"
    outsider.write_text('{"type": "message", "role": "user", "content": "hi"}\n', encoding="utf-8")

    r = client.get("/api/v1/agents/cx/transcripts/session", params={"path": str(outsider)})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"

    # A file that WOULD be contained but is gone gives the same answer, so the
    # difference cannot be used to probe what exists outside the sessions dir.
    missing = client.get(
        "/api/v1/agents/cx/transcripts/session",
        params={"path": str(tmp_path / ".codex" / "sessions" / "nope.jsonl")},
    )
    assert missing.status_code == 404


def test_session_read_emits_no_audit_event(client: TestClient, tmp_path: pathlib.Path) -> None:
    """FR-011: a workspace listing does not audit, nor does reading one of its rows."""
    sessions = _register_codex_with_transcripts(client, tmp_path)
    before = len(client.get("/api/v1/audit").json()["entries"])
    client.get(
        "/api/v1/agents/cx/transcripts/session",
        params={"path": str(sessions / "rollout-a.jsonl")},
    )
    assert len(client.get("/api/v1/audit").json()["entries"]) == before
