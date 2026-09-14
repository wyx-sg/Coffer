"""Shared test helpers for ``backend/tests/integration/surfaces/http/``.

``client`` boots the full FastAPI app (via ``create_app``) so knowledge
routes are wired exactly as production wires them — real SQLite, real
markdown files under a temp HOME, the real converter registry — then drives
them with a Starlette ``TestClient`` (an ``httpx.Client`` subclass). It pins
``COFFER_KNOWLEDGE_ROOT`` into ``tmp_path``, so no test here ever touches a
real ``~/.coffer``.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-knowledge-search-ingest"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))

    app = create_app()
    set_active_token(_TOKEN)
    with TestClient(
        app, base_url="http://localhost", headers=_HEADERS, raise_server_exceptions=False
    ) as c:
        yield c


def _create_collection(client: TestClient, name: str) -> None:
    resp = client.post("/api/v1/knowledge/collections", json={"name": name})
    assert resp.status_code == 201, resp.text


def _write_file(
    client: TestClient, *, directory: str, title: str, description: str, body: str
) -> str:
    resp = client.put(
        "/api/v1/knowledge/file",
        json={"title": title, "description": description, "body": body, "directory": directory},
    )
    assert resp.status_code == 200, resp.text
    path: str = resp.json()["path"]
    return path
