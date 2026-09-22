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


@pytest.fixture(autouse=True)
def _restore_home():
    """The _client helpers overwrite os.environ["HOME"] without a fixture;
    restore it so later test modules don't inherit a dead tmp HOME."""
    prior = os.environ.get("HOME")
    yield
    if prior is not None:
        os.environ["HOME"] = prior


async def _client(tmp_path: Path, *, port: int = 8000):
    monkeypatched_home = tmp_path / "home"
    monkeypatched_home.mkdir()
    os.environ["HOME"] = str(monkeypatched_home)

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))

    # Pre-write daemon.json so rotate-token has something to read
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
    """The /status endpoint must NOT require the token — the CLI and the shim
    probe it for readiness before any token has been read from daemon.json."""
    c, _ = await _client(tmp_path)
    async with c:
        r = await c.get("/api/v1/daemon/status", headers={})
        assert r.status_code == 200


@pytest.mark.acceptance(
    spec="daemon", scenario="rotating the daemon token invalidates the previous one"
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
# T1 — daemon-lifecycle audit events (spec resource-framework FR-006)
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
    # Create an actual coffer.db for the daemon-status probes
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


# --- residency: what starts the daemon, and what ends it (FR-028/FR-029) ---


@pytest.mark.asyncio
async def test_residency_reports_both_halves(tmp_path, monkeypatch):
    c, _ = await _client(tmp_path)
    async with c:
        r = await c.get("/api/v1/daemon/residency")
        assert r.status_code == 200
        body = r.json()
        # The default is the setting, not the absence of one.
        assert body["idle_shutdown_hours"] == 12
        assert "login_service_supported" in body
        assert "login_service_installed" in body


@pytest.mark.asyncio
async def test_residency_requires_the_token(tmp_path):
    c, _ = await _client(tmp_path)
    async with c:
        r = await c.get("/api/v1/daemon/residency", headers={"X-Coffer-Token": ""})
        assert r.status_code == 401


@pytest.mark.acceptance(spec="daemon", scenario="a daemon nothing has wanted stands down")
@pytest.mark.asyncio
async def test_setting_the_idle_window_persists_where_the_next_start_reads_it(
    tmp_path, monkeypatch
):
    """It has to land in daemon-config.json, not in the database: the window
    is read before the database is open, by the next daemon rather than this
    one."""
    from coffer.infrastructure.daemon import login_service

    monkeypatch.setattr(login_service, "is_supported", lambda: False)
    c, home = await _client(tmp_path)
    async with c:
        r = await c.put(
            "/api/v1/daemon/residency",
            json={"login_service_installed": False, "idle_shutdown_hours": 4},
        )
        assert r.status_code == 200
        assert r.json()["idle_shutdown_hours"] == 4

    config = json.loads((home / ".coffer" / "daemon-config.json").read_text())
    assert config["idle_shutdown_hours"] == 4


@pytest.mark.asyncio
async def test_never_standing_down_is_a_setting_not_an_absent_one(tmp_path, monkeypatch):
    from coffer.infrastructure.daemon import login_service

    monkeypatch.setattr(login_service, "is_supported", lambda: False)
    c, _ = await _client(tmp_path)
    async with c:
        r = await c.put(
            "/api/v1/daemon/residency",
            json={"login_service_installed": False, "idle_shutdown_hours": None},
        )
        assert r.status_code == 200
        assert r.json()["idle_shutdown_hours"] is None


@pytest.mark.asyncio
async def test_an_idle_window_too_short_to_mean_anything_is_refused(tmp_path, monkeypatch):
    from coffer.infrastructure.daemon import login_service

    monkeypatch.setattr(login_service, "is_supported", lambda: False)
    c, _ = await _client(tmp_path)
    async with c:
        r = await c.put(
            "/api/v1/daemon/residency",
            json={"login_service_installed": False, "idle_shutdown_hours": 0.01},
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_the_change_is_audited_with_what_became_true(tmp_path, monkeypatch):
    """Recorded from the outcome, not the request. A login service the host
    cannot install is a change that did not happen, and an audit line saying
    it did would be the one place a user goes to find out."""
    from coffer.infrastructure.daemon import login_service

    monkeypatch.setattr(login_service, "is_supported", lambda: False)

    recorded: list[tuple[str, dict]] = []

    class _Spy:
        async def record(self, event_type, *, actor, details=None, **kwargs):
            recorded.append((event_type, details or {}))

    c, _ = await _client(tmp_path)
    # Replace the injected audit service on the app the client is bound to.
    c._transport.app.dependency_overrides[get_audit_service] = lambda: _Spy()
    async with c:
        r = await c.put(
            "/api/v1/daemon/residency",
            json={"login_service_installed": True, "idle_shutdown_hours": 6},
        )
        assert r.status_code == 200
        # Asked for on a host that has no launchd — so it is off, and both the
        # response and the audit line say so.
        assert r.json()["login_service_installed"] is False

    assert recorded == [
        (
            "daemon_residency_updated",
            {"login_service_installed": False, "idle_shutdown_hours": 6},
        )
    ]


@pytest.mark.asyncio
async def test_a_login_service_failure_leaves_the_idle_window_alone(tmp_path, monkeypatch):
    """No half-applied change. The step that can fail runs first, so a 500
    means nothing was written — rather than a 500 over an idle window that
    quietly changed anyway."""
    from coffer.infrastructure.daemon import login_service

    monkeypatch.setattr(login_service, "is_supported", lambda: True)
    monkeypatch.setattr(
        login_service, "install", lambda: (_ for _ in ()).throw(OSError("no launchd for you"))
    )

    c, home = await _client(tmp_path)
    async with c:
        r = await c.put(
            "/api/v1/daemon/residency",
            json={"login_service_installed": True, "idle_shutdown_hours": 4},
        )
        assert r.status_code == 500

    config_path = home / ".coffer" / "daemon-config.json"
    written = json.loads(config_path.read_text()) if config_path.exists() else {}
    assert "idle_shutdown_hours" not in written


@pytest.mark.asyncio
async def test_the_idle_window_is_required_on_the_put(tmp_path, monkeypatch):
    """`null` already means "never stand down", so an omitted field cannot
    also mean "leave it alone" — the request is refused instead."""
    from coffer.infrastructure.daemon import login_service

    monkeypatch.setattr(login_service, "is_supported", lambda: False)
    c, _ = await _client(tmp_path)
    async with c:
        r = await c.put("/api/v1/daemon/residency", json={"login_service_installed": False})
        assert r.status_code == 422
