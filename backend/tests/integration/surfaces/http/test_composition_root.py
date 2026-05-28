"""Integration tests for the composition root (app.py).

These tests verify that create_app() properly wires up all services and mounts
all four route groups. They use starlette.testclient.TestClient which correctly
fires the ASGI lifespan (startup / shutdown) - unlike ASGITransport which only
handles the http scope.
"""

import sqlite3

from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token


def test_app_mounts_all_kind_agnostic_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59100")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59109")

    app = create_app()
    with TestClient(app) as c:
        # set_active_token after lifespan startup so our token wins over daemon.json
        set_active_token("test-token")
        headers = {"X-Coffer-Token": "test-token"}

        # /daemon/status (unauthenticated)
        r = c.get("/api/v1/daemon/status")
        assert r.status_code == 200

        # /resources (token required, no resources yet)
        r = c.get("/api/v1/resources", headers=headers)
        assert r.status_code == 200
        assert r.json() == {"resources": []}

        # /audit (token required) — lifespan emits daemon_started so entries may be non-empty
        r = c.get("/api/v1/audit", headers=headers)
        assert r.status_code == 200
        assert "entries" in r.json()

        # /retention/policies (token required; audit_log + mcp_invocations policies seeded)
        r = c.get("/api/v1/retention/policies", headers=headers)
        assert r.status_code == 200
        body = r.json()
        table_names = {p["table_name"] for p in body["policies"]}
        assert "audit_log" in table_names
        assert "mcp_invocations" in table_names


def test_app_runs_alembic_migrations_on_startup(tmp_path, monkeypatch):
    """Lifespan startup migrates the DB so requests don't 'no such table' fail."""
    monkeypatch.setenv("HOME", str(tmp_path))
    db_path = tmp_path / "c.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59200")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59209")

    app = create_app()
    with TestClient(app) as c:
        set_active_token("test-token")
        r = c.get("/api/v1/resources", headers={"X-Coffer-Token": "test-token"})
        assert r.status_code == 200

    # DB file exists and has the resources table
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    table_names = {r[0] for r in rows}
    assert {"resources", "audit_log", "retention_policies"}.issubset(table_names)
