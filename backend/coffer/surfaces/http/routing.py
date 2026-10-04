"""Router registration table for the FastAPI app.

Extracted from ``app.py`` so the composition root stays within the 400-line
guideline: every sub-router import + ``include_router`` call lives here, grouped
by spec, and ``app.py`` calls :func:`include_all_routers` once.

A router whose paths sit under an experimental feature's route prefixes (the
registry in ``coffer.domain.features``) is included behind that feature's gate
(``require_feature``), so every route under it answers 404 ``FEATURE_DISABLED``
while the feature is off, and serves again the moment it is switched on (spec
experimental-features "Close every surface of a switched-off feature"). The
gate is chosen from the router's own prefix at include time rather than
written beside it, so a new router under a feature's prefix is gated without
being told; ``test_every_route_under_a_features_prefixes_is_gated`` holds the
registry's prefixes against every route the app serves.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI

from coffer.domain.features import feature_for_path
from coffer.surfaces.http import daemon_routes
from coffer.surfaces.http.agent_config_routes import router as agent_config_router
from coffer.surfaces.http.agent_connection_routes import router as agent_connection_router
from coffer.surfaces.http.agent_hooks_routes import router as agent_hooks_router
from coffer.surfaces.http.agent_mcp_import_routes import router as agent_mcp_import_router
from coffer.surfaces.http.agent_native_memory_routes import (
    router as agent_native_memory_router,
)
from coffer.surfaces.http.agent_plugin_part_routes import router as agent_plugin_part_router
from coffer.surfaces.http.agent_routes import router as agent_router
from coffer.surfaces.http.agent_session_routes import router as agent_session_router
from coffer.surfaces.http.agent_unmanaged_skill_routes import (
    router as agent_unmanaged_skill_router,
)
from coffer.surfaces.http.agent_workspace_routes import router as agent_workspace_router
from coffer.surfaces.http.audit_routes import router as audit_router
from coffer.surfaces.http.channel_routes import router as channel_router
from coffer.surfaces.http.chat.agent_provider_routes import router as agent_provider_router
from coffer.surfaces.http.chat.conversation_routes import router as chat_conversation_router
from coffer.surfaces.http.chat.turn_routes import router as chat_turn_router
from coffer.surfaces.http.cli_routes import router as cli_router
from coffer.surfaces.http.daemon_port_routes import router as daemon_port_router
from coffer.surfaces.http.daemon_restart_routes import router as daemon_restart_router
from coffer.surfaces.http.daemon_upgrade_routes import router as daemon_upgrade_router
from coffer.surfaces.http.event_routes import router as event_router
from coffer.surfaces.http.feature_dependencies import require_feature
from coffer.surfaces.http.feature_routes import router as feature_router
from coffer.surfaces.http.fs_routes import router as fs_router
from coffer.surfaces.http.internal_engine_routes import router as internal_engine_router
from coffer.surfaces.http.knowledge import history_router as knowledge_history_router
from coffer.surfaces.http.knowledge import router as knowledge_router
from coffer.surfaces.http.mcp.builtin_routes import router as mcp_builtin_router
from coffer.surfaces.http.mcp.capability_routes import router as mcp_capability_router
from coffer.surfaces.http.mcp.config_test_routes import router as mcp_config_test_router
from coffer.surfaces.http.mcp.custom_tool_routes import router as custom_tool_router
from coffer.surfaces.http.mcp.invocation_routes import (
    aggregate_router as mcp_invocation_aggregate_router,
)
from coffer.surfaces.http.mcp.invocation_routes import router as mcp_invocation_router
from coffer.surfaces.http.mcp.page_routes import router as mcp_page_router
from coffer.surfaces.http.mcp.protocol_routes import router as mcp_protocol_router
from coffer.surfaces.http.mcp.server_test_routes import router as mcp_server_test_router
from coffer.surfaces.http.memory import routers as memory_routers
from coffer.surfaces.http.model_routes import router as model_router
from coffer.surfaces.http.price_list_routes import router as price_list_router
from coffer.surfaces.http.provider_model_switch_routes import router as model_switch_router
from coffer.surfaces.http.provider_routes import router as provider_router
from coffer.surfaces.http.proxy_routes import router as proxy_router
from coffer.surfaces.http.reconcile_routes import attention_router
from coffer.surfaces.http.reconcile_routes import router as reconcile_router
from coffer.surfaces.http.resource_routes import router as resource_router
from coffer.surfaces.http.retention_routes import router as retention_router
from coffer.surfaces.http.secret_boundary_routes import router as secret_boundary_router
from coffer.surfaces.http.secret_routes import router as secret_router
from coffer.surfaces.http.settings_routes import router as settings_router
from coffer.surfaces.http.setup_state import router as setup_router
from coffer.surfaces.http.skill_copy_routes import router as skill_copy_router
from coffer.surfaces.http.skill_delete_routes import router as skill_delete_router
from coffer.surfaces.http.skill_file_routes import router as skill_file_router
from coffer.surfaces.http.skill_routes import router as skill_router
from coffer.surfaces.http.skill_source_routes import router as skill_source_router
from coffer.surfaces.http.storage_routes import router as storage_router
from coffer.surfaces.http.sync_routes import router as sync_router
from coffer.surfaces.http.upkeep_routes import router as upkeep_router
from coffer.surfaces.http.usage_routes import router as usage_router
from coffer.surfaces.http.vault_routes import router as vault_router


def include_all_routers(app: FastAPI) -> None:
    """Mount every sub-router, grouped by spec (kind-agnostic core first)."""
    routers: tuple[APIRouter, ...] = (
        daemon_routes.router,
        daemon_port_router,  # spec daemon (the port of the next start)
        daemon_restart_router,  # spec daemon (restart itself on request)
        setup_router,  # spec daemon (wait in a setup state for git)
        daemon_upgrade_router,  # spec daemon (the upgrade hand-off)
        storage_router,  # spec daemon (Settings > Data: what Coffer stores)
        feature_router,  # spec experimental-features
        resource_router,
        audit_router,
        retention_router,
        upkeep_router,  # what this daemon is rewriting right now (cross-kind)
        reconcile_router,  # the unified reconciler's plan + apply (cross-kind)
        attention_router,  # the Overview's "needs you" list (cross-kind)
        event_router,  # the daemon-wide change feed (cross-kind)
        # Before the ref routes: their `{ref:path}` would otherwise match
        # `/approvals/...` for a DELETE nobody meant.
        secret_boundary_router,
        secret_router,
        settings_router,
        sync_router,  # spec vault-sync
        vault_router,  # spec vault-storage
        internal_engine_router,  # spec internal-engine
        # agent + skill (specs agent-registry/skill-manager)
        # Before agent_router: its `/{uid}` routes would otherwise see `mcp-import`.
        agent_mcp_import_router,
        agent_router,
        agent_config_router,
        agent_connection_router,
        agent_hooks_router,
        agent_workspace_router,
        agent_plugin_part_router,
        agent_native_memory_router,
        agent_session_router,
        agent_unmanaged_skill_router,
        fs_router,
        skill_copy_router,  # before skill_router: /skills/orphans is not a uid
        skill_delete_router,  # DELETE /skills/{uid} and the bulk delete
        skill_router,
        skill_source_router,
        skill_file_router,
        cli_router,  # the commands skills require (spec skill-manager)
        # MCP
        mcp_protocol_router,
        mcp_capability_router,
        mcp_server_test_router,
        mcp_config_test_router,  # testing a config before it is added (nothing saved)
        mcp_builtin_router,  # Coffer's own `coffer` server, read-only
        custom_tool_router,  # spec mcp-gateway: custom-tool groups
        mcp_invocation_router,
        mcp_invocation_aggregate_router,
        mcp_page_router,  # the MCP server page's 24 h summary, log and tiering reads
        knowledge_router,  # the one knowledge kind (experimental: knowledge)
        knowledge_history_router,  # … and its history
        *memory_routers,  # the one memory kind
        # the turn platform's own surfaces (spec chat; spec channels's agents run on it)
        agent_provider_router,
        model_router,
        chat_conversation_router,  # the Conversations page's REST surface
        chat_turn_router,  # … and stopping a turn
        channel_router,  # spec channels
        price_list_router,  # spec provider-switching (before /providers/{uid})
        model_switch_router,  # spec provider-switching: review + apply a model change
        provider_router,  # spec provider-switching
        proxy_router,  # spec provider-switching (the local model proxy)
        usage_router,  # spec provider-switching (usage metering)
    )
    for router in routers:
        _include(app, router)


def _feature_of(router: APIRouter) -> str | None:
    """The experimental feature whose route prefixes ``router``'s prefix sits
    under, or ``None``. Every router of a feature declares the feature's prefix
    as its own, so the prefix alone decides."""
    return feature_for_path(router.prefix) if router.prefix else None


def _include(app: FastAPI, router: APIRouter) -> None:
    """Mount one router, behind its experimental feature's gate if it has one."""
    feature = _feature_of(router)
    if feature is None:
        app.include_router(router)
    else:
        app.include_router(router, dependencies=[Depends(require_feature(feature))])
