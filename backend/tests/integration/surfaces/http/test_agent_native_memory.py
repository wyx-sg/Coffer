"""HTTP: GET /api/v1/agents/{name}/native-memory (read-only discovery)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

pytestmark = pytest.mark.asyncio


async def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    app = create_app()
    return app


async def test_native_memory_lists_unmanaged_claude_facts(tmp_path, monkeypatch):
    # Seed a Claude Code project memory dir with two facts.
    mem = tmp_path / ".claude" / "projects" / "-Users-x-Proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("# index\n", encoding="utf-8")
    (mem / "a.md").write_text("fact a\n", encoding="utf-8")
    (mem / "b.md").write_text("fact b\n", encoding="utf-8")

    app = await _client(tmp_path, monkeypatch)
    async with app.router.lifespan_context(app):
        set_active_token("t")
        client = AsyncClient(
            transport=ASGITransport(app),
            base_url="http://t",
            headers={"X-Coffer-Token": "t", "X-Coffer-Actor": "user"},
        )
        try:
            await client.post(
                "/api/v1/agents",
                json={
                    "type": "claude_code",
                    "name": "claude",
                    "config_dir": str(tmp_path / ".claude"),
                },
            )
            r = await client.get("/api/v1/agents/claude/native-memory")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["unmanaged_fact_count"] == 2
            assert any(
                p["slug"] == "-Users-x-Proj" and p["fact_count"] == 2 for p in body["projects"]
            )
        finally:
            await client.aclose()
