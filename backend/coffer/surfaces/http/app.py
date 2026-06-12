"""FastAPI composition root.

For the lifecycle-managed daemon process, `coffer.infrastructure.daemon.entry`
acquires the port + token before uvicorn binds. The lifespan here reads
daemon.json back to set the auth token + port, runs Alembic migrations,
wires services, and starts the retention worker.

In-process tests can call `create_app()` directly and override
`set_active_token(...)` manually if they want authenticated calls.

MCP-specific composition (upstream factory, session supervisors,
prunable registry, reaper env knobs) lives in
:mod:`coffer.surfaces.http.app_mcp_composition` to keep this file under
the 400-line guideline.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import pathlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI

from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService
from coffer.application.retention_worker import RetentionWorker
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import DatabaseSchemaTooNew
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.daemon.orphan_sweep import sweep_orphans
from coffer.infrastructure.daemon.pid_lock import read as read_daemon_json
from coffer.infrastructure.logging.setup import configure_logging
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
    SqlAlchemyRetentionRepo,
)
from coffer.surfaces.http import cors, daemon_routes
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.agent_config_routes import router as agent_config_router
from coffer.surfaces.http.agent_routes import router as agent_router
from coffer.surfaces.http.agent_skill_wiring import wire_agent_and_skill_kinds
from coffer.surfaces.http.app_mcp_composition import (
    build_prunable_registry,
    reaper_kwargs_from_env,
    wire_mcp_kind,
)
from coffer.surfaces.http.audit_routes import router as audit_router
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import (
    get_invocation_repo_optional,
    set_audit_service,
    set_resource_service,
    set_retention_service,
)
from coffer.surfaces.http.fs_routes import router as fs_router
from coffer.surfaces.http.keychain_routes import router as keychain_router
from coffer.surfaces.http.mcp.capability_routes import router as mcp_capability_router
from coffer.surfaces.http.mcp.invocation_routes import router as mcp_invocation_router
from coffer.surfaces.http.mcp.protocol_routes import router as mcp_protocol_router
from coffer.surfaces.http.mcp.protocol_routes import (
    shutdown_all_sessions,
    start_session_reaper,
)
from coffer.surfaces.http.resource_routes import router as resource_router
from coffer.surfaces.http.retention_routes import router as retention_router
from coffer.surfaces.http.skill_routes import router as skill_router


def _db_url() -> str:
    return os.environ.get(
        "COFFER_DB_URL",
        f"sqlite+aiosqlite:///{pathlib.Path.home()}/.coffer/coffer.db",
    )


def _daemon_json_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


def _alembic_config() -> AlembicConfig:
    cfg = AlembicConfig(
        str(
            pathlib.Path(__file__).resolve().parent.parent.parent
            / "infrastructure/persistence/migrations/alembic.ini"
        )
    )
    return cfg


def _guard_schema_not_newer(cfg: AlembicConfig) -> None:
    """Fail fast when the on-disk DB was migrated by a newer/divergent build.

    If the DB's current Alembic revision is not in this build's migration
    tree (e.g. the DB was created by a feature branch whose migrations this
    release doesn't ship), ``upgrade head`` raises an opaque "Can't locate
    revision identified by ..." and the daemon dies during lifespan startup
    with no actionable message. Detect that here and raise a clear error.

    A fresh DB (no ``alembic_version`` row) reports ``None`` and is fine.
    """
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine

    known = {rev.revision for rev in ScriptDirectory.from_config(cfg).walk_revisions()}
    sync_url = _db_url().replace("sqlite+aiosqlite://", "sqlite://")
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
    if current is not None and current not in known:
        raise DatabaseSchemaTooNew(current=current, db_path=_db_url())


def _run_migrations() -> None:
    """Run Alembic upgrade head synchronously. Caller is expected to be off
    the request path (lifespan startup)."""
    cfg = _alembic_config()
    _guard_schema_not_newer(cfg)
    command.upgrade(cfg, "head")


_logger = logging.getLogger(__name__)

# Daemon lifecycle phase — updated by the lifespan.
# Readable by daemon_routes.get_status to report real phase.
_DaemonPhase = Literal["starting", "ready", "draining"]
_DAEMON_PHASE: _DaemonPhase = "starting"


def get_daemon_phase() -> _DaemonPhase:
    return _DAEMON_PHASE


def set_daemon_phase(phase: _DaemonPhase) -> None:
    global _DAEMON_PHASE
    _DAEMON_PHASE = phase


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Run migrations BEFORE building services so they have a schema to talk to.
    await asyncio.get_running_loop().run_in_executor(None, _run_migrations)

    # Sweep orphans from a previous (potentially crashed) daemon run BEFORE
    # starting any new upstreams. Best-effort; failures don't block startup.
    try:
        killed = await asyncio.get_running_loop().run_in_executor(None, sweep_orphans)
        if killed:
            _logger.info("orphan_sweep.completed", extra={"killed": killed})
    except Exception:
        _logger.exception("orphan_sweep.failed")

    engine = create_async_engine_with_pragmas(_db_url())
    sm = session_maker(engine)

    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resource_svc = ResourceService(
        kinds=app.state.kinds,
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
        # Wired so register/update_config can probe credential_refs against
        # the keychain BEFORE persisting (spec edge case: missing credential
        # must fail registration with a named ref, no partial state).
        credentials=KeyringAdapter(),
    )
    registry = build_prunable_registry()
    retention_svc = RetentionService(
        registry=registry,
        repo=SqlAlchemyRetentionRepo(sm),
        audit=audit,
    )
    await retention_svc.initialize_defaults()

    set_resource_service(resource_svc)
    set_audit_service(audit)
    set_retention_service(retention_svc)

    # Wire up agent + skill kinds (specs 004-agent-registry, 005-skill-manager).
    # The helper builds both in lockstep so the cross-kind on_delete hook (agent
    # deletion cascades into skill binding cleanup) can reference both services,
    # and so app.py stays under the 400-line guideline. Agent detection stays
    # discovery + confirm (no auto-registration on startup).
    wire_agent_and_skill_kinds(app, resource_svc, audit, sm)

    # Wire up MCP-specific plumbing
    process_supervisor, session_supervisors = wire_mcp_kind(app, resource_svc, audit, sm)

    # CODE-020: start the batched invocation writer alongside the retention
    # worker. The repo's start() is a no-op if already started.
    _inv_repo = get_invocation_repo_optional()
    if _inv_repo is not None:
        await _inv_repo.start()

    # Read token + port + started_at if daemon.json exists (set by entry.py BEFORE uvicorn starts).
    json_path = _daemon_json_path()
    if json_path.exists():
        try:
            info = read_daemon_json(json_path)
            set_active_token(info.token)
            daemon_routes.set_port(info.port)
            daemon_routes.set_started_at(info.started_at)
        except (ValueError, KeyError, OSError):
            pass

    worker = RetentionWorker(retention_svc)
    worker_task = asyncio.create_task(worker.run())
    app.state.retention_worker = worker
    app.state.retention_worker_task = worker_task

    # Reap /mcp sessions that have been idle past the threshold. Without this
    # a downstream client that never closes its SSE stream would leak its
    # session + per-session supervisor + upstream subprocesses indefinitely.
    reaper_task = start_session_reaper(**reaper_kwargs_from_env())
    app.state.mcp_session_reaper_task = reaper_task

    # FR-014: record daemon lifecycle audit events; T3: set lifecycle phase
    set_daemon_phase("ready")
    with contextlib.suppress(Exception):
        await audit.record(AuditEventType.DAEMON_STARTED.value, actor="system")

    try:
        yield
    finally:
        set_daemon_phase("draining")
        with contextlib.suppress(Exception):
            await audit.record(AuditEventType.DAEMON_STOPPED.value, actor="system")
        worker.stop()
        # Best-effort shutdown
        try:
            await asyncio.wait_for(worker_task, timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            worker_task.cancel()
        reaper_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reaper_task
        # Drain the buffered invocation writer before tearing down sessions.
        _inv_repo = get_invocation_repo_optional()
        if _inv_repo is not None:
            with contextlib.suppress(Exception):
                await _inv_repo.stop()
        # Dispose MCP supervisors (best-effort)
        with contextlib.suppress(Exception):
            await process_supervisor.dispose()
        for sup in list(session_supervisors.values()):
            with contextlib.suppress(Exception):
                await sup.dispose()
        session_supervisors.clear()
        # Close per-/mcp/-session state in the protocol routes
        with contextlib.suppress(Exception):
            await shutdown_all_sessions()
        await engine.dispose()
        set_active_token(None)


def create_app(kinds: dict[str, Kind] | None = None) -> FastAPI:
    """Build the composition-rooted FastAPI app.

    `kinds`: dict of kind_name -> Kind. The MCP kind is always registered
    by the lifespan itself; callers may pass additional kinds for testing.
    """
    configure_logging()
    app = FastAPI(
        title="Coffer",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        lifespan=_lifespan,
    )
    app.state.kinds = kinds or {}
    # Register the agent Kind eagerly with no on_delete hook so tests that do
    # not run the lifespan still see it. The lifespan helper
    # `wire_agent_and_skill_kinds` overwrites this entry with a real cross-kind
    # hook (agent deletion cascades into skill binding cleanup).
    app.state.kinds.setdefault("agent", make_agent_kind(on_delete=None))
    cors.install(app)
    err_handlers.register(app)
    app.include_router(daemon_routes.router)
    app.include_router(resource_router)
    app.include_router(audit_router)
    app.include_router(retention_router)
    app.include_router(keychain_router)
    # Agent + skill kind routes (specs 004-agent-registry, 005-skill-manager)
    app.include_router(agent_router)
    app.include_router(agent_config_router)
    app.include_router(fs_router)
    app.include_router(skill_router)
    # MCP-specific routers
    app.include_router(mcp_protocol_router)
    app.include_router(mcp_capability_router)
    app.include_router(mcp_invocation_router)
    return app
