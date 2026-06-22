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

from fastapi import FastAPI

from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.channel.kind import make_channel_kind
from coffer.application.embedding_config_service import EmbeddingConfigService
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService
from coffer.application.retention_worker import RetentionWorker
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Kind
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
    SqlAlchemyInternalEngineConfigRepo,
    SqlAlchemyResourceRepo,
    SqlAlchemyRetentionRepo,
)
from coffer.surfaces.http import cors, daemon_routes
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.agent_skill_wiring import wire_agent_and_skill_kinds
from coffer.surfaces.http.app_embedding_composition import build_embedding_resolvers
from coffer.surfaces.http.app_mcp_composition import (
    build_prunable_registry,
    reaper_kwargs_from_env,
    wire_mcp_kind,
)
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.auto_distill_wiring import (
    start_auto_distill,
    stop_auto_distill,
    wire_session_end_distiller,
)
from coffer.surfaces.http.backup_wiring import start_backup_worker, stop_backup_worker
from coffer.surfaces.http.channel_wiring import wire_channel_kind
from coffer.surfaces.http.credential_composition import (
    init_credential_store,
    make_credential_resolver,
    run_legacy_keychain_migration,
)
from coffer.surfaces.http.dependencies import (
    get_agent_service,
    get_invocation_repo_optional,
    get_master_key_manager,
    get_mcp_session_factory,
    get_provider_service,
    set_audit_service,
    set_embedding_config_service,
    set_internal_engine_config_service,
    set_resource_service,
    set_retention_service,
)
from coffer.surfaces.http.distill_wiring import wire_distill
from coffer.surfaces.http.mcp.protocol_routes import (
    shutdown_all_sessions,
    start_session_reaper,
)
from coffer.surfaces.http.memory.organize_state import get_organizer_service
from coffer.surfaces.http.migrations_runner import run_migrations
from coffer.surfaces.http.provider_wiring import wire_provider_kind
from coffer.surfaces.http.routing import include_all_routers
from coffer.surfaces.http.session_end_wiring import start_auto_organize, stop_auto_organize
from coffer.surfaces.http.sync_wiring import start_sync, stop_sync
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


def _daemon_json_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


_logger = logging.getLogger(__name__)


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

    db_path = pathlib.Path(_db_url().split("///", 1)[1]).expanduser()
    credential_store = await init_credential_store(engine, db_path)

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
        credentials=credential_store,
    )
    internal_engine_config_svc = InternalEngineConfigService(
        repo=SqlAlchemyInternalEngineConfigRepo(sm),
        audit=audit,
    )

    set_resource_service(resource_svc)
    set_audit_service(audit)
    set_retention_service(retention_svc)
    set_embedding_config_service(embedding_config_svc)
    set_internal_engine_config_service(internal_engine_config_svc)

    # Build the shared built-in tool registry; each kind contributes its tools.
    # Created before kind wiring so skill/KB/memory can all register into it.
    builtin_tools = BuiltinToolRegistry()

    # Agent + skill kinds (004/005), lockstep: on_delete cascade + skill tools → gateway.
    wire_agent_and_skill_kinds(app, resource_svc, audit, sm, builtin_tools, credential_store)

    # Provider switching (spec 011) — AFTER the agent kind: it projects the
    # active profile into each agent's native config (see provider_wiring).
    wire_provider_kind(app, resource_svc, audit, credential_store)

    # Wire up knowledge_base kind (spec 006). Registers the KB built-in tools
    # into `builtin_tools`. One substrate per process: KB + memory share the
    # DocumentRepo, retrieval facade and reindexer (per KnowledgeRetrieval).
    substrate = build_substrate(sm, credential_store)

    # Embedding is global: KB + memory resolve the current config at index/recall
    # time so a Settings change applies without a daemon restart. The tool-search
    # embedder (ADR-024) reuses the KB embedder, cached per config.
    _resolve_embedding, _tool_search_embedder = build_embedding_resolvers(
        embedding_config_svc, credential_store
    )

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

    # Wire up MCP-specific plumbing (after other kinds so the gateway picks
    # their built-in tools).
    process_supervisor, session_supervisors = wire_mcp_kind(
        app, resource_svc, audit, sm, credential_store, builtin_tools, _tool_search_embedder
    )

    # Wire the chat feature (spec 008). Must come AFTER all other wiring so the
    # coffer-builtin-agent gateway session sees the fully-populated
    # BuiltinToolRegistry (KB + memory + skill + MCP tools). The session factory
    # is the one wire_mcp_kind registered via set_mcp_session_factory.
    chat_gateway_session = wire_chat(
        audit, sm, get_mcp_session_factory(), credential_store, builtin_tools
    )
    # The chat session's supervisor stays in session_supervisors so on_delete evicts
    # its upstreams; shutdown disposes it first (on_dispose deregisters; idempotent).
    app.state.mcp_session_supervisors = session_supervisors

    # Wire transcript distillation + organizer (spec 007 FR-027..031, ADR-020).
    distill_service = wire_distill(
        memory_service=memory_service,
        agent_service=get_agent_service(),
        provider_svc=get_provider_service(),
        credential_resolver=make_credential_resolver(credential_store),
    )

    # Wire the channel kind (spec 009) AFTER wire_chat: the inbound processor
    # drives turns through the chat service handles wire_chat published.
    channel_runtime = wire_channel_kind(app, resource_svc, audit, sm, credential_store)

    # One-time move of legacy OS-keychain secrets into the encrypted store
    # (best-effort; see credential_composition for the mechanics).
    await run_legacy_keychain_migration(
        app.state.kinds, sm, credential_store, audit, embedding_config_svc
    )

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

    # Optional opt-in background workers (default OFF).
    start_backup_worker(app)
    # Auto session-end organize → 固化 pipeline (007 FR-035): default-ON.
    start_auto_organize(app, memory_service, get_organizer_service())
    # Auto-distill catch-up sweep (007 FR-046): default-ON memory write guarantee.
    start_auto_distill(
        app, distill_service=distill_service, agent_service=get_agent_service(), session_maker=sm
    )
    # On-demand SessionEnd distill (Slice 6 FR-051): reuses the FR-046 ledger so
    # a session distilled at session-end is never re-distilled by the sweep.
    wire_session_end_distiller(distill_service=distill_service, session_maker=sm)

    # Multi-machine sync (spec 010); worker is inert until the user enables it.
    start_sync(app, resource_svc, audit, sm, db_path, get_master_key_manager())

    # Channel adapter reconciler (spec 009). Started after the daemon token is
    # published so the callback listener can be spawned with valid loopback
    # credentials on its first tick.
    channel_runtime_task = asyncio.create_task(channel_runtime.run())
    app.state.channel_runtime = channel_runtime
    app.state.channel_runtime_task = channel_runtime_task

    # Reap /mcp sessions that have been idle past the threshold. Without this
    # a downstream client that never closes its SSE stream would leak its
    # session + per-session supervisor + upstream subprocesses indefinitely.
    reaper_task = start_session_reaper(**reaper_kwargs_from_env())
    app.state.mcp_session_reaper_task = reaper_task

    # FR-014: record daemon lifecycle audit events; T3: set lifecycle phase
    daemon_routes.set_daemon_phase("ready")
    with contextlib.suppress(Exception):
        await audit.record(AuditEventType.DAEMON_STARTED.value, actor="system")

    try:
        yield
    finally:
        daemon_routes.set_daemon_phase("draining")
        with contextlib.suppress(Exception):
            await audit.record(AuditEventType.DAEMON_STOPPED.value, actor="system")
        worker.stop()
        # Best-effort shutdown of the optional backup worker.
        await stop_backup_worker(app)
        await stop_auto_organize(app)
        await stop_auto_distill(app)
        await stop_sync(app)
        # Stop channel adapters first so no new turns start mid-teardown.
        # Order matters: cancel the reconciler task BEFORE dispose() so an
        # in-flight tick cannot resurrect adapters dispose() just stopped;
        # everything is suppressed so a dead reconciler (stored exception)
        # can never abort the rest of this teardown.
        channel_runtime.stop()
        channel_runtime_task.cancel()
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(channel_runtime_task, timeout=2.0)
        with contextlib.suppress(Exception):
            await channel_runtime.dispose()
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
    # Same eager registration for the channel kind (the lifespan's
    # wire_channel_kind overwrites it with the runtime-evicting on_delete).
    app.state.kinds.setdefault("channel", make_channel_kind())
    cors.install(app)
    err_handlers.register(app)
    include_all_routers(app)
    return app
