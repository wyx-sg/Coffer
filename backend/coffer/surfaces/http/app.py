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

Credential-store DI singletons and the master-key bootstrap live in
:mod:`coffer.surfaces.http.credential_composition` for the same reason.
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

from fastapi import FastAPI

from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.credential_migration import (
    gather_extra_credential_refs,
    migrate_legacy_keychain,
)
from coffer.application.embedding_config_service import EmbeddingConfigService
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService
from coffer.application.retention_worker import RetentionWorker
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Kind
from coffer.infrastructure.chat.model_persistence import ChatModelRepo
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
    SqlAlchemyEmbeddingConfigRepo,
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
from coffer.surfaces.http.chat.conversation_routes import router as chat_conversation_router
from coffer.surfaces.http.chat.model_routes import router as chat_model_router
from coffer.surfaces.http.chat.turn_routes import router as chat_turn_router
from coffer.surfaces.http.credential_composition import init_credential_store
from coffer.surfaces.http.credential_routes import router as credential_router
from coffer.surfaces.http.dependencies import (
    get_invocation_repo_optional,
    get_mcp_session_factory,
    set_audit_service,
    set_embedding_config_service,
    set_resource_service,
    set_retention_service,
)
from coffer.surfaces.http.embedding_routes import router as embedding_router
from coffer.surfaces.http.fs_routes import router as fs_router
from coffer.surfaces.http.knowledge_base import router as kb_router
from coffer.surfaces.http.mcp.capability_routes import router as mcp_capability_router
from coffer.surfaces.http.mcp.invocation_routes import router as mcp_invocation_router
from coffer.surfaces.http.mcp.protocol_routes import router as mcp_protocol_router
from coffer.surfaces.http.mcp.protocol_routes import (
    shutdown_all_sessions,
    start_session_reaper,
)
from coffer.surfaces.http.memory import router as memory_router
from coffer.surfaces.http.migrations_runner import run_migrations
from coffer.surfaces.http.projection_routes import agent_native_router
from coffer.surfaces.http.projection_routes import router as projection_router
from coffer.surfaces.http.projection_wiring import wire_projection
from coffer.surfaces.http.resource_routes import router as resource_router
from coffer.surfaces.http.retention_routes import router as retention_router
from coffer.surfaces.http.settings_routes import router as settings_router
from coffer.surfaces.http.skill_routes import router as skill_router
from coffer.surfaces.http.wiring import (
    build_substrate,
    wire_chat,
    wire_kb_kind,
    wire_memory_kind,
)


def _db_url() -> str:
    return os.environ.get(
        "COFFER_DB_URL",
        f"sqlite+aiosqlite:///{pathlib.Path.home()}/.coffer/coffer.db",
    )


def _db_path() -> pathlib.Path:
    """Filesystem path of the SQLite DB (master.key lives alongside it)."""
    return pathlib.Path(_db_url().split("///", 1)[1]).expanduser()


def _daemon_json_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


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
    await asyncio.get_running_loop().run_in_executor(None, run_migrations, _db_url())

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

    credential_store = await init_credential_store(engine, _db_path())

    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resource_svc = ResourceService(
        kinds=app.state.kinds,
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
        # Wired so register/update_config can probe credential_refs against
        # the encrypted store BEFORE persisting (spec edge case: missing
        # credential must fail registration with a named ref, no partial state).
        credentials=credential_store,
    )
    registry = build_prunable_registry()
    retention_svc = RetentionService(
        registry=registry,
        repo=SqlAlchemyRetentionRepo(sm),
        audit=audit,
    )
    await retention_svc.initialize_defaults()
    embedding_config_svc = EmbeddingConfigService(
        repo=SqlAlchemyEmbeddingConfigRepo(sm),
        audit=audit,
    )

    set_resource_service(resource_svc)
    set_audit_service(audit)
    set_retention_service(retention_svc)
    set_embedding_config_service(embedding_config_svc)

    # Build the shared built-in tool registry; each kind contributes its tools.
    # Created before kind wiring so skill/KB/memory can all register into it.
    builtin_tools = BuiltinToolRegistry()

    # Wire up agent + skill kinds (specs 004-agent-registry, 005-skill-manager).
    # The helper builds both in lockstep so the cross-kind on_delete hook (agent
    # deletion cascades into skill binding cleanup) can reference both services,
    # and so app.py stays under the 400-line guideline. Agent detection stays
    # discovery + confirm (no auto-registration on startup). Passing
    # builtin_tools registers the skill tools (list_skills / load_skill) so the
    # built-in chat agent can reach them through the gateway (spec 008).
    wire_agent_and_skill_kinds(app, resource_svc, audit, sm, builtin_tools)

    # Wire up knowledge_base kind (spec 006). Registers the KB built-in tools
    # into `builtin_tools` so the gateway can expose them.
    # One substrate per process: KB + memory share the DocumentRepo,
    # retrieval facade and reindexer (per KnowledgeRetrieval's contract).
    substrate = build_substrate(sm, credential_store)

    # Embedding is global: KB + memory resolve the current config at index/recall
    # time so a Settings change applies without a daemon restart.
    async def _resolve_embedding() -> object:
        return (await embedding_config_svc.get()).to_embedding_config()

    wire_kb_kind(
        app,
        resource_svc,
        audit,
        sm,
        builtin_tools,
        substrate=substrate,
        embedding_resolver=_resolve_embedding,  # type: ignore[arg-type]
    )
    # Wire up Memory plumbing (spec 007). Registers the memory built-in tools.
    memory_service = wire_memory_kind(
        app,
        resource_svc,
        audit,
        sm,
        builtin_tools,
        substrate=substrate,
        embedding_resolver=_resolve_embedding,  # type: ignore[arg-type]
    )

    # Wire the composition-root projection service (bridges memory + agent so
    # neither kind imports the other — Contract 5e). Re-renders established
    # projections whenever the memory store changes.
    wire_projection(app, sm, memory_service, audit=audit)

    # Wire up MCP-specific plumbing (after other kinds so the gateway picks
    # their built-in tools).
    process_supervisor, session_supervisors = wire_mcp_kind(
        app, resource_svc, audit, sm, credential_store, builtin_tools
    )

    # Wire the chat feature (spec 008). Must come AFTER all other wiring so the
    # coffer-builtin-agent gateway session sees the fully-populated
    # BuiltinToolRegistry (KB + memory + skill + MCP tools). The session factory
    # is the one wire_mcp_kind registered via set_mcp_session_factory.
    chat_gateway_session = wire_chat(audit, sm, get_mcp_session_factory(), credential_store)
    # The chat session's supervisor stays registered in session_supervisors so
    # the mcp_server on_delete hook evicts its upstream connections too; shutdown
    # disposes the chat session first (its on_dispose deregisters the entry), so
    # the supervisor loop never double-disposes it (dispose() is idempotent).
    app.state.mcp_session_supervisors = session_supervisors

    # One-time move of legacy OS-keychain secrets into the encrypted store
    # (no-op once migrated). Best-effort: failures must not block startup.
    try:
        # Non-resource owners (chat models + global embedding config) cite
        # refs too; gather inside this try so it can't block startup.
        extra_refs = await gather_extra_credential_refs(ChatModelRepo(sm), embedding_config_svc)
        moved = await migrate_legacy_keychain(
            app.state.kinds,
            SqlAlchemyResourceRepo(sm),
            KeyringAdapter(),
            credential_store,
            audit,
            extra_refs=extra_refs,
        )
        if moved:
            _logger.info("credential_migration.completed", extra={"moved": moved})
    except Exception:
        _logger.exception("credential_migration.failed")

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
        # Dispose the built-in agent's chat gateway session first (best-effort);
        # its on_dispose callback removes its entry from session_supervisors.
        with contextlib.suppress(Exception):
            await chat_gateway_session.dispose()
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
        # KB / Memory services hold no long-lived handles (the substrate is
        # session-maker-bound + lazy), so only the shared engine needs disposal.
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
    app.include_router(credential_router)
    app.include_router(settings_router)
    app.include_router(embedding_router)
    # Agent + skill kind routes (specs 004-agent-registry, 005-skill-manager)
    app.include_router(agent_router)
    app.include_router(agent_config_router)
    app.include_router(fs_router)
    app.include_router(skill_router)
    # KB router (spec 006-knowledge-base)
    app.include_router(kb_router)
    # MCP-specific routers
    app.include_router(mcp_protocol_router)
    app.include_router(mcp_capability_router)
    app.include_router(mcp_invocation_router)
    # Memory router (spec 007-memory)
    app.include_router(memory_router)
    # Memory projection router (spec 007-memory; bridges memory + agent)
    app.include_router(projection_router)
    app.include_router(agent_native_router)
    # Agent chat routers (spec 008)
    app.include_router(chat_conversation_router)
    app.include_router(chat_turn_router)
    app.include_router(chat_model_router)
    return app
