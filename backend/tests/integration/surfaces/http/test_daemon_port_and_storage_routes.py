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

from coffer.surfaces.http import daemon_port
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
    monkeypatch.delenv("COFFER_DB_URL", raising=False)
    return h


@pytest.fixture
def audit() -> _Audit:
    return _Audit()


@pytest.fixture
def client(home, audit, monkeypatch):
    monkeypatch.setattr(daemon_port, "_PORT", 8000)
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
    monkeypatch.setattr(daemon_port, "_PORT", 18300)
    async with client:
        r = await client.get("/api/v1/daemon/port")
    assert r.json() == {"port": 8000, "bound_port": 18300, "pending": False}


@pytest.mark.asyncio
async def test_the_port_routes_require_the_token(client):
    async with client:
        r = await client.get("/api/v1/daemon/port", headers={"X-Coffer-Token": ""})
    assert r.status_code == 401


@pytest.mark.acceptance(
    spec="daemon", scenario="a port set from the settings page is pending until restart"
)
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
    monkeypatch.setattr(daemon_port, "_PORT", own)
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


@pytest.mark.acceptance(spec="daemon", scenario="the storage summary reports the four kinds")
@pytest.mark.asyncio
async def test_the_storage_summary_reports_the_four_kinds(client, home):
    coffer = home / ".coffer"
    vault = coffer / "vault"
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q", str(vault)], check=True, env=env)
    _write(vault / "knowledge" / "a.md", 100)
    _write(vault / "skills" / "s" / "SKILL.md", 50)
    for i, path in enumerate(("knowledge/a.md", "skills/s/SKILL.md", "knowledge/a.md")):
        (vault / path).write_text("x" * (100 + i))
        subprocess.run(["git", "-C", str(vault), "add", "."], check=True, env=env)
        subprocess.run(["git", "-C", str(vault), "commit", "-qm", f"c{i}"], check=True, env=env)
    _write(coffer / "content" / "chat-media" / "m1", 300)
    _write(coffer / "content" / "channel-media" / "m2", 200)
    _write(coffer / "runs.db", 1000)
    _write(coffer / "runs.db-wal", 24)
    _write(coffer / "derived" / "memory" / "p1" / "MEMORY.md", 70)
    _write(coffer / "derived" / "cache" / "agent" / "summaries.json", 30)
    async with client:
        r = await client.get("/api/v1/storage")
    assert r.status_code == 200
    body = r.json()
    assert body["vault"]["path"] == str(vault)
    assert body["vault"]["versions"] == 3
    assert body["vault"]["bytes"] > 150
    # A commit with no Coffer trailers is a person's own: it reads as a disk edit.
    assert body["vault"]["latest_writer"] == "disk"
    assert body["vault"]["latest_time"] is not None
    assert body["vault"]["sync_configured"] is False
    assert body["local_content"]["bytes"] == 500
    assert body["local_content"]["folder"] == str(coffer / "content")
    assert sorted(body["local_content"]["locations"]) == [
        str(coffer / "content" / "channel-media"),
        str(coffer / "content" / "chat-media"),
    ]
    assert body["history"] == {"path": str(coffer / "runs.db"), "bytes": 1024}
    assert body["cache"] == {"bytes": 100}


@pytest.mark.acceptance(spec="daemon", scenario="the storage summary reports the four kinds")
@pytest.mark.asyncio
async def test_a_vault_not_yet_created_reports_no_versions(client, home):
    async with client:
        r = await client.get("/api/v1/storage")
    assert r.json()["vault"] == {
        "path": str(home / ".coffer" / "vault"),
        "bytes": 0,
        "versions": None,
        "latest_time": None,
        "latest_writer": None,
        "sync_configured": False,
    }


@pytest.mark.asyncio
async def test_the_vault_block_names_the_newest_writer_and_the_sync_remote(client, home):
    from coffer.domain.vault.writers import WRITER_USER, CommitMeta
    from coffer.domain.vault.writes import Expect
    from coffer.infrastructure.vault.instance import vault_writer

    meta = CommitMeta(writer=WRITER_USER, operation="edit", summary="Saved", actor="ui")
    vault_writer().write_file("knowledge/a.md", b"one\n", meta=meta, expected=Expect.ABSENT)
    remote = home / ".coffer" / "local" / "sync" / "remote.json"
    remote.parent.mkdir(parents=True)
    remote.write_text(json.dumps({"url": "https://example.invalid/vault.git"}))
    async with client:
        r = await client.get("/api/v1/storage")
    vault = r.json()["vault"]
    # The first commit (the daemon's) and the save.
    assert vault["versions"] == 2
    assert vault["latest_writer"] == "user"
    assert vault["sync_configured"] is True


# web-ui "clearing the cache is confirmed and rebuilt" has its backend half here
# (only the memory tree and the transcript cache go); DataSettings.test.tsx the page's.
@pytest.mark.acceptance(spec="web-ui", scenario="clearing the cache is confirmed and rebuilt")
@pytest.mark.acceptance(spec="daemon", scenario="clearing the cache leaves everything else")
@pytest.mark.asyncio
async def test_clearing_the_cache_touches_nothing_else(client, home, audit):
    coffer = home / ".coffer"
    memory = coffer / "derived" / "memory"
    _write(memory / "p1" / "MEMORY.md", 70)
    _write(memory / "p1" / "notes" / "n.md", 30)
    _write(memory / ".source_state.json", 10)
    _write(coffer / "derived" / "cache" / "agent" / "summaries.json", 40)
    _write(coffer / "vault" / "knowledge" / "a.md", 5)
    _write(coffer / "content" / "chat-media" / "m1", 5)
    _write(coffer / "vault" / "memory-triggers" / "t.md", 5)
    _write(coffer / "derived" / "sync-conflicts" / "a.md", 5)
    _write(coffer / "runs.db", 5)
    async with client:
        r = await client.post("/api/v1/storage/cache/clear")
    assert r.status_code == 200
    assert r.json() == {"cleared_bytes": 150}
    assert memory.is_dir() and list(memory.iterdir()) == []
    assert list((coffer / "derived" / "cache" / "agent").iterdir()) == []
    for kept in (
        "vault/knowledge/a.md",
        "content/chat-media/m1",
        "vault/memory-triggers/t.md",
        "derived/sync-conflicts/a.md",
        "runs.db",
    ):
        assert (coffer / kept).exists(), kept
    assert audit.events == [("storage_cache_cleared", {"cleared_bytes": 150})]


@pytest.mark.acceptance(spec="daemon", scenario="clearing the cache leaves everything else")
@pytest.mark.asyncio
async def test_clearing_is_refused_while_a_memory_pass_runs(client, home):
    from coffer.application.upkeep_runs import UPKEEP_RUNS

    _write(home / ".coffer" / "derived" / "memory" / "p1" / "MEMORY.md", 70)
    assert UPKEEP_RUNS.claim("memory", "p1")
    try:
        async with client:
            r = await client.post("/api/v1/storage/cache/clear")
    finally:
        UPKEEP_RUNS.release("memory", "p1")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "UPKEEP_ALREADY_RUNNING"
    assert (home / ".coffer" / "derived" / "memory" / "p1" / "MEMORY.md").exists()
