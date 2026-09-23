"""Acceptance scenarios that need the whole daemon: its routes, its database,
its audit log, and the built-in tools its gateway advertises.

Boots the real app via ``create_app`` against a fresh SQLite file under
``tmp_path`` (the app upgrades it to head on startup), with ``HOME``,
``COFFER_MEMORY_ROOT`` and ``COFFER_KNOWLEDGE_ROOT`` all pinned into
``tmp_path`` — nothing here reaches a real ``~/.coffer`` or ``~/.claude``. No
internal connection is configured, so distil takes its mechanical path.
"""

from __future__ import annotations

import pathlib
import shutil
import sqlite3

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.integration.memory.conftest import claude_code_config, init_repository

_TOKEN = "test-token-memory-scenarios"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}


def _cc_file(name: str, description: str, type_: str, body: str) -> str:
    return (
        f"---\nname: {name}\ndescription: {description}\n"
        f"metadata:\n  type: {type_}\n---\n\n{body}\n"
    )


_FILES = {
    "python-lockfile.md": _cc_file(
        "python-lockfile", "Dependencies are locked with uv", "project", "Run uv sync --frozen."
    ),
    "worktree-development.md": _cc_file(
        "worktree-development", "Always develop in a git worktree", "feedback", "Use worktrees."
    ),
}


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59320")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59329")
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".codex").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def client(home: pathlib.Path):  # type: ignore[no-untyped-def]
    app = create_app()
    set_active_token(_TOKEN)
    with TestClient(
        app, base_url="http://localhost", headers=_HEADERS, raise_server_exceptions=False
    ) as c:
        yield c


def _seed(c: TestClient, home: pathlib.Path) -> pathlib.Path:
    r = c.post("/api/v1/agents", json={"type": "claude_code", "name": "cc"})
    assert r.status_code == 201, r.text
    repository = init_repository(home / "coffer")
    claude_code_config(home / ".claude", repository, _FILES)
    return repository


def _partitions(c: TestClient) -> dict[str, dict]:  # type: ignore[type-arg]
    r = c.get("/api/v1/memory/partitions")
    assert r.status_code == 200, r.text
    return {p["name"]: p for p in r.json()["partitions"]}


def _sync_and_distil(c: TestClient, *, headers: dict[str, str] | None = None) -> None:
    r = c.post("/api/v1/memory/sync", headers=headers)
    assert r.status_code == 200, r.text
    for row in _partitions(c).values():
        r = c.post(f"/api/v1/memory/partitions/{row['uid']}/distil", headers=headers)
        assert r.status_code == 200, r.text


# --- Report unresolvable partitions -------------------------------------------


@pytest.mark.acceptance(
    spec="memory", scenario="list an orphaned partition as unresolvable and delete it"
)
def test_an_orphaned_partition_is_listed_unresolvable_and_deletes_cleanly(
    client: TestClient, home: pathlib.Path
) -> None:
    repository = _seed(client, home)
    _sync_and_distil(client)
    shutil.rmtree(repository)

    listed = _partitions(client)
    assert listed["coffer"]["unresolvable"] is True

    r = client.delete(f"/api/v1/resources/{listed['coffer']['uid']}")
    assert r.status_code in (200, 204), r.text

    after = _partitions(client)
    assert "coffer" not in after
    assert "global" in after


# --- Audit every lifecycle act ------------------------------------------------


@pytest.mark.acceptance(
    spec="memory", scenario="audit a requested aggregation and distil with their actor"
)
def test_a_requested_aggregation_and_distil_each_record_one_event_naming_the_user(
    client: TestClient, home: pathlib.Path
) -> None:
    _seed(client, home)
    headers = {**_HEADERS, "X-Coffer-Actor": "alice"}

    r = client.post("/api/v1/memory/sync", headers=headers)
    assert r.status_code == 200, r.text
    uid = _partitions(client)["coffer"]["uid"]
    r = client.post(f"/api/v1/memory/partitions/{uid}/distil", headers=headers)
    assert r.status_code == 200, r.text

    def events(event_type: str) -> list[dict]:  # type: ignore[type-arg]
        r = client.get("/api/v1/audit", params={"event_type": event_type, "limit": 500})
        assert r.status_code == 200, r.text
        return list(r.json()["entries"])

    # The daemon's own interval workers also run a pass on startup, under
    # their own actor — that is a scheduled pass, not the one requested here.
    aggregated = [e for e in events("memory_aggregated") if e["actor"] == "alice"]
    distilled = [e for e in events("memory_distilled") if e["actor"] == "alice"]
    assert len(aggregated) == 1
    assert len(distilled) == 1
    assert aggregated[0]["details"]["entries_written"] == 2  # the requested pass itself
    assert distilled[0]["resource_name"] == "coffer"
    others = [
        e for e in events("memory_aggregated") + events("memory_distilled") if e["actor"] != "alice"
    ]
    assert all(e["actor"] not in ("user", "api") for e in others)


# --- Add no table of its own --------------------------------------------------


@pytest.mark.acceptance(
    spec="memory", scenario="keep partitions in the resources table and files only"
)
def test_after_both_passes_no_memory_table_exists_and_each_partition_is_one_row(
    client: TestClient, home: pathlib.Path
) -> None:
    _seed(client, home)
    _sync_and_distil(client)
    partitions = _partitions(client)
    assert sorted(partitions) == ["coffer", "global"]

    with sqlite3.connect(home / "c.db") as db:
        head = db.execute("SELECT version_num FROM alembic_version").fetchall()
        tables = [
            name for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        ]
        rows = db.execute("SELECT uid, name FROM resources WHERE kind = 'memory'").fetchall()

    assert len(head) == 1  # upgraded, to one head
    assert "resources" in tables
    assert [t for t in tables if "memory" in t.lower()] == []
    assert sorted(name for _, name in rows) == ["coffer", "global"]
    assert {uid for uid, _ in rows} == {p["uid"] for p in partitions.values()}


# --- Expose only coffer__recall -----------------------------------------------


@pytest.mark.acceptance(
    spec="memory", scenario="advertise recall as a locator and no remember tool"
)
def test_the_gateway_lists_recall_as_a_literal_locator_and_nothing_to_remember_with(
    client: TestClient,
) -> None:
    init = client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert init.status_code == 200, init.text
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers={**_HEADERS, "Mcp-Session-Id": init.headers["mcp-session-id"]},
    )
    assert r.status_code == 200, r.text
    builtins = {
        t["name"]: t for t in r.json()["result"]["tools"] if t["name"].startswith("coffer__")
    }

    assert "coffer__recall" in builtins
    description = builtins["coffer__recall"]["description"].lower()
    assert "locate" in description
    assert "literal" in description
    assert "path" in description  # it answers with where to read

    assert "coffer__remember" not in builtins
    memory_tools = [
        name for name in builtins if "memory" in name or "remember" in name or "recall" in name
    ]
    assert memory_tools == ["coffer__recall"]
