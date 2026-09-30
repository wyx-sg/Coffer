"""``/api/v1/daemon/port`` and ``/api/v1/storage`` (Settings > Daemon and > Data).

Spec daemon "Bind a fixed, settable port" and "Report what Coffer stores and
clear the rebuildable cache". Every test runs under a throwaway HOME.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.surfaces.http import daemon_routes
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.daemon_port_routes import router as port_router
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.storage_routes import router as storage_router

TOKEN = "t-port"


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def record(self, event_type, *, actor, details=None, **_kw):
        self.events.append((event_type, details or {}))


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    h = tmp_path / "home"
    (h / ".coffer").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    for var in (
        "COFFER_MEMORY_ROOT",
        "COFFER_AGENT_STATE_ROOT",
        "COFFER_KNOWLEDGE_ROOT",
        "COFFER_SKILLS_ROOT",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{h / '.coffer' / 'coffer.db'}")
    return h


@pytest.fixture
def audit() -> _Audit:
    return _Audit()


@pytest.fixture
def client(home, audit, monkeypatch):
    monkeypatch.setattr(daemon_routes, "_PORT", 8000)
    set_active_token(TOKEN)
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(port_router)
    app.include_router(storage_router)
    app.dependency_overrides[get_audit_service] = lambda: audit
    app.dependency_overrides[get_actor] = lambda: "ui"
    return AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
    )


def _config(home: Path) -> dict:
    path = home / ".coffer" / "daemon-config.json"
    return json.loads(path.read_text()) if path.exists() else {}


# --- the port ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_port_reads_the_default_and_the_bound_port(client):
    async with client:
        r = await client.get("/api/v1/daemon/port")
    assert r.status_code == 200
    assert r.json() == {"port": 8000, "bound_port": 8000, "pending": False}


@pytest.mark.asyncio
async def test_nothing_is_pending_while_no_port_is_saved(client, monkeypatch):
    # A daemon started in a test port range answers elsewhere than 8000 with
    # nothing saved: there is nothing to apply at the next start.
    monkeypatch.setattr(daemon_routes, "_PORT", 18300)
    async with client:
        r = await client.get("/api/v1/daemon/port")
    assert r.json() == {"port": 8000, "bound_port": 18300, "pending": False}


@pytest.mark.asyncio
async def test_the_port_routes_require_the_token(client):
    async with client:
        r = await client.get("/api/v1/daemon/port", headers={"X-Coffer-Token": ""})
    assert r.status_code == 401


# revise-web-ui-ia: daemon "a port set from the settings page is pending until
# restart" — the acceptance marker is added when the change is archived.
@pytest.mark.asyncio
async def test_a_port_set_from_the_settings_page_is_pending_until_restart(client, home):
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    taken = holder.getsockname()[1]
    try:
        async with client:
            r = await client.put("/api/v1/daemon/port", json={"port": 8123})
            assert r.status_code == 200
            assert r.json() == {"port": 8123, "bound_port": 8000, "pending": True}
            assert _config(home)["port"] == 8123

            refused = await client.put("/api/v1/daemon/port", json={"port": taken})
        assert refused.status_code == 409
        error = refused.json()["error"]
        assert error["code"] == "PORT_IN_USE"
        assert error["details"]["port"] == taken
        # This test process holds it, and says so by pid.
        assert error["details"]["holder"]["pid"] == os.getpid()
        assert str(os.getpid()) in error["message"]
        assert _config(home)["port"] == 8123  # the file is unchanged
    finally:
        holder.close()


@pytest.mark.asyncio
async def test_a_port_outside_the_range_is_refused_and_nothing_is_written(client, home):
    async with client:
        low = await client.put("/api/v1/daemon/port", json={"port": 80})
        high = await client.put("/api/v1/daemon/port", json={"port": 70000})
    for r in (low, high):
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "PORT_OUT_OF_RANGE"
        assert r.json()["error"]["details"]["min"] == 1024
    assert _config(home) == {}


@pytest.mark.asyncio
async def test_the_port_the_daemon_answers_on_counts_as_free(client, home, monkeypatch):
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    own = holder.getsockname()[1]
    monkeypatch.setattr(daemon_routes, "_PORT", own)
    try:
        async with client:
            r = await client.put("/api/v1/daemon/port", json={"port": own})
        assert r.status_code == 200
        assert r.json() == {"port": own, "bound_port": own, "pending": False}
    finally:
        holder.close()


# --- storage ----------------------------------------------------------------


def _write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


# revise-web-ui-ia: daemon "the storage summary reports the four kinds" — the
# acceptance marker is added when the change is archived.
@pytest.mark.asyncio
async def test_the_storage_summary_reports_the_four_kinds(client, home):
    coffer = home / ".coffer"
    _write(coffer / "knowledge" / "a.md", 100)
    _write(coffer / "skills" / "s" / "SKILL.md", 50)
    _write(coffer / "chat-media" / "m1", 300)
    _write(coffer / "channel-media" / "m2", 200)
    _write(coffer / "coffer.db", 1000)
    _write(coffer / "coffer.db-wal", 24)
    _write(coffer / "memory" / "p1" / "MEMORY.md", 70)
    _write(coffer / "cache" / "agent" / "summaries.json", 30)
    async with client:
        r = await client.get("/api/v1/storage")
    assert r.status_code == 200
    body = r.json()
    # No sync tree: the vault is what it would carry, with no version count.
    assert body["vault"] == {"path": str(coffer), "bytes": 150, "versions": None}
    assert body["local_content"]["bytes"] == 500
    assert body["local_content"]["folder"] == str(coffer)
    assert sorted(body["local_content"]["locations"]) == [
        str(coffer / "channel-media"),
        str(coffer / "chat-media"),
    ]
    assert body["history"] == {"path": str(coffer / "coffer.db"), "bytes": 1024}
    assert body["cache"] == {"bytes": 100}


@pytest.mark.asyncio
async def test_a_synced_vault_reports_its_git_versions(client, home):
    tree = home / ".coffer" / "sync"
    tree.mkdir(parents=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q", str(tree)], check=True, env=env)
    for i in range(3):
        (tree / f"f{i}").write_text(str(i))
        subprocess.run(["git", "-C", str(tree), "add", "."], check=True, env=env)
        subprocess.run(["git", "-C", str(tree), "commit", "-qm", f"c{i}"], check=True, env=env)
    async with client:
        r = await client.get("/api/v1/storage")
    vault = r.json()["vault"]
    assert vault["path"] == str(tree)
    assert vault["versions"] == 3
    assert vault["bytes"] > 0


# revise-web-ui-ia: web-ui "clearing the cache is confirmed and rebuilt" (the
# backend half: only the memory tree and the transcript cache go) — the
# acceptance marker is added when the change is archived.
@pytest.mark.asyncio
async def test_clearing_the_cache_touches_nothing_else(client, home, audit):
    coffer = home / ".coffer"
    _write(coffer / "memory" / "p1" / "MEMORY.md", 70)
    _write(coffer / "memory" / "p1" / "notes" / "n.md", 30)
    _write(coffer / "memory" / ".source_state.json", 10)
    _write(coffer / "cache" / "agent" / "summaries.json", 40)
    _write(coffer / "knowledge" / "a.md", 5)
    _write(coffer / "chat-media" / "m1", 5)
    _write(coffer / "vault" / "memory-triggers" / "t.md", 5)
    _write(coffer / "coffer.db", 5)
    async with client:
        r = await client.post("/api/v1/storage/cache/clear")
    assert r.status_code == 200
    assert r.json() == {"cleared_bytes": 150}
    assert (coffer / "memory").is_dir() and list((coffer / "memory").iterdir()) == []
    assert list((coffer / "cache" / "agent").iterdir()) == []
    for kept in ("knowledge/a.md", "chat-media/m1", "vault/memory-triggers/t.md", "coffer.db"):
        assert (coffer / kept).exists(), kept
    assert audit.events == [("storage_cache_cleared", {"cleared_bytes": 150})]


@pytest.mark.asyncio
async def test_clearing_is_refused_while_a_memory_pass_runs(client, home):
    from coffer.application.upkeep_runs import UPKEEP_RUNS

    _write(home / ".coffer" / "memory" / "p1" / "MEMORY.md", 70)
    assert UPKEEP_RUNS.claim("memory", "p1")
    try:
        async with client:
            r = await client.post("/api/v1/storage/cache/clear")
    finally:
        UPKEEP_RUNS.release("memory", "p1")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "UPKEEP_ALREADY_RUNNING"
    assert (home / ".coffer" / "memory" / "p1" / "MEMORY.md").exists()
