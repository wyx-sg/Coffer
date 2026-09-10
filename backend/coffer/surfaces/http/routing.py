"""Router registration table for the FastAPI app.

Extracted from ``app.py`` so the composition root stays within the 400-line
guideline: every sub-router import + ``include_router`` call lives here, grouped
by spec, and ``app.py`` calls :func:`include_all_routers` once.
"""

from __future__ import annotations

from fastapi import FastAPI

from coffer.surfaces.http import daemon_routes
from coffer.surfaces.http.agent_config_routes import router as agent_config_router
from coffer.surfaces.http.agent_provider_routes import router as agent_provider_router
from coffer.surfaces.http.agent_routes import router as agent_router
from coffer.surfaces.http.agent_unmanaged_skill_routes import (
    router as agent_unmanaged_skill_router,
)
from coffer.surfaces.http.agent_workspace_routes import router as agent_workspace_router
from coffer.surfaces.http.audit_routes import router as audit_router
from coffer.surfaces.http.channel_routes import router as channel_router
from coffer.surfaces.http.credential_routes import router as credential_router
from coffer.surfaces.http.embedding_routes import router as embedding_router
from coffer.surfaces.http.fs_routes import router as fs_router
from coffer.surfaces.http.internal_engine_routes import router as internal_engine_router
from coffer.surfaces.http.knowledge import router as knowledge_router
from coffer.surfaces.http.mcp.capability_routes import router as mcp_capability_router
from coffer.surfaces.http.mcp.invocation_routes import router as mcp_invocation_router
from coffer.surfaces.http.mcp.protocol_routes import router as mcp_protocol_router
from coffer.surfaces.http.mcp.server_test_routes import router as mcp_server_test_router
from coffer.surfaces.http.mcp.tiering_routes import router as mcp_tiering_router
from coffer.surfaces.http.model_routes import router as model_router
from coffer.surfaces.http.provider_routes import router as provider_router
from coffer.surfaces.http.resource_routes import router as resource_router
from coffer.surfaces.http.retention_routes import router as retention_router
from coffer.surfaces.http.settings_routes import router as settings_router
from coffer.surfaces.http.skill_file_routes import router as skill_file_router
from coffer.surfaces.http.skill_routes import router as skill_router
from coffer.surfaces.http.sync_routes import router as sync_router


def include_all_routers(app: FastAPI) -> None:
    """Mount every sub-router, grouped by spec (kind-agnostic core first)."""
    for sub_router in (
        daemon_routes.router,
        resource_router,
        audit_router,
        retention_router,
        credential_router,
        settings_router,
        sync_router,  # spec 010
        embedding_router,
        internal_engine_router,  # spec 011
        # agent + skill (specs 004/005)
        agent_router,
        agent_config_router,
        agent_workspace_router,
        agent_unmanaged_skill_router,
        fs_router,
        skill_router,
        skill_file_router,
        # MCP
        mcp_protocol_router,
        mcp_capability_router,
        mcp_server_test_router,
        mcp_invocation_router,
        mcp_tiering_router,
        knowledge_router,  # the one knowledge kind
        # the turn platform's own surfaces (spec 009's agents run on it)
        agent_provider_router,
        model_router,
        channel_router,  # spec 009
        provider_router,  # spec 011
    ):
        app.include_router(sub_router)
