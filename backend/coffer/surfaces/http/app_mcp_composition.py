"""MCP-specific composition for the FastAPI app.

Extracted from ``app.py`` to keep that composition root under the
400-line guideline. Holds:

* :func:`wire_mcp_kind` — builds MCP repos, supervisors, discovery,
  per-session gateway factory and installs them on the FastAPI app +
  dependency module, returning them as :class:`McpWiring`. Supervisors get
  the concrete upstream factory
  (:func:`coffer.infrastructure.mcp.factory.build_upstream`) injected here.
* :func:`build_prunable_registry` — the retention registry for the
  audit log + MCP invocation tables.
* :func:`reaper_kwargs_from_env` — parses ``COFFER_MCP_SESSION_*``
  environment overrides for the SSE-session reaper.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.mcp.custom_tool_import import CustomToolImporter
from coffer.application.mcp.custom_tool_views import GroupViewer
from coffer.application.mcp.custom_tools import CustomToolService
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.mcp.server_requires import ServerRequirements
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.mcp.supervisor_failures import UpstreamFailureLedger
from coffer.application.mcp.upstream_auth import UpstreamAuthMonitor
from coffer.application.resource_service import ResourceService
from coffer.application.retention_registry import (
    PrunableRegistry,
    PrunableTable,
)
from coffer.application.retention_service import (
    RetentionService,
)
from coffer.domain.mcp.secret_target import mcp_destination
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Resource
from coffer.domain.secrets import SecretDestination
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.mcp.http_api_runner import HttpApiToolRunner
from coffer.infrastructure.mcp.openapi_fetch import OpenApiDocumentSource
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceStore,
    MCPInvocationRepo,
    MCPServerHealthRepo,
)
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.surfaces.http.cli_wiring import build_command_probe
from coffer.surfaces.http.mcp.custom_tool_dependencies import set_custom_tool_services
from coffer.surfaces.http.mcp.dependencies import (
    set_capability_discovery,
    set_health_repo,
    set_invocation_repo,
    set_mcp_session_factory,
    set_preferences_repo,
    set_server_requirements,
)
from coffer.surfaces.http.retention_wiring import build_file_policies
from coffer.surfaces.http.secret_boundary_wiring import (
    optional_secret_boundary,
    register_resource_destination,
)
from coffer.surfaces.http.secret_composition import boundary_resolver
from coffer.surfaces.http.usage_wiring import register_usage_retention
from coffer.surfaces.http.vault_composition import VaultStores

_log = logging.getLogger(__name__)


#: Registry key for the process-wide supervisor (step 4). The ``/mcp`` route
#: never takes a client-sent id that starts with ``__`` as a session id
#: (``protocol_routes.RESERVED_SESSION_PREFIX``), so this cannot collide with one,
#: and the lifecycle hooks walk the registry rather than a list of sessions —
#: they need every supervisor holding a live upstream, not every session.
_PROCESS_SUPERVISOR_KEY = "__process__"


@dataclass(frozen=True)
class McpWiring:
    """What the MCP kind hands back to the lifespan.

    The supervisors are disposed at shutdown; the invocation repo is the
    batched writer the lifespan starts and drains.
    """

    process_supervisor: SubprocessSupervisor
    session_supervisors: dict[str, SubprocessSupervisor]
    invocation_repo: MCPInvocationRepo
    #: Writes a rejected key from a real call into the server's health; the
    #: lifespan points its ``on_change`` at the attention watcher.
    auth_monitor: UpstreamAuthMonitor


def wire_mcp_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker[AsyncSession],
    vault: VaultStores,
    secret_store: EncryptedSecretStore,
    builtin_tools: BuiltinToolRegistry,
) -> McpWiring:
    """Build and wire all MCP-specific plumbing into the app."""
    # 1. Build the MCP-side stores: capability switches are a vault document
    # per server that goes with it, health and seen-times are derived, the
    # invocation log is history.
    names = vault.resources.name_of
    prefs_repo = MCPCapabilityPreferenceStore(vault.derived_sm, name_of=names)
    vault.resources.add_follower(prefs_repo.documents.follow)
    prefs_repo.documents.add_owner_listener(vault.resources.announce)
    inv_repo = MCPInvocationRepo(sm, name_of=names)
    health_repo = MCPServerHealthRepo(vault.derived_sm)
    auth_monitor = UpstreamAuthMonitor(health_repo)

    # 2. Per-session supervisor registry (used for the lifecycle hooks + factory)
    session_supervisors: dict[str, SubprocessSupervisor] = {}
    # One failure ledger for every supervisor: a dead upstream is backed off
    # once for the daemon, not once per client session.
    upstream_failures = UpstreamFailureLedger()

    # 3. Build the on_delete-aware Kind and register it
    mcp_kind = make_mcp_kind(session_supervisors)
    app.state.kinds["mcp_server"] = mcp_kind
    # Where each server's secrets go, for the secret boundary's adoption and
    # listing (spec secret "Hold a secret for a new destination until a
    # person approves it").
    register_resource_destination("mcp_server", _mcp_secret_destination)

    # 4. Build the process-wide supervisor + discovery for REST routes
    #    (management routes: capabilities listing + refresh, via
    #    CapabilityDiscovery's self-heal path — not per-session protocol
    #    routing).
    process_supervisor = SubprocessSupervisor(
        resource_service=resource_svc,
        secret_resolver=boundary_resolver(secret_store),
        upstream_factory=build_upstream,
        failures=upstream_failures,
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
            secret_resolver=boundary_resolver(secret_store),
            upstream_factory=build_upstream,
            failures=upstream_failures,
        )
        session_supervisors[session_id] = supervisor

        def _drop_supervisor() -> None:
            # Remove this session's supervisor from the registry on
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
            auth_monitor=auth_monitor,
        )

    # 6. Set ALL the MCP dependency providers
    set_capability_discovery(process_discovery)
    set_preferences_repo(prefs_repo)
    set_invocation_repo(inv_repo)
    set_health_repo(health_repo)
    set_mcp_session_factory(mcp_session_factory)
    set_server_requirements(
        ServerRequirements(
            probe=build_command_probe(), secrets=secret_store, boundary=optional_secret_boundary
        )
    )
    wire_custom_tools(resource_svc, audit, secret_store, inv_repo)
    return McpWiring(
        process_supervisor=process_supervisor,
        session_supervisors=session_supervisors,
        invocation_repo=inv_repo,
        auth_monitor=auth_monitor,
    )


def wire_custom_tools(
    resource_svc: ResourceService,
    audit: AuditService,
    secret_store: EncryptedSecretStore,
    inv_repo: MCPInvocationRepo,
) -> CustomToolService:
    """Custom-tool groups (design add-http-custom-tools §9): the service behind
    ``/api/v1/custom-tools`` and ``coffer tool``."""
    viewer = GroupViewer(
        outcomes=inv_repo,
        secrets=secret_store,
        boundary=optional_secret_boundary,
        clock=lambda: datetime.now(tz=UTC),
    )
    service = CustomToolService(
        resources=resource_svc,
        audit=audit,
        viewer=viewer,
        resolver=lambda: boundary_resolver(secret_store),
        runner=HttpApiToolRunner(),
    )
    set_custom_tool_services(service, CustomToolImporter(service, OpenApiDocumentSource()))
    return service


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
    register_usage_retention(registry)
    return registry


def build_retention_service(
    sm: async_sessionmaker[AsyncSession], *, audit: AuditService
) -> RetentionService:
    """Compose the ``RetentionService`` (registry + repo + audit) and bind the
    file policies (``attachments`` over ``channel-media``,
    ``skill_data`` over ``skill-data``) at
    composition root, so the
    application layer never imports the infrastructure prune. The caller runs
    ``initialize_defaults`` and drives the worker cadence."""
    from coffer.infrastructure.persistence.retention_repo import (
        FileRetentionRepo,
        allowlist_from_registry,
    )

    registry = build_prunable_registry()
    # The SQL allowlist is derived from these very registrations, so the two
    # cannot drift apart by hand — a table registered here is sweepable, and
    # nothing else is.
    return RetentionService(
        registry=registry,
        repo=FileRetentionRepo(sm, allowlist=allowlist_from_registry(registry.all())),
        audit=audit,
        file_policies=build_file_policies(),
    )


_REAPER_ENV_KNOBS: dict[str, str] = {
    "COFFER_MCP_SESSION_IDLE_S": "max_idle_seconds",
    "COFFER_MCP_SESSION_REAPER_INTERVAL_S": "interval_seconds",
}


def reaper_kwargs_from_env() -> dict[str, float]:
    """Read ``COFFER_MCP_SESSION_*`` env overrides for the SSE reaper.

    Knobs come from env so deployments can tune them without
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


def _mcp_secret_destination(resource: Resource) -> tuple[SecretDestination, dict[str, str]] | None:
    config = MCPServerConfig.model_validate(resource.config)
    refs = dict(config.transport.secret_refs)
    return (mcp_destination(resource.uid, resource.name, config), refs) if refs else None
