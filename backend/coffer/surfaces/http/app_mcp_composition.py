"""MCP-specific composition for the FastAPI app.

Extracted from ``app.py`` to keep that composition root under the
400-line guideline. Holds:

* :func:`wire_mcp_kind` — builds MCP repos, supervisors, discovery,
  per-session gateway factory and installs them on the FastAPI app +
  dependency module. Supervisors get the concrete upstream factory
  (:func:`coffer.infrastructure.mcp.factory.build_upstream`) injected here
  (CODE-005).
* :func:`build_prunable_registry` — the retention registry for the
  audit log + MCP invocation tables.
* :func:`reaper_kwargs_from_env` — parses ``COFFER_MCP_SESSION_*``
  environment overrides for the SSE-session reaper (CODE-022).
"""

from __future__ import annotations

import contextlib
import os
import platform
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.mcp.sync_state import McpPreferenceSyncState
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService
from coffer.application.sync.identity import MachineIdentityService
from coffer.infrastructure.channel.media_retention import default_media_sweep
from coffer.infrastructure.knowledge.ids import new_ulid
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
    MCPServerHealthRepo,
)
from coffer.infrastructure.persistence.retention import (
    PrunableRegistry,
    PrunableTable,
)
from coffer.infrastructure.sync.persistence import SqlAlchemyMachineIdentityRepo
from coffer.surfaces.http.dependencies import (
    set_capability_discovery,
    set_health_repo,
    set_invocation_repo,
    set_mcp_session_factory,
    set_preferences_repo,
    set_supervisor,
)


def wire_mcp_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: object,
    credential_store: Any,
    builtin_tools: BuiltinToolRegistry | None = None,
    embedder_provider: Callable[[], Awaitable[Any | None]] | None = None,
) -> tuple[SubprocessSupervisor, dict[str, SubprocessSupervisor]]:
    """Build and wire all MCP-specific plumbing into the app.

    Returns (process_supervisor, session_supervisors) so the caller can
    dispose them on shutdown.
    """
    # 1. Build the MCP-side repos
    prefs_repo = MCPCapabilityPreferenceRepo(sm)  # type: ignore[arg-type]
    providers = getattr(app.state, "sync_state_providers", None)
    if providers is None:
        providers = []
        app.state.sync_state_providers = providers
    providers.append(McpPreferenceSyncState(resource_svc, prefs_repo))
    inv_repo = MCPInvocationRepo(sm)  # type: ignore[arg-type]
    health_repo = MCPServerHealthRepo(sm)  # type: ignore[arg-type]

    # 2. Per-session supervisor registry (used for the on_delete hook + factory)
    session_supervisors: dict[str, SubprocessSupervisor] = {}

    # 3. Build the on_delete-aware Kind and register it
    mcp_kind = make_mcp_kind(session_supervisors)
    app.state.kinds["mcp_server"] = mcp_kind

    # ADR-045 machine axis (Task 8): this daemon's stable sync identity, built
    # exactly as channel_wiring.py does, so every supervisor and gateway
    # session in this process resolves the same machine id. A None provider
    # anywhere means "no filtering" (legacy behavior); here we always wire it
    # so a daemon never spawns an upstream server scoped to a different
    # machine, whether via a session's tool call or a management REST route.
    identity = MachineIdentityService(
        SqlAlchemyMachineIdentityRepo(sm),  # type: ignore[arg-type]
        audit,
        new_id=new_ulid,
        default_name=lambda: platform.node() or "coffer",
    )

    async def _local_machine_id() -> str:
        return (await identity.get()).machine_id

    # 4. Build the process-wide supervisor + discovery for REST routes
    #    (management routes: capabilities, refresh, test — not per-session protocol routing)
    process_supervisor = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(credential_store),
        upstream_factory=build_upstream,
        machine_id=_local_machine_id,
    )
    process_discovery = CapabilityDiscovery(
        resource_service=resource_svc,
        supervisor=process_supervisor,
        preferences=prefs_repo,
        audit=audit,
    )

    # 5. Build the per-session MCPGatewaySession factory
    def mcp_session_factory(session_id: str) -> MCPGatewaySession:
        supervisor = SubprocessSupervisor(
            resource_service=resource_svc,
            credential_resolver=CredentialResolver(credential_store),
            upstream_factory=build_upstream,
            machine_id=_local_machine_id,
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
            audit=audit,
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
            embedder_provider=embedder_provider,
            machine_id=_local_machine_id,
        )

    # 6. Set ALL the MCP dependency providers
    set_supervisor(process_supervisor)
    set_capability_discovery(process_discovery)
    set_preferences_repo(prefs_repo)
    set_invocation_repo(inv_repo)
    set_health_repo(health_repo)
    set_mcp_session_factory(mcp_session_factory)

    return process_supervisor, session_supervisors


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


def build_retention_service(sm: Any, *, audit: AuditService) -> RetentionService:
    """Compose the ``RetentionService`` (registry + repo + audit) and bind the
    channel-media dir sweep (FR-033) at composition root, so the application
    layer never imports the infrastructure prune. The caller runs
    ``initialize_defaults`` and drives the worker cadence."""
    from coffer.infrastructure.persistence.repos import SqlAlchemyRetentionRepo

    return RetentionService(
        registry=build_prunable_registry(),
        repo=SqlAlchemyRetentionRepo(sm),
        audit=audit,
        media_sweep=default_media_sweep,
    )


def reaper_kwargs_from_env() -> dict[str, float]:
    """Read ``COFFER_MCP_SESSION_*`` env overrides for the SSE reaper.

    CODE-022: knobs come from env so deployments can tune them without
    code changes; unset env falls back to ``start_session_reaper``'s
    safe defaults. Invalid values are silently ignored.
    """
    reaper_kwargs: dict[str, float] = {}
    if idle_env := os.environ.get("COFFER_MCP_SESSION_IDLE_S"):
        with contextlib.suppress(ValueError):
            reaper_kwargs["max_idle_seconds"] = float(idle_env)
    if interval_env := os.environ.get("COFFER_MCP_SESSION_REAPER_INTERVAL_S"):
        with contextlib.suppress(ValueError):
            reaper_kwargs["interval_seconds"] = float(interval_env)
    return reaper_kwargs
