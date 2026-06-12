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
from typing import Any

from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.mcp.credential_resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
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
) -> tuple[SubprocessSupervisor, dict[str, SubprocessSupervisor]]:
    """Build and wire all MCP-specific plumbing into the app.

    Returns (process_supervisor, session_supervisors) so the caller can
    dispose them on shutdown.
    """
    # 1. Build the MCP-side repos
    prefs_repo = MCPCapabilityPreferenceRepo(sm)  # type: ignore[arg-type]
    inv_repo = MCPInvocationRepo(sm)  # type: ignore[arg-type]
    health_repo = MCPServerHealthRepo(sm)  # type: ignore[arg-type]

    # 2. Per-session supervisor registry (used for the on_delete hook + factory)
    session_supervisors: dict[str, SubprocessSupervisor] = {}

    # 3. Build the on_delete-aware Kind and register it
    mcp_kind = make_mcp_kind(session_supervisors)
    app.state.kinds["mcp_server"] = mcp_kind

    # 4. Build the process-wide supervisor + discovery for REST routes
    #    (management routes: capabilities, refresh, test — not per-session protocol routing)
    process_supervisor = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(credential_store),
        upstream_factory=build_upstream,
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
    registry.register(
        PrunableTable(
            name="conversations",
            timestamp_column="updated_at",
            # None = keep forever until the user sets a retention window; chat
            # threads are user content, so retention is opt-in, never a surprise.
            default_retention_days=None,
            display_name="Chat Conversations",
            description="Chat threads and their messages, pruned by last activity.",
        )
    )
    return registry


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
