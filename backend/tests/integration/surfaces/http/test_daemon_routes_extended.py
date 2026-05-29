import json
import os
import sqlite3
from datetime import UTC
from datetime import datetime as dt
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas, session_maker
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.daemon_routes import router as daemon_router
from coffer.surfaces.http.dependencies import get_audit_service


async def _client(tmp_path: Path, *, port: int = 8000):
    monkeypatched_home = tmp_path / "home"
    monkeypatched_home.mkdir()
    os.environ["HOME"] = str(monkeypatched_home)

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))

    # Pre-write daemon.json so backup/rotate-token have something to read
    write(
        monkeypatched_home / ".coffer" / "daemon.json",
        DaemonInfo(
            version=1,
            pid=os.getpid(),
            port=port,
            token="initial-token",
            started_at=dt.now(tz=UTC),
            binary_path="/test/binary",
        ),
    )
    set_active_token("initial-token")

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(daemon_router)
    app.dependency_overrides[get_audit_service] = lambda: audit
    transport = ASGITransport(app)
    client = AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "initial-token"},
    )
    return client, monkeypatched_home


@pytest.mark.asyncio
async def test_status_remains_unauthenticated(tmp_path):
    """The /status endpoint must NOT require the token (Tauri readiness probe)."""
    c, _ = await _client(tmp_path)
    async with c:
        r = await c.get("/api/v1/daemon/status", headers={})
        assert r.status_code == 200


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="rotating the daemon token invalidates the previous one"
)
@pytest.mark.asyncio
async def test_rotate_token_returns_new_token_and_updates_daemon_json(tmp_path):
    c, home = await _client(tmp_path)
    async with c:
        r = await c.post("/api/v1/daemon/rotate-token")
        assert r.status_code == 200
        new_token = r.json()["token"]
        assert new_token != "initial-token"
        assert len(new_token) >= 32
        # daemon.json updated
        info = json.loads((home / ".coffer" / "daemon.json").read_text())
        assert info["token"] == new_token

        # The previous token must be rejected (401) and the new one accepted.
        # rotate-token itself is the only authed daemon route mounted here;
        # POSTing with the old token must now be denied.
        r_old = await c.post(
            "/api/v1/daemon/rotate-token",
            headers={"X-Coffer-Token": "initial-token"},
        )
        assert r_old.status_code == 401, (
            f"previous token must be rejected after rotate; got {r_old.status_code}"
        )
        # The new token must succeed (rotating again returns 200).
        r_new = await c.post(
            "/api/v1/daemon/rotate-token",
            headers={"X-Coffer-Token": new_token},
        )
        assert r_new.status_code == 200, (
            f"new token must be accepted after rotate; got {r_new.status_code}"
        )
    set_active_token(None)


@pytest.mark.asyncio
async def test_rotate_token_requires_auth(tmp_path):
    c, _ = await _client(tmp_path)
    async with c:
        r = await c.post("/api/v1/daemon/rotate-token", headers={"X-Coffer-Token": "wrong"})
        assert r.status_code == 401
    set_active_token(None)


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="daemon backup produces a portable SQLite copy"
)
@pytest.mark.asyncio
async def test_backup_creates_file(tmp_path):
    c, home = await _client(tmp_path)
    # Create an actual coffer.db so backup can read it
    db_path = home / ".coffer" / "coffer.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (x INTEGER);")
    conn.execute("INSERT INTO t VALUES (1);")
    conn.commit()
    conn.close()

    async with c:
        r = await c.post("/api/v1/daemon/backup", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        backup_path = Path(body["path"])
        assert backup_path.exists()
        assert body["size_bytes"] > 0
        # Backup is a valid sqlite file with same content
        bconn = sqlite3.connect(backup_path)
        rows = bconn.execute("SELECT x FROM t;").fetchall()
        bconn.close()
        assert rows == [(1,)]
    set_active_token(None)


@pytest.mark.asyncio
async def test_backup_to_custom_path(tmp_path):
    c, home = await _client(tmp_path)
    # Create DB
    db_path = home / ".coffer" / "coffer.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3

    sqlite3.connect(db_path).close()

    custom = tmp_path / "custom" / "out.bak"
    custom.parent.mkdir(parents=True, exist_ok=True)

    async with c:
        r = await c.post("/api/v1/daemon/backup", json={"path": str(custom)})
        assert r.status_code == 200
        assert r.json()["path"] == str(custom)
        assert custom.exists()
    set_active_token(None)


@pytest.mark.asyncio
async def test_shutdown_returns_204(tmp_path):
    """Shutdown schedules graceful exit. We can't actually kill the test
    process — just verify the endpoint returns 204."""
    c, _ = await _client(tmp_path)
    async with c:
        # Mock os.kill to avoid actually terminating the test process
        import unittest.mock as mock

        with mock.patch("coffer.surfaces.http.daemon_routes._schedule_shutdown") as mocked:
            r = await c.post("/api/v1/daemon/shutdown")
            assert r.status_code == 204
            mocked.assert_called_once()
    set_active_token(None)


@pytest.mark.asyncio
async def test_shutdown_signals_termination(tmp_path):
    """_schedule_shutdown must send SIGTERM to the current process.

    We patch os.kill at the module level so we can assert it is called
    with the correct arguments (os.getpid(), signal.SIGTERM) without
    actually killing the test process.
    """
    import signal
    import unittest.mock as mock

    c, _ = await _client(tmp_path)
    async with c:
        with mock.patch("coffer.surfaces.http.daemon_routes.os.kill") as mock_kill:
            r = await c.post("/api/v1/daemon/shutdown")
            assert r.status_code == 204
            mock_kill.assert_called_once_with(os.getpid(), signal.SIGTERM)
    set_active_token(None)


# ---------------------------------------------------------------------------
# T1 — daemon-lifecycle audit events (FR-014)
# ---------------------------------------------------------------------------


async def _client_with_audit(tmp_path: Path, *, port: int = 8000):
    """Build a minimal app that includes the audit dependency override."""
    monkeypatched_home = tmp_path / "home"
    monkeypatched_home.mkdir()
    os.environ["HOME"] = str(monkeypatched_home)

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))

    # Pre-write daemon.json
    write(
        monkeypatched_home / ".coffer" / "daemon.json",
        DaemonInfo(
            version=1,
            pid=os.getpid(),
            port=port,
            token="initial-token",
            started_at=dt.now(tz=UTC),
            binary_path="/test/binary",
        ),
    )
    # Create an actual coffer.db so backup can read it
    db_path = monkeypatched_home / ".coffer" / "coffer.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn2 = sqlite3.connect(db_path)
    conn2.execute("CREATE TABLE t (x INTEGER);")
    conn2.execute("INSERT INTO t VALUES (1);")
    conn2.commit()
    conn2.close()

    set_active_token("initial-token")

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(daemon_router)
    app.dependency_overrides[get_audit_service] = lambda: audit

    transport = ASGITransport(app)
    client = AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-Coffer-Token": "initial-token"},
    )
    return client, audit, engine


@pytest.mark.asyncio
async def test_rotate_token_records_token_rotated_audit(tmp_path):
    """POST /daemon/rotate-token must record a token_rotated audit entry."""
    c, audit, engine = await _client_with_audit(tmp_path)
    try:
        async with c:
            r = await c.post("/api/v1/daemon/rotate-token")
            assert r.status_code == 200
        entries = await audit.query(event_type="token_rotated")
        assert len(entries) == 1
        assert entries[0].actor == "api"
    finally:
        await engine.dispose()
        set_active_token(None)


@pytest.mark.asyncio
async def test_backup_records_backup_created_audit(tmp_path):
    """POST /daemon/backup must record a backup_created audit entry with path."""
    c, audit, engine = await _client_with_audit(tmp_path)
    try:
        async with c:
            r = await c.post("/api/v1/daemon/backup", json={})
            assert r.status_code == 200, r.text
            backup_path = r.json()["path"]
        entries = await audit.query(event_type="backup_created")
        assert len(entries) == 1
        assert entries[0].actor == "api"
        assert entries[0].details.get("path") == backup_path
    finally:
        await engine.dispose()
        set_active_token(None)
