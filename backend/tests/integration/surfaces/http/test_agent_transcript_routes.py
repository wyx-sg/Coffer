"""HTTP coverage for GET /api/v1/agents/{uid}/transcripts and .../session.

HOME is redirected at ``tmp_path``, so the registered agent's config dir — and
every transcript the reader walks — lives inside the test's own temp tree. The
user's real ``~/.claude`` / ``~/.codex`` is never read.

Both routes address the agent by its immutable ``uid`` (ADR
resource-identity-is-an-immutable-uid), never by the label the user typed, so
every test here takes the uid straight off the registration response rather than
re-spelling the name in the URL. The ``path`` query parameter is untouched by
that change: it is a filesystem path the listing handed back, not an identity.
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

#: A well-formed uid that no resource in these tests was ever minted with. It is
#: uid-shaped on purpose: the route must 404 because nothing answers to this
#: identity, not because the string could not be an identity in the first place.
ABSENT_UID = "3f2b1c0d4e5a6b7c8d9e0f1a2b3c4d5e"


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


def _register_codex_with_transcripts(
    c: TestClient, tmp_path: pathlib.Path
) -> tuple[str, pathlib.Path]:
    """Register a codex agent labelled ``cx`` holding three transcript sessions.

    Returns ``(uid, sessions_dir)``: the uid the registration minted — which is
    what the transcript routes are addressed by — and the directory the three
    ``.jsonl`` files were written into, so a caller can name one of them in the
    ``path`` query parameter.
    """
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
    return r.json()["uid"], sessions


@pytest.fixture
def client(tmp_path: pathlib.Path, monkeypatch) -> TestClient:
    with _client(_app(tmp_path, monkeypatch, 8710)) as c:
        yield c


def test_lists_sessions_newest_activity_first(client: TestClient, tmp_path: pathlib.Path) -> None:
    uid, sessions = _register_codex_with_transcripts(client, tmp_path)
    r = client.get(f"/api/v1/agents/{uid}/transcripts")
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
    uid, _sessions = _register_codex_with_transcripts(client, tmp_path)
    body = client.get(f"/api/v1/agents/{uid}/transcripts").json()
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
    uid, _sessions = _register_codex_with_transcripts(client, tmp_path)
    body = client.get(f"/api/v1/agents/{uid}/transcripts", params={"q": "beta"}).json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == "b"


def test_project_filter_is_exact(client: TestClient, tmp_path: pathlib.Path) -> None:
    uid, _sessions = _register_codex_with_transcripts(client, tmp_path)
    body = client.get(f"/api/v1/agents/{uid}/transcripts", params={"project": "/proj/alpha"}).json()
    assert {s["session_id"] for s in body["sessions"]} == {"a", "c"}


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="browse an agent's transcript history with title, search, and sort",
)
def test_sort_and_order_are_honoured(client: TestClient, tmp_path: pathlib.Path) -> None:
    uid, _sessions = _register_codex_with_transcripts(client, tmp_path)
    body = client.get(
        f"/api/v1/agents/{uid}/transcripts", params={"sort": "started_at", "order": "asc"}
    ).json()
    assert [s["session_id"] for s in body["sessions"]] == ["a", "b", "c"]


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="browse an agent's transcript history with title, search, and sort",
)
def test_pagination_pages_against_the_matched_total(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    uid, _sessions = _register_codex_with_transcripts(client, tmp_path)
    body = client.get(
        f"/api/v1/agents/{uid}/transcripts",
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
    r = client.post("/api/v1/agents", json={"type": "codex", "name": "cx"})
    assert r.status_code == 201, r.text
    body = client.get(f"/api/v1/agents/{r.json()['uid']}/transcripts").json()
    assert body == {"sessions": [], "total": 0, "limit": 100, "offset": 0}


def test_unknown_agent_is_404(client: TestClient) -> None:
    """A uid no agent answers to is 404 — not an empty listing.

    Nothing was registered in this test, so the lookup the service does before
    it touches the filesystem is the thing under assertion.
    """
    r = client.get(f"/api/v1/agents/{ABSENT_UID}/transcripts")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_bad_sort_value_is_422(client: TestClient, tmp_path: pathlib.Path) -> None:
    uid, _sessions = _register_codex_with_transcripts(client, tmp_path)
    r = client.get(f"/api/v1/agents/{uid}/transcripts", params={"sort": "title"})
    assert r.status_code == 422


def test_requires_a_token(tmp_path: pathlib.Path, monkeypatch) -> None:
    """The token is refused before the uid is ever looked up, so no agent is
    registered here: 401 must not depend on the uid naming anything."""
    app = _app(tmp_path, monkeypatch, 8720)
    set_active_token(TOKEN)
    with TestClient(app) as anon:
        r = anon.get(f"/api/v1/agents/{ABSENT_UID}/transcripts")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# The boot-time warm pass (FR-040) — the first visit must not be the slow one
# ---------------------------------------------------------------------------


def test_warm_pass_fills_the_sidecar_and_audits_nothing(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    """The worker is wired into the lifespan, warms the reader the listing uses,
    and stays a cache pass: FR-048 lets no workspace listing audit, this one
    included."""
    uid, _sessions = _register_codex_with_transcripts(client, tmp_path)
    sidecar = paths.transcript_summaries_path()
    # The worker's first sweep is a created task, not an awaited one, so it may
    # reach its target list before the agent above was registered or after it:
    # whether a sidecar is already on disk at this point is a matter of
    # scheduling. Deleting it makes what follows an assertion about THIS pass's
    # output rather than the startup one's. Whether the reader's in-memory cache
    # is warm from that sweep is the same coin toss, and that the pass writes the
    # file back regardless is pinned by the test below, deterministically.
    sidecar.unlink(missing_ok=True)
    before = len(client.get("/api/v1/audit").json()["entries"])

    worker = client.app.state.background_workers.warm_worker  # type: ignore[attr-defined]
    client.portal.call(worker.run_once)  # type: ignore[union-attr]

    stored = json.loads(sidecar.read_text(encoding="utf-8"))
    assert len(stored) == 3
    assert all("message_count" in entry for entry in stored.values())
    assert len(client.get("/api/v1/audit").json()["entries"]) == before

    # The listing is served from what the warm pass parsed — same reader, one cache.
    body = client.get(f"/api/v1/agents/{uid}/transcripts").json()
    assert [s["session_id"] for s in body["sessions"]] == ["a", "c", "b"]


def test_warm_pass_rebuilds_a_sidecar_deleted_under_a_hot_cache(
    client: TestClient, tmp_path: pathlib.Path
) -> None:
    """The sidecar is disposable, so the pass has to be able to put it back.

    The interesting state is the one the test above cannot pin down: the
    reader's in-memory cache is already warm AND the file is gone. Nothing has
    changed on disk, so a pass that only writes when it parsed something new
    writes nothing — and the sidecar the user deleted never comes back, which
    is exactly the case this worker exists for.
    """
    _register_codex_with_transcripts(client, tmp_path)
    sidecar = paths.transcript_summaries_path()
    worker = client.app.state.background_workers.warm_worker  # type: ignore[attr-defined]

    # Warm first: after this the in-memory cache holds all three files' stamps.
    client.portal.call(worker.run_once)  # type: ignore[union-attr]
    assert len(json.loads(sidecar.read_text(encoding="utf-8"))) == 3

    sidecar.unlink()
    client.portal.call(worker.run_once)  # type: ignore[union-attr]

    assert sidecar.is_file(), "a warm pass left the deleted sidecar deleted"
    assert len(json.loads(sidecar.read_text(encoding="utf-8"))) == 3


# ---------------------------------------------------------------------------
# Reading ONE session — the first surface that puts a transcript body on the wire
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="read one of the agent's conversations",
)
def test_reads_one_session_as_turns(client: TestClient, tmp_path: pathlib.Path) -> None:
    """The summary the row showed, plus the turns that row deliberately omitted."""
    uid, sessions = _register_codex_with_transcripts(client, tmp_path)
    # ``path`` stays a filesystem path — it is the source_path the listing gave,
    # not an identity, so the uid change leaves it exactly as it was.
    path = str(sessions / "rollout-a.jsonl")

    r = client.get(f"/api/v1/agents/{uid}/transcripts/session", params={"path": path})
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
    uid, sessions = _register_codex_with_transcripts(client, tmp_path)
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
        f"/api/v1/agents/{uid}/transcripts/session", params={"path": path, "limit": 1}
    ).json()
    assert "sk-abcdefghijklmnopqrstuvwx" not in body["messages"][0]["text"]
    assert "[redacted]" in body["messages"][0]["text"]
    # limit=1 returns the first turn only, while the count still says there are 2.
    assert len(body["messages"]) == 1
    assert body["message_count"] == 2

    # …and offset walks the rest of them.
    rest = client.get(
        f"/api/v1/agents/{uid}/transcripts/session", params={"path": path, "offset": 1}
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
    uid, _sessions = _register_codex_with_transcripts(client, tmp_path)
    outsider = tmp_path / "elsewhere.jsonl"
    outsider.write_text('{"type": "message", "role": "user", "content": "hi"}\n', encoding="utf-8")

    r = client.get(f"/api/v1/agents/{uid}/transcripts/session", params={"path": str(outsider)})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"

    # A file that WOULD be contained but is gone gives the same answer, so the
    # difference cannot be used to probe what exists outside the sessions dir.
    missing = client.get(
        f"/api/v1/agents/{uid}/transcripts/session",
        params={"path": str(tmp_path / ".codex" / "sessions" / "nope.jsonl")},
    )
    assert missing.status_code == 404


def test_session_read_emits_no_audit_event(client: TestClient, tmp_path: pathlib.Path) -> None:
    """FR-048: a workspace listing does not audit, nor does reading one of its rows."""
    uid, sessions = _register_codex_with_transcripts(client, tmp_path)
    before = len(client.get("/api/v1/audit").json()["entries"])
    client.get(
        f"/api/v1/agents/{uid}/transcripts/session",
        params={"path": str(sessions / "rollout-a.jsonl")},
    )
    assert len(client.get("/api/v1/audit").json()["entries"]) == before
