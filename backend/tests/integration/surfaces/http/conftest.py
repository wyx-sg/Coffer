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

_TOKEN = "test-token-knowledge-routes"
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


def _submit(
    client: TestClient,
    *,
    collection: str,
    title: str,
    description: str,
    body: str,
) -> str:
    """Submit material through the route and return the document it became.

    The app booted here has no internal model configured, so material is
    promoted to a document on the spot rather than waiting in the inbox (spec
    knowledge FR-029) — which is what gives the caller a path to read back.
    """
    resp = client.post(
        "/api/v1/knowledge/material",
        json={"collection": collection, "title": title, "description": description, "body": body},
    )
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["status"] == "written", out
    path: str = out["path"]
    return path


def _hold_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the running service believe a model could merge material, so a
    submission waits in the inbox instead of being promoted.

    Patched on the service rather than by configuring a provider: the only
    thing under test is where material lands, and a real provider would bring
    a model call into a tier that makes none.
    """
    from coffer.surfaces.http.knowledge.dependencies import get_knowledge_service

    async def _yes() -> bool:
        return True

    monkeypatch.setattr(get_knowledge_service(), "_merge_available", _yes)
