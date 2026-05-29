import os
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from coffer.surfaces.http.app import create_app, set_daemon_phase


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="daemon status reflects ready state")
@pytest.mark.asyncio
async def test_status_returns_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    db_path = tmp_path / "c.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    app = create_app()
    # Must drive the lifespan so the phase transitions to "ready"
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://t") as c,
    ):
        r = await c.get("/api/v1/daemon/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["version"] == "0.1.0"
    assert "started_at" in body
    assert "port" in body


@pytest.mark.asyncio
async def test_lifespan_records_daemon_started_and_stopped(tmp_path, monkeypatch):
    """The lifespan must emit daemon_started on startup and daemon_stopped on shutdown."""
    monkeypatch.setenv("HOME", str(tmp_path))
    db_path = tmp_path / "c.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    from coffer.application.audit_service import AuditService
    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )
    from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo

    # Drive the lifespan directly (ASGITransport does not drive lifespan).
    app = create_app()
    async with app.router.lifespan_context(app):
        pass  # lifespan startup + yield + shutdown

    # After lifespan exits the DB has the audit_log table (Alembic ran inside lifespan).
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    started = await audit.query(event_type="daemon_started")
    stopped = await audit.query(event_type="daemon_stopped")
    await engine.dispose()

    assert len(started) >= 1, "daemon_started audit entry missing"
    assert started[0].actor == "system"
    assert len(stopped) >= 1, "daemon_stopped audit entry missing"
    assert stopped[0].actor == "system"


# ---------------------------------------------------------------------------
# T3 — real status + upstream_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_reports_ready_after_startup(tmp_path, monkeypatch):
    """GET /daemon/status must report status=='ready' after lifespan completes."""
    monkeypatch.setenv("HOME", str(tmp_path))
    db_path = tmp_path / "c.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    app = create_app()
    from coffer.surfaces.http.auth import set_active_token

    set_active_token("tok")
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://t") as c,
    ):
        r = await c.get("/api/v1/daemon/status")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_status_includes_upstream_summary(tmp_path, monkeypatch):
    """GET /daemon/status upstream_summary counts must reflect persisted health state."""
    monkeypatch.setenv("HOME", str(tmp_path))
    db_path = tmp_path / "c.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    app = create_app()
    from coffer.surfaces.http.auth import set_active_token

    set_active_token("tok")
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://t") as c,
    ):
        # Register two mcp_servers via the resource API
        r1 = await c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "srv-healthy",
                "config": {
                    "transport": {
                        "type": "stdio",
                        "command": "echo",
                        "args": [],
                    }
                },
            },
            headers={"X-Coffer-Token": "tok"},
        )
        assert r1.status_code == 201, r1.text
        r2 = await c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "srv-failing",
                "config": {
                    "transport": {
                        "type": "stdio",
                        "command": "echo",
                        "args": [],
                    }
                },
            },
            headers={"X-Coffer-Token": "tok"},
        )
        assert r2.status_code == 201, r2.text

        # Write health rows directly through the health repo
        from coffer.surfaces.http import dependencies as _deps

        health_repo = _deps._health_repo
        assert health_repo is not None
        await health_repo.upsert("srv-healthy", "healthy", datetime.now(tz=UTC))
        await health_repo.upsert("srv-failing", "failing", datetime.now(tz=UTC))

        r = await c.get("/api/v1/daemon/status")
    assert r.status_code == 200
    body = r.json()
    assert "upstream_summary" in body, "upstream_summary missing from status response"
    summary = body["upstream_summary"]
    for key in ("registered", "enabled", "healthy", "unhealthy"):
        assert key in summary, f"upstream_summary missing field: {key}"
        assert isinstance(summary[key], int), f"upstream_summary.{key} must be int"

    assert summary["registered"] == 2, f"expected 2 registered, got {summary['registered']}"
    assert summary["enabled"] == 2, f"expected 2 enabled, got {summary['enabled']}"
    assert summary["healthy"] == 1, f"expected 1 healthy, got {summary['healthy']}"
    assert summary["unhealthy"] == 1, f"expected 1 unhealthy, got {summary['unhealthy']}"


# ---------------------------------------------------------------------------
# T5 — started_at matches daemon.json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_started_at_matches_daemon_json(tmp_path, monkeypatch):
    """GET /daemon/status started_at must match the started_at in daemon.json."""
    monkeypatch.setenv("HOME", str(tmp_path))
    db_path = tmp_path / "c.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    # Write a daemon.json with a known started_at in the past
    from coffer.infrastructure.daemon.pid_lock import DaemonInfo
    from coffer.infrastructure.daemon.pid_lock import write as write_daemon_json

    known_started_at = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
    daemon_json_path = tmp_path / ".coffer" / "daemon.json"
    daemon_json_path.parent.mkdir(parents=True, exist_ok=True)
    write_daemon_json(
        daemon_json_path,
        DaemonInfo(
            version=1,
            pid=os.getpid(),
            port=8765,
            token="test-tok",
            started_at=known_started_at,
            binary_path="/usr/bin/coffer",
        ),
    )

    app = create_app()
    from coffer.surfaces.http.auth import set_active_token

    set_active_token("test-tok")
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://t") as c,
    ):
        r = await c.get("/api/v1/daemon/status")

    assert r.status_code == 200
    body = r.json()
    returned_started_at = datetime.fromisoformat(body["started_at"])
    # Allow at most 1 second difference (timezone normalisation)
    assert abs((returned_started_at - known_started_at).total_seconds()) < 1, (
        f"started_at mismatch: got {returned_started_at}, expected {known_started_at}"
    )


# ---------------------------------------------------------------------------
# T3 — status reports "draining" during lifespan teardown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_reports_draining_during_teardown(tmp_path, monkeypatch):
    """GET /daemon/status must report status=='draining' once the lifespan
    teardown phase begins.

    Observing the mid-teardown state via a live HTTP request is not feasible
    with the test harness (the lifespan context manager blocks until teardown
    is complete). Instead, we drive the phase-setter directly — the same code
    path that _lifespan's finally-block calls — and confirm the status endpoint
    reads back 'draining'.  This validates the full status → get_daemon_phase()
    wire without sending SIGTERM to the test process.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    db_path = tmp_path / "c.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    app = create_app()
    from coffer.surfaces.http.auth import set_active_token

    set_active_token("tok")
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://t") as c,
    ):
        # Confirm we start in "ready"
        r_ready = await c.get("/api/v1/daemon/status")
        assert r_ready.status_code == 200
        assert r_ready.json()["status"] == "ready"

        # Simulate the lifespan finally-block setting the phase to "draining"
        set_daemon_phase("draining")
        try:
            r_drain = await c.get("/api/v1/daemon/status")
            assert r_drain.status_code == 200
            assert r_drain.json()["status"] == "draining", (
                f"Expected 'draining' after set_daemon_phase('draining'), got: {r_drain.json()}"
            )
        finally:
            # Restore so lifespan teardown (which also sets draining) is idempotent
            set_daemon_phase("ready")
