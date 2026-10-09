"""FastAPI composition root.

For the lifecycle-managed daemon process, `coffer.infrastructure.daemon.entry`
acquires the port + token before uvicorn binds. The lifespan here reads
daemon.json back to set the auth token + port, runs Alembic migrations,
builds the vault's stores, wires services, and starts the background workers.

Every wiring step below RETURNS what it built, and the next step takes it as
a parameter: the order the lifespan reads in is the dependency order, and a
step cannot run before what it needs exists. ``app.state`` carries only what
routes, wiring and tests read: ``kinds``, ``feature_service``,
``mcp_session_supervisors``, ``background_workers``.
In-process tests can call `create_app()` directly and override
`set_active_token(...)` for authenticated calls.

MCP-specific composition (upstream factory, session supervisors,
prunable registry, reaper env knobs) lives in
:mod:`coffer.surfaces.http.app_mcp_composition`; secret-store DI
singletons and the master-key bootstrap in
:mod:`coffer.surfaces.http.secret_composition` — both for the 400-line
guideline.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.binary_deploy import deploy_frozen_sidecars
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.channel.kind import make_channel_kind
from coffer.application.reconcile.hints import HintingResourceRepo
from coffer.application.resource_service import ResourceService
from coffer.application.runtime import loop_lag
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.domain.resource import Kind
from coffer.infrastructure.agent.legacy_cleanup import remove_transcript_sidecar
from coffer.infrastructure.daemon.orphan_sweep import startup_sweep
from coffer.infrastructure.logging.setup import configure_logging
from coffer.infrastructure.persistence.attention_ignore_repo import SqlAlchemyAttentionIgnoreRepo
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.migrations_runner import run_migrations, sqlite_file
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.platform import HostPlatform
from coffer.infrastructure.vault.home import runs_db_path
from coffer.infrastructure.vault.reach_store import switch_off_empty_scopes
from coffer.surfaces.http import daemon_routes, middleware, webui
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.agent_connection_wiring import wire_agent_connection
from coffer.surfaces.http.agent_facet_wiring import build_agent_catalog
from coffer.surfaces.http.app_mcp_composition import build_retention_service, reaper_kwargs_from_env
from coffer.surfaces.http.app_shutdown import Running, shutdown
from coffer.surfaces.http.attention_wiring import lifespan_attention_sources
from coffer.surfaces.http.background_workers import start_background_workers
from coffer.surfaces.http.channel_wiring import wire_channel_kind
from coffer.surfaces.http.chat_wiring import wire_chat
from coffer.surfaces.http.daemon_identity import publish_daemon_identity
from coffer.surfaces.http.dependencies import (
    set_audit_service,
    set_internal_engine_config_service,
    set_platform,
    set_resource_service,
    set_retention_service,
)
from coffer.surfaces.http.engine_config_composition import build_config_services
from coffer.surfaces.http.event_wiring import build_event_stream, start_attention_watch
from coffer.surfaces.http.feature_dependencies import build_feature_service, set_feature_service
from coffer.surfaces.http.guide_wiring import run_builtin_guide_refresh
from coffer.surfaces.http.kind_wiring import wire_resource_kinds
from coffer.surfaces.http.mcp.protocol_routes import start_session_reaper
from coffer.surfaces.http.memory_turn_wiring import memory_context_composer, memory_turn_retriever
from coffer.surfaces.http.memory_wiring import (
    follow_memory_switch,
    register_delivery_hook_target,
)
from coffer.surfaces.http.openapi_route import include_openapi_route
from coffer.surfaces.http.provider_health_wiring import wire_provider_health
from coffer.surfaces.http.reconcile_wiring import (
    build_reconciler,
    run_boot_pass,
    start_reconciler,
    wire_attention,
)
from coffer.surfaces.http.release_check_wiring import wire_release_check
from coffer.surfaces.http.routing import include_all_routers
from coffer.surfaces.http.secret_boundary_wiring import remember_destination_sources
from coffer.surfaces.http.secret_composition import init_secret_store
from coffer.surfaces.http.secret_index_wiring import wire_secret_index
from coffer.surfaces.http.session_conversation_wiring import wire_session_conversations
from coffer.surfaces.http.setup_lifespan import guarded
from coffer.surfaces.http.vault_composition import build_vault_stores
from coffer.surfaces.http.vault_wiring import start_vault_scanning
from coffer.surfaces.http.workspace_dependencies import get_native_session_service


def _db_url() -> str:
    """The history database (``runs.db``); ``COFFER_DB_URL`` names another."""
    return os.environ.get("COFFER_DB_URL", f"sqlite+aiosqlite:///{runs_db_path()}")


_logger = logging.getLogger(__name__)


async def _best_effort(step: str, awaitable: Awaitable[object]) -> None:
    """One teardown step that must not abort the steps after it.

    A failure is a WARNING with the traceback — never silent. Cancellation is
    DEBUG: every task here was cancelled by this very teardown, so seeing it
    acknowledge is the expected outcome, not a fault.
    """
    try:
        await awaitable
    except asyncio.CancelledError:
        _logger.debug("shutdown.%s.cancelled", step)
    except Exception:
        _logger.warning("shutdown.%s.failed", step, exc_info=True)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Run migrations BEFORE building services so they have a schema to talk to.
    await asyncio.get_running_loop().run_in_executor(None, run_migrations, _db_url())

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
    # The vault repository, the resource files, derived.db and the one
    # validator every vault write passes (ADR storage-is-five-classes-by-nature).
    vault = await build_vault_stores(app.state.kinds)

    secrets = await init_secret_store()
    secret_store = secrets.store

    # ``AuditService.record`` is handed the ``Resource`` the event is about, so
    # the uid it stores is read off it, never looked back up by label.
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    # The unified reconciler (ADR one-level-triggered-reconciler-compares-
    # parameters) and the event stream: built first, so every resource write
    # hints both, and so each kind below can register the targets it supplies.
    reconciler = build_reconciler(audit)
    events = build_event_stream(reconciler)
    # A change another writer makes to a resource file (a hand edit settled,
    # a sync checkout, a restore) is hinted exactly like an API write.
    vault.resources.set_change_sink(events.hint_sink)
    # Hand edits: the boot scan, then a watcher and periodic scans, each
    # settled commit audited (spec vault-storage "Keep the last valid version
    # when a hand edit is invalid").
    vault_scanning = await start_vault_scanning(audit)
    resource_svc = ResourceService(
        kinds=app.state.kinds,
        repo=HintingResourceRepo(vault.resources, events.hint_sink),
        audit=audit,
        # Probed before persisting (spec mcp-gateway "Manage MCP servers as resources").
        secrets=secret_store,
    )

    retention_svc = build_retention_service(sm, audit=audit)
    await retention_svc.initialize_defaults()
    internal_engine_config_svc = build_config_services(audit)

    set_resource_service(resource_svc)
    set_audit_service(audit)
    set_retention_service(retention_svc)
    set_internal_engine_config_service(internal_engine_config_svc)
    # The one adapter that knows the host OS (infrastructure/platform); every
    # application service that needs an OS answer is handed this instance.
    platform = HostPlatform()
    set_platform(platform)
    # The agent descriptors with their mechanism facets bound (ADR
    # agent-mechanisms-are-optional-facets-on-the-descriptor); every kind that
    # needs an agent-specific mechanism is handed this catalogue.
    agent_catalog = build_agent_catalog()

    # Build the shared built-in tool registry; each kind contributes its tools.
    # Created before kind wiring so skill + knowledge can register into it.
    # A tool owned by a switched-off experimental feature is neither listed
    # nor found (spec experimental-features).
    features = app.state.feature_service
    builtin_tools = BuiltinToolRegistry(feature_enabled=features.is_enabled)

    # Every resource kind, in dependency order (see kind_wiring).
    kinds = await wire_resource_kinds(
        app,
        resource_svc=resource_svc,
        audit=audit,
        sm=sm,
        vault=vault,
        builtin_tools=builtin_tools,
        secret_store=secret_store,
        platform=platform,
        agent_catalog=agent_catalog,
        reconciler=reconciler,
    )

    # Wire the chat feature (spec chat) after the kinds: the agent service is
    # the agent kind's result, and a channel turn's memory append closes over
    # the memory kind's service (spec memory "Deliver to channel turns through
    # the system prompt").
    chat = wire_chat(
        sm,
        secret_store,
        kinds.agent_skill.agent_service,
        resource_svc,
        agent_catalog,
        compose_memory_context=memory_context_composer(
            kinds.memory.turn_retrieval, features.is_enabled
        ),
        retrieve_memory=memory_turn_retriever(kinds.memory.turn_retrieval, features.is_enabled),
    )
    # Each connection's health, kept without anyone opening it (provider_health_wiring).
    wire_provider_health(vault.derived_sm, kinds, chat.introspection_service, events)
    # An agent's native sessions that a channel conversation points at are also
    # that conversation: the sessions service joins the turn platform here (the
    # two kinds meet only in a composition root).
    wire_session_conversations(
        get_native_session_service(),
        chat=chat.chat_service,
        orchestrator=chat.orchestrator,
        resources=resource_svc,
        agents=kinds.agent_skill.agent_service,
    )
    # Kept on app.state: an integration test asserts the registry's contents.
    app.state.mcp_session_supervisors = kinds.mcp.session_supervisors

    # The channel kind AFTER wire_chat: its turns run through the chat platform.
    channel_runtime = wire_channel_kind(
        app, resource_svc, audit, sm, vault, secret_store, chat, builtin_tools
    )

    # Every kind has registered its secret destinations; the approval refresh reads them.
    remember_destination_sources(resource_svc, audit)
    # What cites each secret, and the one-time move of old refs to minted ids.
    await wire_secret_index(resource_svc, events)

    # An agent's Coffer connection spans two kinds (the gateway entry is the
    # agent kind's, the memory hook the memory kind's), so it is composed here.
    connection = wire_agent_connection(
        kinds.agent_skill.agent_service,
        kinds.agent_skill.mcp_service,
        kinds.memory.delivery_service,
        features,
    )
    register_delivery_hook_target(
        reconciler, kinds.memory.delivery_service, features, connection.connected_agents
    )
    # The boot pass converges every target at once — MCP entries, skill links,
    # provider projections, delivery hooks — before the daemon reports ready.
    await run_boot_pass(reconciler)
    follow_memory_switch(reconciler, kinds.guide, features)
    # Coffer's own skill, re-rendered from this build and the corpus every boot
    # (cheap when nothing moved; heals an edited master; upgrades old renders).
    await run_builtin_guide_refresh(kinds.guide)

    # Start the batched invocation writer (its start() is a no-op if started).
    await kinds.mcp.invocation_repo.start()
    publish_daemon_identity()

    # Frozen builds only; no-op from source (spec daemon "Deploy frozen sibling
    # binaries and back up the history database before migrating", see binary_deploy).
    await asyncio.to_thread(deploy_frozen_sidecars)
    wire_release_check()
    # Leftover of the retired transcript summary cache (derived, safe to drop).
    await asyncio.to_thread(remove_transcript_sidecar)
    # ONE-TIME (require-an-agent-while-on): an empty agent list becomes off.
    await asyncio.to_thread(switch_off_empty_scopes)

    workers = start_background_workers(
        retention_svc=retention_svc,
        knowledge_service=kinds.knowledge.service,
        guide=kinds.guide,
        distil=kinds.memory.distil,
        memory_service=kinds.memory.service,
        resource_svc=resource_svc,
        audit=audit,
        engine_config=internal_engine_config_svc,
        sm=sm,
        secret_store=secret_store,
        master_key=secrets.master_key,
        features=features,
        platform=platform,
        history_db=sqlite_file(_db_url()),
    )
    # Published like ``app.state.kinds``: a test asserting the lifespan started
    # a worker needs a seam to reach it through.
    app.state.background_workers = workers

    # Channel adapter reconciler (spec channels): Telegram polling and the
    # SeaTalk websocket connections converge from its first tick.
    channel_runtime_task = spawn_restarting(channel_runtime.run, name="channel-runtime")
    # The event-loop lag probe behind /daemon/status's ``runtime`` block.
    spawn_restarting(loop_lag.probe().run, name="loop-lag-probe")
    # The reconciler's periodic loop; hints bring a pass forward.
    reconciler_task = start_reconciler(reconciler)
    # The Overview's "needs you" list: open drift, then each kind's signals.
    attention = wire_attention(
        reconciler,
        features.is_enabled,
        [
            *lifespan_attention_sources(
                resource_svc=resource_svc,
                secret_store=secret_store,
                connection_service=connection,
                sync_service=workers.sync.service,
            ),
            vault_scanning.attention,
        ],
        ignores=SqlAlchemyAttentionIgnoreRepo(sm),
        audit=audit,
    )
    attention_watch_task = await start_attention_watch(events, attention, kinds.mcp.auth_monitor)

    # Reap /mcp sessions that have been idle past the threshold. Without this
    # a downstream client that never closes its SSE stream would leak its
    # session + per-session supervisor + upstream subprocesses indefinitely.
    reaper_task = start_session_reaper(**reaper_kwargs_from_env())

    # Set the lifecycle phase
    daemon_routes.set_daemon_phase("ready")

    try:
        yield
    finally:
        await shutdown(
            Running(
                workers=workers,
                channel_runtime=channel_runtime,
                channel_runtime_task=channel_runtime_task,
                reaper_task=reaper_task,
                reconciler_task=reconciler_task,
                attention_watch_task=attention_watch_task,
                kinds=kinds,
                engine=engine,
            )
        )
        await _best_effort("vault_scanner", vault_scanning.stop())
        await _best_effort("derived_db", vault.derived_engine.dispose())


def create_app(kinds: dict[str, Kind] | None = None) -> FastAPI:
    """Build the composition-rooted FastAPI app.

    `kinds`: dict of kind_name -> Kind. The MCP kind is always registered
    by the lifespan itself; callers may pass additional kinds for testing.
    """
    configure_logging()
    app = FastAPI(
        title="Coffer",
        version="0.1.0",
        # FastAPI's schema route and its /docs and /redoc pages answer without
        # the token; the schema is served behind it instead (openapi_route).
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        # Opens the vault only once git is there; waits in the setup state
        # otherwise (spec daemon "Wait in a setup state when git is missing or too old").
        lifespan=guarded(_lifespan),
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
    # Built here, not in the lifespan: /daemon/status reports the features and
    # must answer before the lifespan has run (spec experimental-features).
    # The lifespan hands ``app.state.feature_service`` to what gates on it.
    app.state.feature_service = build_feature_service()
    set_feature_service(app.state.feature_service)
    # CORS, then the loopback host guard, then the trace id — the ordering and
    # why each position is load-bearing live in ``middleware``.
    middleware.install(app)
    err_handlers.register(app)
    include_all_routers(app)
    include_openapi_route(app)
    # LAST: the SPA mount claims "/", so every API route must already be
    # registered or it would swallow them.
    webui.install(app)
    return app
