"""Shared fixtures for CLI integration tests.

The ``in_proc_daemon`` fixture builds a full in-process FastAPI app,
monkeypatches ``_client.client_or_exit`` to return a ``starlette.testclient.TestClient``
(a sync ``httpx.Client`` subclass) wrapping the app via WSGI/ASGI bridge.
No threads, no ports, no races.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC
from datetime import datetime as dt

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.testclient import TestClient

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService
from coffer.domain.resource import Kind
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
    SqlAlchemyRetentionRepo,
)
from coffer.infrastructure.persistence.retention import PrunableRegistry, PrunableTable
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.audit_routes import router as audit_router
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.daemon_routes import router as daemon_router
from coffer.surfaces.http.dependencies import (
    get_audit_service,
    get_resource_service,
    get_retention_service,
)
from coffer.surfaces.http.resource_routes import router as resource_router
from coffer.surfaces.http.retention_routes import router as retention_router

# Re-export the MCP daemon fixture so both test_mcp_cmd.py and
# test_mcp_caps_cmd.py can request it by name (pytest resolves fixtures from
# conftest), avoiding a cross-module import that would shadow the param (F811).
from .test_mcp_cmd import mcp_daemon  # noqa: F401


class _FakeConfig(BaseModel):
    foo: int
    bar: str = "default"


_TOKEN = "test-token"
_PORT = 8000


def _build_app(tmp_path) -> tuple[FastAPI, object]:  # type: ignore[type-ignore]
    """Build a fully-wired FastAPI app with an in-memory SQLite DB."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"
    engine = create_async_engine_with_pragmas(db_url)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_create_tables(engine))

    sm = session_maker(engine)
    kinds = {"fake_kind": Kind(name="fake_kind", display_name="Fake", config_schema=_FakeConfig)}
    resource_repo = SqlAlchemyResourceRepo(sm)
    audit_repo = SqlAlchemyAuditRepo(sm)
    audit_svc = AuditService(audit_repo)
    resource_svc = ResourceService(kinds=kinds, repo=resource_repo, audit=audit_svc)

    registry = PrunableRegistry()
    registry.register(
        PrunableTable(
            name="audit_log",
            timestamp_column="timestamp",
            default_retention_days=365,
            display_name="Audit Log",
            description="Resource lifecycle events.",
        )
    )
    retention_repo = SqlAlchemyRetentionRepo(sm)
    retention_svc = RetentionService(registry=registry, repo=retention_repo, audit=audit_svc)
    loop.run_until_complete(retention_svc.initialize_defaults())
    loop.close()

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(daemon_router)
    app.include_router(resource_router)
    app.include_router(audit_router)
    app.include_router(retention_router)

    app.dependency_overrides[get_resource_service] = lambda: resource_svc
    app.dependency_overrides[get_audit_service] = lambda: audit_svc
    app.dependency_overrides[get_retention_service] = lambda: retention_svc

    set_active_token(_TOKEN)

    return app, engine


async def _create_tables(engine) -> None:  # type: ignore[type-ignore]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def in_proc_daemon(tmp_path, monkeypatch):
    """In-process daemon via Starlette TestClient; monkeypatches client_or_exit."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # Prevent daemon_routes from reading the real HOME coffer.db
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    # Also override os.environ so that daemon_routes._default_db_path() picks up tmp_path
    orig_environ_home = os.environ.get("HOME")
    os.environ["HOME"] = str(home)

    app, _engine = _build_app(tmp_path)

    # Write daemon.json so parts that read it still find one
    daemon_json_dir = home / ".coffer"
    daemon_json_dir.mkdir(parents=True, exist_ok=True)
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=_PORT,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    write(home / ".coffer" / "daemon.json", info)

    # Build a sync httpx.Client (TestClient) wrapping the app
    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN},
        raise_server_exceptions=False,
    )

    from coffer.surfaces.cli import _client as _cli_client

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, info))

    yield home

    # Cleanup
    set_active_token(None)
    if orig_environ_home is not None:
        os.environ["HOME"] = orig_environ_home
    elif "HOME" in os.environ:
        del os.environ["HOME"]
