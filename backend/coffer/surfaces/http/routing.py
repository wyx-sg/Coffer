"""Router registration table for the FastAPI app.

Extracted from ``app.py`` so the composition root stays within the 400-line
guideline: every sub-router import + ``include_router`` call lives here, grouped
by spec, and ``app.py`` calls :func:`include_all_routers` once.

The routers of an experimental feature are included behind its gate
(``require_feature``), so every route under them answers 404
``FEATURE_DISABLED`` while the feature is off, and serves again the moment it is
switched on (spec experimental-features "Close every surface of a switched-off
feature"). The gate goes on at include time rather than on each router: a
router split into sub-routers (memory's four) cannot forget one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI

from coffer.surfaces.http import daemon_routes
from coffer.surfaces.http.agent_config_routes import router as agent_config_router
from coffer.surfaces.http.agent_native_memory_routes import (
    router as agent_native_memory_router,
)
from coffer.surfaces.http.agent_routes import router as agent_router
from coffer.surfaces.http.agent_transcript_routes import router as agent_transcript_router
from coffer.surfaces.http.agent_unmanaged_skill_routes import (
    router as agent_unmanaged_skill_router,
)
from coffer.surfaces.http.agent_workspace_routes import router as agent_workspace_router
from coffer.surfaces.http.audit_routes import router as audit_router
from coffer.surfaces.http.channel_routes import router as channel_router
from coffer.surfaces.http.chat.agent_provider_routes import router as agent_provider_router
from coffer.surfaces.http.chat.conversation_routes import router as chat_conversation_router
from coffer.surfaces.http.chat.turn_routes import router as chat_turn_router
from coffer.surfaces.http.credential_routes import router as credential_router
from coffer.surfaces.http.feature_dependencies import require_feature
from coffer.surfaces.http.feature_routes import router as feature_router
from coffer.surfaces.http.fs_routes import router as fs_router
from coffer.surfaces.http.internal_engine_routes import router as internal_engine_router
from coffer.surfaces.http.knowledge import router as knowledge_router
from coffer.surfaces.http.mcp.capability_routes import router as mcp_capability_router
from coffer.surfaces.http.mcp.invocation_routes import (
    aggregate_router as mcp_invocation_aggregate_router,
)
from coffer.surfaces.http.mcp.invocation_routes import router as mcp_invocation_router
from coffer.surfaces.http.mcp.protocol_routes import router as mcp_protocol_router
from coffer.surfaces.http.mcp.server_test_routes import router as mcp_server_test_router
from coffer.surfaces.http.memory import router as memory_router
from coffer.surfaces.http.model_routes import router as model_router
from coffer.surfaces.http.provider_routes import router as provider_router
from coffer.surfaces.http.resource_routes import router as resource_router
from coffer.surfaces.http.retention_routes import router as retention_router
from coffer.surfaces.http.settings_routes import router as settings_router
from coffer.surfaces.http.skill_file_routes import router as skill_file_router
from coffer.surfaces.http.skill_routes import router as skill_router
from coffer.surfaces.http.sync_routes import router as sync_router
from coffer.surfaces.http.upkeep_routes import router as upkeep_router


def include_all_routers(app: FastAPI) -> None:
    """Mount every sub-router, grouped by spec (kind-agnostic core first)."""
    entries: tuple[APIRouter | tuple[APIRouter, str], ...] = (
        daemon_routes.router,
        feature_router,  # spec experimental-features
        resource_router,
        audit_router,
        retention_router,
        upkeep_router,  # what this daemon is rewriting right now (cross-kind)
        credential_router,
        settings_router,
        (sync_router, "vault_sync"),  # spec vault-sync
        internal_engine_router,  # spec internal-engine
        # agent + skill (specs agent-registry/skill-manager)
        agent_router,
        agent_config_router,
        agent_workspace_router,
        agent_native_memory_router,
        agent_transcript_router,
        agent_unmanaged_skill_router,
        fs_router,
        skill_router,
        skill_file_router,
        # MCP
        mcp_protocol_router,
        mcp_capability_router,
        mcp_server_test_router,
        mcp_invocation_router,
        mcp_invocation_aggregate_router,
        (knowledge_router, "knowledge"),  # the one knowledge kind
        (memory_router, "memory"),  # the one memory kind
        # the turn platform's own surfaces (spec chat; spec channels's agents run on it)
        agent_provider_router,
        model_router,
        chat_conversation_router,  # the web Chat page's own REST surface
        chat_turn_router,  # … and its turn/SSE half
        channel_router,  # spec channels
        provider_router,  # spec provider-switching
    )
    for entry in entries:
        _include(app, entry)


def _include(app: FastAPI, entry: APIRouter | tuple[APIRouter, str]) -> None:
    """Mount one router, behind its experimental feature's gate if it has one."""
    if isinstance(entry, tuple):
        router, feature = entry
        app.include_router(router, dependencies=[Depends(require_feature(feature))])
    else:
        app.include_router(entry)
