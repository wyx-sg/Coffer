"""FastAPI composition root.

For the lifecycle-managed daemon process, `coffer.infrastructure.daemon.entry`
acquires the port + token before uvicorn binds. The lifespan here reads
daemon.json back to set the auth token + port, runs Alembic migrations,
wires services, and starts the background workers.

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
from coffer.application.binary_deploy import deploy_frozen_sidecars
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.channel.kind import make_channel_kind
from coffer.application.diagnostics import register_diagnostics_builtin_tools
from coffer.application.resource_service import ResourceService
from coffer.application.retention_worker import RetentionWorker
from coffer.domain.resource import Kind
from coffer.infrastructure.daemon.orphan_sweep import startup_sweep
from coffer.infrastructure.daemon.pid_lock import read as read_daemon_json
from coffer.infrastructure.logging.files import log_dir, prune_log_dir
from coffer.infrastructure.logging.setup import configure_logging
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.surfaces.http import cors, daemon_routes, host_guard, webui
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.agent_skill_wiring import wire_agent_and_skill_kinds
from coffer.surfaces.http.app_embedding_composition import (
    build_config_services,
    build_embedding_resolvers,
)
from coffer.surfaces.http.app_mcp_composition import (
    build_retention_service,
    reaper_kwargs_from_env,
    wire_mcp_kind,
)
from coffer.surfaces.http.async_batch_wiring import start_async_batches, stop_async_batches
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.channel_wiring import wire_channel_kind
from coffer.surfaces.http.consolidate_wiring import run_lane_migration, run_store_consolidation
from coffer.surfaces.http.credential_composition import (
    init_credential_store,
    make_credential_resolver,
    run_legacy_keychain_migration,
)
from coffer.surfaces.http.dependencies import (
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
from coffer.surfaces.http.knowledge_wiring import (
    run_knowledge_reindex_sweep,
    wire_knowledge_kind,
)
from coffer.surfaces.http.mcp.protocol_routes import (
    shutdown_all_sessions,
    start_session_reaper,
)
from coffer.surfaces.http.migrations_runner import run_migrations
from coffer.surfaces.http.provider_wiring import (
    run_provider_projection_sweep,
    wire_provider_kind,
)
from coffer.surfaces.http.removed_agent_notice import report_removed_agent_leftovers
from coffer.surfaces.http.reorg_wiring import wire_reorg
from coffer.surfaces.http.routing import include_all_routers
from coffer.surfaces.http.sync_wiring import start_sync
from coffer.surfaces.http.tidy_wiring import start_tidy, stop_tidy
from coffer.surfaces.http.wiring import build_substrate, wire_chat


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

    # 0048 dropped the removed-type agent rows; name what they left on disk.
    try:  # Courtesy notice only: never fatal.
        report_removed_agent_leftovers()
    except Exception:
        _logger.exception("removed_agent_type.leftover_scan_failed")

    # Startup process hygiene (ADR daemon-detect-or-spawn), BEFORE new upstreams: reap leaked MCP
    # upstreams AND stale sibling daemons. Best-effort; never blocks startup.
    try:
        orphans, stale = await asyncio.get_running_loop().run_in_executor(None, startup_sweep)
        if orphans or stale:
            _logger.info("startup_sweep.completed", extra={"upstreams": orphans, "daemons": stale})
    except Exception:
        _logger.exception("startup_sweep.failed")

    engine = create_async_engine_with_pragmas(_db_url())
    sm = session_maker(engine)

    db_path = pathlib.Path(_db_url().split("///", 1)[1]).expanduser()
    credential_store = await init_credential_store(engine, db_path)

    audit_repo = SqlAlchemyAuditRepo(sm)
    audit = AuditService(audit_repo)
    resource_svc = ResourceService(
        kinds=app.state.kinds,
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
        # Wired so register/update_config can probe credential_refs against
        # the encrypted store BEFORE persisting (spec edge case: missing
        # credential must fail registration with a named ref, no partial state).
        credentials=credential_store,
    )
    retention_svc = build_retention_service(sm, audit=audit)
    await retention_svc.initialize_defaults()
    # Also registers the engine-settings synced state area (spec vault-export-import slice 7).
    embedding_config_svc, internal_engine_config_svc = build_config_services(
        app, sm, audit, credential_store
    )

    set_resource_service(resource_svc)
    set_audit_service(audit)
    set_retention_service(retention_svc)
    set_embedding_config_service(embedding_config_svc)
    set_internal_engine_config_service(internal_engine_config_svc)

    # Build the shared built-in tool registry; each kind contributes its tools.
    # Created before kind wiring so skill + knowledge can register into it.
    builtin_tools = BuiltinToolRegistry()

    # Coffer's own history, read by the agent debugging Coffer. The audit log
    # and the daemon log both lost their human reader — the audit page is gone
    # and nobody greps a log by hand — so the reader is the agent, and the way
    # in is a tool it already holds.
    register_diagnostics_builtin_tools(
        builtin_tools, audit_repo=audit_repo, log_path=lambda: log_dir() / "daemon.log"
    )

    # Agent + skill kinds (004/005), lockstep: on_delete cascade + skill tools → gateway.
    wire_agent_and_skill_kinds(app, resource_svc, audit, sm, builtin_tools, credential_store)

    # Provider switching (spec provider-switching) — AFTER the agent kind: it projects the
    # active profile into each agent's native config (see provider_wiring).
    wire_provider_kind(app, resource_svc, audit, credential_store, sm)

    # One substrate per process: the DocumentRepo, retrieval facade and
    # reindexer are shared by everything that indexes markdown.
    substrate = build_substrate(sm, credential_store)

    # Embedding is global: the knowledge kind resolves the current config at
    # index/recall time so a Settings change applies without a daemon restart.
    # The tool-search embedder (ADR builtin-agent-is-internal-capability)
    # reuses it, cached per config.
    _resolve_embedding, _tool_search_embedder = build_embedding_resolvers(
        embedding_config_svc, credential_store
    )

    # The one knowledge kind: notes + documents over three scopes. Registers
    # the six built-in knowledge tools into `builtin_tools`.
    knowledge_service = wire_knowledge_kind(
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

    # Wire the chat feature (spec channels). Must come AFTER all other wiring so the
    # coffer-builtin-agent gateway session sees the fully-populated
    # BuiltinToolRegistry (knowledge + skill + MCP tools). The session factory
    # is the one wire_mcp_kind registered via set_mcp_session_factory.
    chat_gateway_session = wire_chat(sm, get_mcp_session_factory(), credential_store)
    # The chat session's supervisor stays in session_supervisors so on_delete evicts
    # its upstreams; shutdown disposes it first (on_dispose deregisters; idempotent).
    app.state.mcp_session_supervisors = session_supervisors

    # The one internal-LLM knowledge consumer: the tidy pass over a scope's
    # notes. Built here so the composition root keeps a single internal-LLM
    # call site; `start_tidy` further down decides when it fires.
    _credential_resolver = make_credential_resolver(credential_store)
    wire_reorg(knowledge_service, get_provider_service(), _credential_resolver)

    # Wire the channel kind (spec channels) AFTER wire_chat: the inbound processor
    # drives turns through the chat service handles wire_chat published.
    channel_runtime = wire_channel_kind(app, resource_svc, audit, sm, credential_store)

    # One-time move of legacy OS-keychain secrets into the encrypted store
    # (best-effort; see credential_composition for the mechanics).
    await run_legacy_keychain_migration(
        app.state.kinds, sm, credential_store, audit, embedding_config_svc
    )

    # Boot projection heal: the agents' native config files are not Coffer's to
    # own, so re-derive the projection the registry implies (best-effort).
    await run_provider_projection_sweep(app)

    # Boot knowledge heals (best-effort, idempotent): bring the file tree to the
    # two-lane layout FIRST — everything below addresses a scope by the new
    # directory names — then collapse worktree-fragmented scopes, then reindex so
    # what was written is searchable (FR-043).
    await run_lane_migration()
    await run_store_consolidation(resources=resource_svc, sm=sm, substrate=substrate)
    await run_knowledge_reindex_sweep(app, resource_svc, _resolve_embedding)  # type: ignore[arg-type]

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

    # Frozen builds only; no-op from source (FR-026, see binary_deploy).
    await asyncio.to_thread(deploy_frozen_sidecars)

    worker = RetentionWorker(retention_svc, prune_logs=prune_log_dir)
    worker_task = asyncio.create_task(worker.run())
    app.state.retention_worker = worker
    app.state.retention_worker_task = worker_task

    # The notes tidy pass: on idle after a write, and on a periodic sweep.
    start_tidy(app, knowledge_service)
    await start_async_batches(  # document re-embed — off the request path
        app,
        knowledge_service=knowledge_service,
    )

    # Vault export/import (spec vault-export-import). Nothing runs in the background: the
    # service only acts when the user exports or imports a bundle.
    start_sync(app, resource_svc, audit, db_path, get_master_key_manager())

    # Channel adapter reconciler (spec channels). Started after the daemon token is
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

    # T3: set lifecycle phase
    daemon_routes.set_daemon_phase("ready")

    try:
        yield
    finally:
        daemon_routes.set_daemon_phase("draining")
        worker.stop()
        await stop_tidy(app)
        await stop_async_batches(app)
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
        # The knowledge service holds no long-lived handles (the substrate is
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
    # AFTER cors so it wraps it: Starlette runs the last-added middleware
    # outermost, and a request for an authority this daemon does not answer for
    # should be refused before anything else looks at it.
    host_guard.install(app)
    err_handlers.register(app)
    include_all_routers(app)
    # LAST: the SPA mount claims "/", so every API route must already be
    # registered or it would swallow them.
    webui.install(app)
    return app
