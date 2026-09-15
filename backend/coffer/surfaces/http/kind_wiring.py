"""Wire every resource kind, in the order they depend on each other.

Gathered out of ``app.py``'s lifespan because the order is the only thing here
worth reading, and it was buried between the things that surround it: provider
after agent, because it projects into each agent's native config; memory before
MCP, so the gateway advertises ``coffer__recall``; MCP last of the kinds, so it
picks up every built-in tool the others registered. Each step returns what it
built and the next step takes it as a parameter, so the dependency is the
argument list, not a getter that happens to be populated by then.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.knowledge.skill_seed import seed_knowledge_skill
from coffer.application.resource_service import ResourceService
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.surfaces.http.agent_skill_wiring import AgentSkillWiring, wire_agent_and_skill_kinds
from coffer.surfaces.http.app_mcp_composition import McpWiring, wire_mcp_kind
from coffer.surfaces.http.knowledge_wiring import KnowledgeWiring, wire_knowledge_kind
from coffer.surfaces.http.memory_wiring import MemoryWiring, wire_memory_kind
from coffer.surfaces.http.provider_wiring import ProviderWiring, wire_provider_kind
from coffer.surfaces.http.sync_contributions import SyncContributions


@dataclass(frozen=True)
class KindWirings:
    """Every kind's result, bundled for the lifespan in wiring order."""

    agent_skill: AgentSkillWiring
    provider: ProviderWiring
    knowledge: KnowledgeWiring
    memory: MemoryWiring
    mcp: McpWiring


async def wire_resource_kinds(
    app: FastAPI,
    *,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker[AsyncSession],
    builtin_tools: BuiltinToolRegistry,
    credential_store: EncryptedCredentialStore,
    credential_resolver: Callable[[str], str],
    sync: SyncContributions,
) -> KindWirings:
    # Agent + skill kinds (004/005), lockstep: on_delete cascade + skill tools → gateway.
    agent_skill = wire_agent_and_skill_kinds(
        app, resource_svc, audit, sm, builtin_tools, credential_store, sync
    )

    # Provider switching (spec provider-switching) — AFTER the agent kind: it projects the
    # active profile into each agent's native config (see provider_wiring).
    provider = wire_provider_kind(
        app, resource_svc, audit, credential_store, agent_skill.agent_service, sync
    )

    # The one knowledge kind: a directory of markdown files. Also builds ranked
    # retrieval and ingestion, and registers its built-in tools.
    knowledge = wire_knowledge_kind(
        app, resource_svc, audit, builtin_tools, provider.service, credential_resolver
    )

    # The layer's delivery half (spec knowledge FR-042): a skill that tells an
    # agent this directory is here, shipped down the skill channel that already
    # reaches every managed agent. Best-effort — a failed seed must not stop the
    # daemon, and the tools work either way.
    await seed_knowledge_skill(agent_skill.skill_service)

    # Before wire_mcp_kind below, so the gateway advertises `coffer__recall`.
    memory = wire_memory_kind(
        app,
        resource_svc,
        audit,
        builtin_tools,
        provider.service,
        credential_resolver,
        sm,
        agent_skill.agent_service,
        sync,
    )

    # Wire up MCP-specific plumbing (after other kinds so the gateway picks
    # their built-in tools).
    mcp = wire_mcp_kind(app, resource_svc, audit, sm, credential_store, builtin_tools, sync)
    return KindWirings(
        agent_skill=agent_skill, provider=provider, knowledge=knowledge, memory=memory, mcp=mcp
    )
