"""FastAPI composition root.

For the lifecycle-managed daemon process, `coffer.infrastructure.daemon.entry`
acquires the port + token before uvicorn binds. The lifespan here reads
daemon.json back to set the auth token + port, runs Alembic migrations,
wires services, and starts the background workers.

Every wiring step below RETURNS what it built, and the next step takes it as
a parameter: the order the lifespan reads in is the dependency order, and a
step cannot run before what it needs exists. ``app.state`` carries only two
final results that routes and tests read (``kinds``, ``mcp_session_supervisors``).

In-process tests can call `create_app()` directly and override
`set_active_token(...)` manually if they want authenticated calls.

MCP-specific composition (upstream factory, session supervisors,
prunable registry, reaper env knobs) lives in
:mod:`coffer.surfaces.http.app_mcp_composition`; credential-store DI
singletons and the master-key bootstrap in
:mod:`coffer.surfaces.http.credential_composition` — both for the 400-line
guideline.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.binary_deploy import deploy_frozen_sidecars
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.channel.kind import make_channel_kind
from coffer.application.diagnostics import register_diagnostics_builtin_tools
from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Kind
from coffer.infrastructure.daemon.orphan_sweep import startup_sweep
from coffer.infrastructure.logging.files import log_dir
from coffer.infrastructure.logging.setup import configure_logging
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.surfaces.http import daemon_routes, middleware, webui
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.agent_skill_wiring import run_skill_drift_boot_heal
from coffer.surfaces.http.app_mcp_composition import (
    build_retention_service,
    reaper_kwargs_from_env,
)
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.background_workers import start_background_workers
from coffer.surfaces.http.channel_wiring import wire_channel_kind
from coffer.surfaces.http.chat_wiring import wire_chat
from coffer.surfaces.http.credential_composition import (
    init_credential_store,
    make_credential_resolver,
    run_legacy_keychain_migration,
)
from coffer.surfaces.http.curation_wiring import stop_curation_worker, wire_curation
from coffer.surfaces.http.daemon_identity import publish_daemon_identity
from coffer.surfaces.http.dependencies import (
    set_audit_service,
    set_internal_engine_config_service,
    set_resource_service,
    set_retention_service,
)
from coffer.surfaces.http.engine_config_composition import build_config_services
from coffer.surfaces.http.kind_wiring import wire_resource_kinds
from coffer.surfaces.http.mcp.protocol_routes import (
    shutdown_all_sessions,
    start_session_reaper,
)
from coffer.surfaces.http.memory_wiring import stop_aggregate_worker, stop_distil_worker
from coffer.surfaces.http.migrations_runner import run_migrations
from coffer.surfaces.http.provider_wiring import run_provider_projection_sweep
from coffer.surfaces.http.removed_agent_notice import report_removed_agent_leftovers
from coffer.surfaces.http.routing import include_all_routers
from coffer.surfaces.http.sync_contributions import SyncContributions
from coffer.surfaces.http.sync_wiring import stop_converge_worker
from coffer.surfaces.http.transcript_warm_wiring import stop_transcript_warm_worker


def _db_url() -> str:
    return os.environ.get(
        "COFFER_DB_URL",
        f"sqlite+aiosqlite:///{pathlib.Path.home()}/.coffer/coffer.db",
    )


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
    credentials = await init_credential_store(engine, db_path)
    credential_store = credentials.store
    # Computed once, up front, so every internal-LLM consumer below (knowledge
    # ingest, the curation pass, the memory distil pass, the sync conflict
    # resolver) shares one resolver rather than each re-wrapping the store.
    credential_resolver = make_credential_resolver(credential_store)

    audit_repo = SqlAlchemyAuditRepo(sm)
    resource_repo = SqlAlchemyResourceRepo(sm)

    # No resolver is injected any more. ``AuditService.record`` is handed the
    # ``Resource`` the event is about, and every caller performing a mutation
    # already has that row — so the id it stores is read off it rather than
    # looked back up from a label that may since have changed.
    audit = AuditService(audit_repo)
    resource_svc = ResourceService(
        kinds=app.state.kinds,
        repo=resource_repo,
        audit=audit,
        # Wired so register/update_config can probe credential_refs against
        # the encrypted store BEFORE persisting (spec edge case: missing
        # credential must fail registration with a named ref, no partial state).
        credentials=credential_store,
    )

    retention_svc = build_retention_service(sm, audit=audit)
    await retention_svc.initialize_defaults()
    # What each kind contributes to vault convergence (spec vault-sync),
    # collected as wiring proceeds and handed to ``start_sync`` at the end.
    sync_contributions = SyncContributions()
    # Also registers the engine-settings synced state area.
    internal_engine_config_svc = build_config_services(sm, audit, sync_contributions)

    set_resource_service(resource_svc)
    set_audit_service(audit)
    set_retention_service(retention_svc)
    set_internal_engine_config_service(internal_engine_config_svc)

    # Build the shared built-in tool registry; each kind contributes its tools.
    # Created before kind wiring so skill + knowledge can register into it.
    builtin_tools = BuiltinToolRegistry()

    # Coffer's own history, read by the agent debugging Coffer: the audit log
    # and the daemon log both lost their human reader, so the reader is the
    # agent and the way in is a tool it already holds.
    register_diagnostics_builtin_tools(
        builtin_tools,
        audit_repo=audit_repo,
        log_path=lambda: log_dir() / "daemon.log",
        # The tool's filter names a resource the way the agent asking knows it —
        # a kind and a name. Resolving it here is what lets the query key on the
        # resource's identity instead, so "what happened to X" answers with X's
        # whole history rather than the slice that happened to carry its current
        # label. Without this the tool refuses the filter rather than silently
        # answering a different question.
        find_resource=resource_svc.find_by_name,
    )

    # Every resource kind, in dependency order (see kind_wiring).
    kinds = await wire_resource_kinds(
        app,
        resource_svc=resource_svc,
        audit=audit,
        sm=sm,
        builtin_tools=builtin_tools,
        credential_store=credential_store,
        credential_resolver=credential_resolver,
        sync=sync_contributions,
    )

    # Wire the chat feature (spec channels). Must come AFTER all other wiring so the
    # coffer-builtin-agent gateway session sees the fully-populated
    # BuiltinToolRegistry (knowledge + skill + MCP tools); the session factory
    # and the agent service are the kinds' own results.
    chat = wire_chat(
        sm,
        kinds.mcp.session_factory,
        credential_store,
        kinds.agent_skill.agent_service,
        resource_svc,
    )
    # The chat session's supervisor stays in session_supervisors so on_delete evicts
    # its upstreams; shutdown disposes it first (on_dispose deregisters; idempotent).
    # Kept on app.state: an integration test asserts the registry's contents.
    app.state.mcp_session_supervisors = kinds.mcp.session_supervisors

    # Another internal-LLM knowledge consumer: the curation pass that derives
    # a collection's `topics/` lane from the sources people write. It carries
    # the skill delivery too, because a document nothing has re-rendered a
    # catalogue for is a document no agent has a path to (spec knowledge).
    curation_pass = wire_curation(
        kinds.knowledge.models, credential_resolver, kinds.knowledge.skill_delivery
    )

    # Wire the channel kind (spec channels) AFTER wire_chat: the inbound processor
    # drives turns through the chat platform's handles, and `/save` through the
    # knowledge kind's.
    channel_runtime = wire_channel_kind(
        app, resource_svc, audit, sm, credential_store, chat, kinds.knowledge, sync_contributions
    )

    # One-time move of legacy OS-keychain secrets into the encrypted store
    # (best-effort; see credential_composition for the mechanics).
    await run_legacy_keychain_migration(app.state.kinds, sm, credential_store, audit)

    # Boot heals — best-effort, never allowed to fail startup (see
    # provider_wiring / agent_skill_wiring for what each corrects).
    await run_provider_projection_sweep(kinds.provider.boot_heal)
    await run_skill_drift_boot_heal(kinds.agent_skill.boot_heal)
    # Each agent's knowledge skill, rendered from whatever the corpus holds
    # right now. Done every boot rather than only on change: it is cheap, it
    # heals a copy someone edited or deleted, and it is what replaces a
    # shared-master symlink on a vault upgraded from the previous delivery.
    await kinds.knowledge.skill_delivery.deliver_all()

    # CODE-020: start the batched invocation writer alongside the retention
    # worker. The repo's start() is a no-op if already started.
    await kinds.mcp.invocation_repo.start()

    publish_daemon_identity()

    # Frozen builds only; no-op from source (spec daemon FR-027, see binary_deploy).
    await asyncio.to_thread(deploy_frozen_sidecars)

    workers = start_background_workers(
        retention_svc=retention_svc,
        knowledge_service=kinds.knowledge.service,
        curation_pass=curation_pass,
        skill_delivery=kinds.knowledge.skill_delivery,
        distil=kinds.memory.distil,
        memory_service=kinds.memory.service,
        transcript_reader=kinds.agent_skill.transcript_reader,
        resource_svc=resource_svc,
        audit=audit,
        engine_config=internal_engine_config_svc,
        internal_connection=kinds.provider.internal_connection,
        credential_resolver=credential_resolver,
        db_path=db_path,
        sm=sm,
        credential_store=credential_store,
        master_key=credentials.master_key,
        sync_contributions=sync_contributions,
    )
    # Published for the same reason ``app.state.kinds`` is: a test that asserts
    # the lifespan actually started a worker needs a seam to reach it through,
    # and the alternative is asserting the wiring by reading the wiring.
    app.state.background_workers = workers
    # Same seam, for the same reason. An area that forgets to register its
    # state provider does not fail — it just silently stops converging, which
    # is how channel pairings went a whole release without syncing. A test that
    # can read the collected set is what makes that visible.
    app.state.sync_contributions = sync_contributions

    # Channel adapter reconciler (spec channels). Started after the daemon token is
    # published so the callback listener can be spawned with valid loopback
    # credentials on its first tick.
    channel_runtime_task = asyncio.create_task(channel_runtime.run())

    # Reap /mcp sessions that have been idle past the threshold. Without this
    # a downstream client that never closes its SSE stream would leak its
    # session + per-session supervisor + upstream subprocesses indefinitely.
    reaper_task = start_session_reaper(**reaper_kwargs_from_env())

    # T3: set lifecycle phase
    daemon_routes.set_daemon_phase("ready")

    try:
        yield
    finally:
        daemon_routes.set_daemon_phase("draining")
        workers.retention_worker.stop()
        await stop_converge_worker(workers.converge_worker)
        await stop_curation_worker(workers.curation_task)
        await stop_distil_worker(workers.distil_task)
        await stop_aggregate_worker(workers.aggregate_task)
        await stop_transcript_warm_worker(workers.warm_worker, workers.warm_task)
        # Stop channel adapters first so no new turns start mid-teardown.
        # Order matters: cancel the reconciler task BEFORE dispose() so an
        # in-flight tick cannot resurrect adapters dispose() just stopped;
        # every step is best-effort so a dead reconciler (stored exception)
        # can never abort the rest of this teardown.
        channel_runtime.stop()
        channel_runtime_task.cancel()
        await _best_effort("channel_runtime", asyncio.wait_for(channel_runtime_task, timeout=2.0))
        await _best_effort("channel_runtime.dispose", channel_runtime.dispose())
        # The retention worker was asked to stop above; give it a grace period
        # to finish an in-flight prune, then cancel it.
        try:
            await asyncio.wait_for(workers.retention_task, timeout=2.0)
        except TimeoutError:
            _logger.warning("shutdown.retention_worker.grace_expired; cancelling")
            workers.retention_task.cancel()
        except asyncio.CancelledError:
            _logger.debug("shutdown.retention_worker.cancelled")
            workers.retention_task.cancel()
        reaper_task.cancel()
        await _best_effort("mcp_session_reaper", reaper_task)
        # Drain the buffered invocation writer before tearing down sessions.
        await _best_effort("invocation_repo", kinds.mcp.invocation_repo.stop())
        # Dispose the built-in agent's chat gateway session first (best-effort);
        # its on_dispose callback removes its entry from session_supervisors.
        await _best_effort("chat_gateway_session", chat.gateway_session.dispose())
        # Dispose MCP supervisors (best-effort). The process-wide supervisor is
        # IN this registry now — it has to be, or the kind's delete and rename
        # hooks cannot reach the upstreams it holds — so the loop covers it and
        # the separate call it used to get would only dispose it twice.
        for session_id, sup in list(kinds.mcp.session_supervisors.items()):
            await _best_effort(f"session_supervisor[{session_id}]", sup.dispose())
        kinds.mcp.session_supervisors.clear()
        # Close per-/mcp/-session state in the protocol routes
        await _best_effort("mcp_sessions", shutdown_all_sessions())
        # The knowledge service holds no long-lived handles (the directory is
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
    # CORS, then the loopback host guard, then the trace id — the ordering and
    # why each position is load-bearing live in ``middleware``.
    middleware.install(app)
    err_handlers.register(app)
    include_all_routers(app)
    # LAST: the SPA mount claims "/", so every API route must already be
    # registered or it would swallow them.
    webui.install(app)
    return app
