"""The facts the Memory page reads, over the real daemon: each partition's
sources and distil state, each memory's agents, and the last read of
the agents' memory (spec memory "Show a partition's memories read-only",
"Report the last read of the agents' memory").

Same boot as ``test_spec_scenarios_http``: the real app on a throwaway HOME,
memory root and SQLite file, with no internal connection (distil is
mechanical).
"""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.integration.memory.conftest import claude_code_config, init_repository

_TOKEN = "test-token-memory-page-facts"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}

_FILE = (
    "---\nname: python-lockfile\ndescription: Dependencies are locked with uv\n"
    "metadata:\n  type: project\n---\n\nRun uv sync --frozen.\n"
)


@pytest.fixture
def client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59340")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59349")
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".codex").mkdir(parents=True, exist_ok=True)
    app = create_app()
    set_active_token(_TOKEN)
    with TestClient(
        app, base_url="http://localhost", headers=_HEADERS, raise_server_exceptions=False
    ) as c:
        r = c.post("/api/v1/agents", json={"type": "claude_code", "name": "cc"})
        assert r.status_code == 201, r.text
        repository = init_repository(tmp_path / "coffer")
        claude_code_config(tmp_path / ".claude", repository, {"python-lockfile.md": _FILE})
        yield c
    set_active_token(None)


def test_a_distilled_partition_lists_its_sources_and_distil_time(
    client: TestClient,
) -> None:
    before = client.get("/api/v1/memory/reading").json()
    assert before["failures"] == []

    assert client.post("/api/v1/memory/sync").status_code == 200

    partitions = {
        p["name"]: p for p in client.get("/api/v1/memory/partitions").json()["partitions"]
    }
    coffer = partitions["coffer"]
    assert coffer["sources"] == ["claude-code"]
    assert coffer["distilled_at"] is not None
    assert coffer["waiting_entries"] == 0
    assert coffer["waiting_agents"] == []

    notes = client.get(f"/api/v1/memory/partitions/{coffer['uid']}/notes").json()["notes"]
    assert [n["agents"] for n in notes] == [["claude-code"]]

    reading = client.get("/api/v1/memory/reading").json()
    assert reading["read_at"] is not None
    assert reading["failures"] == []


def test_update_memory_is_not_listed_as_running_once_it_has_answered(
    client: TestClient,
) -> None:
    assert client.post("/api/v1/memory/sync").status_code == 200
    runs = client.get("/api/v1/upkeep/runs").json()["runs"]
    assert [r for r in runs if r["kind"] == "memory"] == []
