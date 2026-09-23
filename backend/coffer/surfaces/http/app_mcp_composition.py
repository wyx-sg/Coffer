"""MCP-specific composition for the FastAPI app.

Extracted from ``app.py`` to keep that composition root under the
400-line guideline. Holds:

* :func:`wire_mcp_kind` — builds MCP repos, supervisors, discovery,
  per-session gateway factory and installs them on the FastAPI app +
  dependency module, returning them as :class:`McpWiring`. Supervisors get
  the concrete upstream factory
  (:func:`coffer.infrastructure.mcp.factory.build_upstream`) injected here
  (CODE-005).
* :func:`build_prunable_registry` — the retention registry for the
  audit log + MCP invocation tables.
* :func:`reaper_kwargs_from_env` — parses ``COFFER_MCP_SESSION_*``
  environment overrides for the SSE-session reaper (CODE-022).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.mcp.sync_state import McpPreferenceSyncState
from coffer.application.resource_service import ResourceService
from coffer.application.retention_registry import (
    PrunableRegistry,
    PrunableTable,
)
from coffer.application.retention_service import RetentionService
from coffer.infrastructure.channel.media_retention import default_media_sweep
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
    MCPServerHealthRepo,
)
from coffer.surfaces.http.mcp.dependencies import (
    McpSessionFactory,
    set_capability_discovery,
    set_health_repo,
    set_invocation_repo,
    set_mcp_session_factory,
    set_preferences_repo,
)
from coffer.surfaces.http.sync_contributions import SyncContributions

_log = logging.getLogger(__name__)


#: Registry key for the process-wide supervisor (step 4). A session id is a
#: UUID, so this cannot collide with one, and the lifecycle hooks walk the
#: registry rather than a list of sessions — they need every supervisor holding
#: a live upstream, not every session.
_PROCESS_SUPERVISOR_KEY = "__process__"


@dataclass(frozen=True)
class McpWiring:
    """What the MCP kind hands back to the lifespan.

    The supervisors are disposed at shutdown; the session factory builds the
    chat platform's long-lived gateway session; the invocation repo is the
    batched writer the lifespan starts and drains.
    """

    process_supervisor: SubprocessSupervisor
    session_supervisors: dict[str, SubprocessSupervisor]
    session_factory: McpSessionFactory
    invocation_repo: MCPInvocationRepo


def wire_mcp_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker[AsyncSession],
    credential_store: EncryptedCredentialStore,
    builtin_tools: BuiltinToolRegistry,
    sync: SyncContributions,
) -> McpWiring:
    """Build and wire all MCP-specific plumbing into the app."""
    # 1. Build the MCP-side repos
    prefs_repo = MCPCapabilityPreferenceRepo(sm)
    sync.state_providers.append(McpPreferenceSyncState(resource_svc, prefs_repo))
    inv_repo = MCPInvocationRepo(sm)
    health_repo = MCPServerHealthRepo(sm)

    # 2. Per-session supervisor registry (used for the lifecycle hooks + factory)
    session_supervisors: dict[str, SubprocessSupervisor] = {}

    # 3. Build the on_delete-aware Kind and register it
    mcp_kind = make_mcp_kind(session_supervisors)
    app.state.kinds["mcp_server"] = mcp_kind

    # 4. Build the process-wide supervisor + discovery for REST routes
    #    (management routes: capabilities listing + refresh, via
    #    CapabilityDiscovery's self-heal path — not per-session protocol
    #    routing).
    process_supervisor = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(credential_store),
        upstream_factory=build_upstream,
    )
    process_discovery = CapabilityDiscovery(
        resource_service=resource_svc,
        supervisor=process_supervisor,
        preferences=prefs_repo,
    )
    # Registered under a reserved key that no session id can collide with, so
    # the kind's lifecycle hooks can reach it.
    #
    # It was absent from this registry, and the consequence was a leak nothing
    # reported: this supervisor spawns real upstream subprocesses for the
    # capability-management routes, so deleting a server left one of its
    # connections live and unreachable — the hook walked every session's
    # supervisor and never this one. The gap was invisible while it only
    # affected deletion, because the row was gone and nobody looked again.
    # Making rename available to every kind gave the same gap a second, louder
    # way to bite (a renamed server would answer under its new name while an
    # orphaned subprocess held the old one), which is what turned it up.
    session_supervisors[_PROCESS_SUPERVISOR_KEY] = process_supervisor

    # 5. Build the per-session MCPGatewaySession factory
    def mcp_session_factory(session_id: str) -> MCPGatewaySession:
        supervisor = SubprocessSupervisor(
            resource_service=resource_svc,
            credential_resolver=CredentialResolver(credential_store),
            upstream_factory=build_upstream,
        )
        session_supervisors[session_id] = supervisor

        def _drop_supervisor() -> None:
            # CODE-035: remove this session's supervisor from the registry on
            # dispose so disposed supervisors don't accumulate and the
            # on_delete hook never walks dead ones. A plain function (not a
            # lambda) so the return type is None, matching on_dispose's type.
            session_supervisors.pop(session_id, None)

        discovery = CapabilityDiscovery(
            resource_service=resource_svc,
            supervisor=supervisor,
            preferences=prefs_repo,
        )
        return MCPGatewaySession(
            session_id=session_id,
            resource_service=resource_svc,
            supervisor=supervisor,
            discovery=discovery,
            preferences=prefs_repo,
            invocations=inv_repo,
            on_dispose=_drop_supervisor,
            builtin_tools=builtin_tools,
        )

    # 6. Set ALL the MCP dependency providers
    set_capability_discovery(process_discovery)
    set_preferences_repo(prefs_repo)
    set_invocation_repo(inv_repo)
    set_health_repo(health_repo)
    set_mcp_session_factory(mcp_session_factory)
    return McpWiring(
        process_supervisor=process_supervisor,
        session_supervisors=session_supervisors,
        session_factory=mcp_session_factory,
        invocation_repo=inv_repo,
    )


def build_prunable_registry() -> PrunableRegistry:
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
    registry.register(
        PrunableTable(
            name="mcp_invocations",
            timestamp_column="timestamp",
            default_retention_days=30,
            display_name="MCP Invocations",
            description="MCP tool/resource/prompt invocation log.",
        )
    )
    registry.register(
        PrunableTable(
            name="sync_runs",
            timestamp_column="finished_at",
            default_retention_days=90,
            display_name="Sync Rounds",
            description="History of converge rounds against the sync remote.",
        )
    )
    # Conversations follow a two-stage lifecycle: idle threads are auto-archived,
    # then archived threads are deleted a while later. Both windows are user-tunable
    # (or None to disable) via the same retention surface as the log tables.
    registry.register(
        PrunableTable(
            name="conversations_archive",
            timestamp_column="updated_at",
            default_retention_days=7,
            display_name="Auto-archive Idle Chats",
            description="Archive conversations with no new message for this many days.",
            action="archive",
            target_table="conversations",
            archive_set_column="archived_at",
        )
    )
    registry.register(
        PrunableTable(
            name="conversations",
            timestamp_column="archived_at",
            default_retention_days=30,
            display_name="Delete Archived Chats",
            description="Delete archived conversations this many days after archival "
            "(with their messages).",
        )
    )
    return registry


def build_retention_service(
    sm: async_sessionmaker[AsyncSession], *, audit: AuditService
) -> RetentionService:
    """Compose the ``RetentionService`` (registry + repo + audit) and bind the
    channel-media dir sweep (spec channels "Persist inbound attachments as
    references") at composition root, so the
    application layer never imports the infrastructure prune. The caller runs
    ``initialize_defaults`` and drives the worker cadence."""
    from coffer.infrastructure.persistence.repos import SqlAlchemyRetentionRepo
    from coffer.infrastructure.persistence.retention_repo import allowlist_from_registry

    registry = build_prunable_registry()
    # The SQL allowlist is derived from these very registrations, so the two
    # cannot drift apart by hand — a table registered here is sweepable, and
    # nothing else is.
    return RetentionService(
        registry=registry,
        repo=SqlAlchemyRetentionRepo(sm, allowlist=allowlist_from_registry(registry.all())),
        audit=audit,
        media_sweep=default_media_sweep,
    )


_REAPER_ENV_KNOBS: dict[str, str] = {
    "COFFER_MCP_SESSION_IDLE_S": "max_idle_seconds",
    "COFFER_MCP_SESSION_REAPER_INTERVAL_S": "interval_seconds",
}


def reaper_kwargs_from_env() -> dict[str, float]:
    """Read ``COFFER_MCP_SESSION_*`` env overrides for the SSE reaper.

    CODE-022: knobs come from env so deployments can tune them without
    code changes; unset env falls back to ``start_session_reaper``'s
    safe defaults. A value that does not parse as a number is logged with
    the raw text and falls back to the same default — an operator who
    mistyped a knob must be told, not silently ignored.
    """
    reaper_kwargs: dict[str, float] = {}
    for env_name, kwarg in _REAPER_ENV_KNOBS.items():
        raw = os.environ.get(env_name)
        if not raw:
            continue
        try:
            reaper_kwargs[kwarg] = float(raw)
        except ValueError:
            _log.warning(
                "%s=%r is not a number; using the reaper's default for %s",
                env_name,
                raw,
                kwarg,
            )
    return reaper_kwargs
