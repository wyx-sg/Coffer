"""Integration acceptance tests for GET /api/v1/memory_stores/{name}/rules."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.knowledge.paths import rules_path
from coffer.infrastructure.memory.rules_files import append_rule
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "rules-route-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="the rules read surface returns the stored rules",
)
def test_rules_read_surface_returns_stored_rules(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59900)
    store_dir = tmp_path / "memory" / "global"
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        # Provision the global store first
        r = c.get("/api/v1/memory_stores", headers=_HEADERS)
        assert r.status_code == 200, r.text

        # Seed the rules file directly
        store_dir.mkdir(parents=True, exist_ok=True)
        rule_text = "Always run make verify before pushing."
        append_rule(rules_path(store_dir), rule_text)

        # GET /rules should return the text
        r = c.get("/api/v1/memory_stores/global/rules", headers=_HEADERS)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "text" in data
        assert rule_text in data["text"]


def test_rules_returns_null_when_no_rules(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59910)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        # Provision the global store
        c.get("/api/v1/memory_stores", headers=_HEADERS)

        r = c.get("/api/v1/memory_stores/global/rules", headers=_HEADERS)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["text"] is None
