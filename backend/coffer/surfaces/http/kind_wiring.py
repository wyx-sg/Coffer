"""Wire every resource kind, in the order they depend on each other.

Gathered out of ``app.py``'s lifespan because the order is the only thing here
worth reading, and it was buried between the things that surround it: provider
after agent, because it projects into each agent's native config; memory before
MCP, so the gateway advertises ``coffer__recall``; MCP last of the kinds, so it
picks up every built-in tool the others registered.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.skill_seed import seed_knowledge_skill
from coffer.application.resource_service import ResourceService
from coffer.surfaces.http.agent_skill_wiring import wire_agent_and_skill_kinds
from coffer.surfaces.http.app_mcp_composition import wire_mcp_kind
from coffer.surfaces.http.dependencies import (
    get_agent_service,
    get_provider_service,
    get_skill_service,
)
from coffer.surfaces.http.knowledge_wiring import wire_knowledge_kind
from coffer.surfaces.http.memory_wiring import wire_memory_kind
from coffer.surfaces.http.provider_wiring import wire_provider_kind


async def wire_resource_kinds(
    app: FastAPI,
    *,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: Any,
    builtin_tools: Any,
    credential_store: Any,
    credential_resolver: Any,
) -> tuple[KnowledgeService, Any, Any]:
    # Agent + skill kinds (004/005), lockstep: on_delete cascade + skill tools → gateway.
    wire_agent_and_skill_kinds(app, resource_svc, audit, sm, builtin_tools, credential_store)

    # Provider switching (spec provider-switching) — AFTER the agent kind: it projects the
    # active profile into each agent's native config (see provider_wiring).
    wire_provider_kind(app, resource_svc, audit, credential_store, sm)

    # The one knowledge kind: a directory of markdown files. Also builds ranked
    # retrieval and ingestion, and registers its built-in tools.
    knowledge_service = wire_knowledge_kind(
        app,
        resource_svc,
        audit,
        builtin_tools,
        get_provider_service(),
        credential_resolver,
    )

    # The layer's delivery half (spec knowledge FR-042): a skill that tells an
    # agent this directory is here, shipped down the skill channel that already
    # reaches every managed agent. Best-effort — a failed seed must not stop the
    # daemon, and the tools work either way.
    await seed_knowledge_skill(get_skill_service())

    # Before wire_mcp_kind below, so the gateway advertises `coffer__recall`.
    wire_memory_kind(
        app,
        resource_svc,
        audit,
        builtin_tools,
        get_provider_service(),
        credential_resolver,
        sm,
        get_agent_service(),
    )

    # Wire up MCP-specific plumbing (after other kinds so the gateway picks
    # their built-in tools).
    process_supervisor, session_supervisors = wire_mcp_kind(
        app, resource_svc, audit, sm, credential_store, builtin_tools
    )
    return knowledge_service, process_supervisor, session_supervisors
