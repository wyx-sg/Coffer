"""Wire every resource kind, in the order they depend on each other.

Gathered out of ``app.py``'s lifespan because the order is the only thing here
worth reading, and it was buried between the things that surround it: provider
after agent, because it projects into each agent's native config; memory before
MCP, so the gateway's handshake can name the memory root; MCP last of the kinds,
so it picks up every built-in tool the others registered. Each step returns what it
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
from coffer.application.knowledge.guide_render import GUIDE_SKILL_NAME
from coffer.application.platform_port import PlatformPort
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.facets import AgentCatalog
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.surfaces.http.agent_skill_wiring import AgentSkillWiring, wire_agent_and_skill_kinds
from coffer.surfaces.http.app_mcp_composition import McpWiring, wire_mcp_kind
from coffer.surfaces.http.builtin_server_wiring import wire_builtin_server
from coffer.surfaces.http.guide_wiring import BuiltinGuide
from coffer.surfaces.http.knowledge_wiring import KnowledgeWiring, wire_knowledge_kind
from coffer.surfaces.http.memory_wiring import MemoryWiring, wire_memory_kind
from coffer.surfaces.http.provider_wiring import ProviderWiring, wire_provider_kind
from coffer.surfaces.http.secret_boundary_wiring import register_destination_source
from coffer.surfaces.http.sync_contributions import SyncContributions
from coffer.surfaces.http.sync_wiring import sync_remote_secret_source
from coffer.surfaces.http.usage_wiring import UsageWiring, wire_model_usage


@dataclass(frozen=True)
class KindWirings:
    """Every kind's result, bundled for the lifespan in wiring order."""

    agent_skill: AgentSkillWiring
    provider: ProviderWiring
    knowledge: KnowledgeWiring
    memory: MemoryWiring
    mcp: McpWiring
    #: Usage metering and subscription quota (spec provider-switching).
    usage: UsageWiring
    #: Coffer's own skill. Built here rather than by either kind because it is
    #: the knowledge layer's text written through the skill layer's store, and
    #: the two may not import each other.
    guide: BuiltinGuide


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
    platform: PlatformPort,
    agent_catalog: AgentCatalog,
    reconciler: Reconciler,
) -> KindWirings:
    # The sync remote's push token is a secret destination too; the secret
    # boundary reads it from here to adopt and list it (spec vault-sync "Hold a
    # push token pointed at a new URL until approved").
    register_destination_source(sync_remote_secret_source(sm))
    # Agent + skill kinds (004/005), lockstep: on_delete cascade + skill tools → gateway.
    agent_skill = wire_agent_and_skill_kinds(
        app,
        resource_svc,
        audit,
        sm,
        builtin_tools,
        credential_store,
        sync,
        platform,
        agent_catalog,
        reconciler,
    )

    # Provider switching (spec provider-switching) — AFTER the agent kind: it projects the
    # active profile into each agent's native config (see provider_wiring).
    provider = wire_provider_kind(
        app,
        resource_svc,
        audit,
        credential_store,
        agent_skill.agent_service,
        sync,
        agent_catalog,
        reconciler,
    )

    # What the proxy metered, and the official quota of subscription agents.
    usage = await wire_model_usage(
        sm, provider.service, agent_skill.agent_service, prices=provider.prices, audit=audit
    )

    # Coffer's own skill carries the knowledge catalogue, so a collection
    # appearing, going or being switched has to reach the rendered file. The
    # binding is late by necessity and not by accident: what renders that file
    # needs the knowledge service to exist first, so the hook reads ``guide``
    # at call time rather than closing over what it was at wiring time.
    guide: BuiltinGuide | None = None

    async def _catalogue_changed() -> None:
        if guide is not None:
            await guide.refresh()

    # The one knowledge kind: a directory of markdown files. Also builds ranked
    # retrieval and ingestion, and registers its built-in tools.
    knowledge = wire_knowledge_kind(
        app,
        resource_svc,
        audit,
        builtin_tools,
        provider.internal_connection,
        credential_resolver,
        _catalogue_changed,
    )

    # Before wire_mcp_kind below, so the gateway's handshake names the memory root.
    memory = wire_memory_kind(
        app,
        resource_svc,
        audit,
        builtin_tools,
        provider.internal_connection,
        credential_resolver,
        agent_skill.agent_service,
        agent_catalog,
    )

    # Wire up MCP-specific plumbing (after other kinds so the gateway picks
    # their built-in tools).
    mcp = wire_mcp_kind(app, resource_svc, audit, sm, credential_store, builtin_tools, sync)
    # Coffer's own `coffer` server, described for the MCP servers page.
    wire_builtin_server(builtin_tools, agent_skill.agent_service, agent_skill.mcp_service)

    # Last, because it needs both ends: the knowledge kind's renderer and the
    # skill kind's seed. The lifespan refreshes it once every kind is up.
    guide = BuiltinGuide(
        name=GUIDE_SKILL_NAME,
        render=knowledge.render_guide,
        seed=agent_skill.builtin_seed,
    )
    return KindWirings(
        agent_skill=agent_skill,
        provider=provider,
        knowledge=knowledge,
        memory=memory,
        mcp=mcp,
        usage=usage,
        guide=guide,
    )
