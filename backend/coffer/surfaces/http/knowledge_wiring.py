"""Wiring for the one ``knowledge`` kind.

Three things are built here: the directory service, ``IngestService`` (document
upload, spec knowledge FR-016..FR-019), and ``KnowledgeSkillDelivery``, which
renders each agent's own copy of the knowledge skill.

There is no ``SearchService`` any more, and no retrieval tool to register
alongside it. The layer exposes exactly one built-in, ``coffer__write``
(FR-033); reading is the agent's own, at the absolute paths the delivered skill
carries. ``IngestService`` takes an optional ``completion`` port and so cannot
fail to build: with no internal connection configured it falls back to the
document's own opening prose (FR-017). The model port is handed in rather than
built here — which connection the internal engine runs on is the engine's
question, not this kind's (spec internal-engine FR-005).

Delivery bridges two kinds — it has to resolve an *agent's* skill directory to
write a *knowledge* artifact into it — and a composition root is the one place
allowed to do that (Contract 5), which is why the resolver is defined here
rather than inside ``application.knowledge``.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.engine_ports import ModelSelectorPort
from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.ingest import IngestService
from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.knowledge.skill_delivery import KnowledgeSkillDelivery
from coffer.domain.agent.config import AgentConfig
from coffer.infrastructure.knowledge.converters.registry import default_registry
from coffer.infrastructure.llm.llm_completion import LangchainLlmCompletion
from coffer.surfaces.http.knowledge.dependencies import (
    set_ingest_service,
    set_knowledge_service,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from coffer.application.audit_service import AuditService
    from coffer.application.resource_service import ResourceService
    from coffer.domain.resource import Resource


@dataclass(frozen=True)
class KnowledgeWiring:
    """What the knowledge kind hands back: the directory service and its
    consumers (the channel ``/save`` card takes the first two), the
    internal-model selector the curation pass shares, and the skill delivery
    the pass re-runs whenever the corpus changes."""

    service: KnowledgeService
    ingest_service: IngestService
    models: ModelSelectorPort
    skill_delivery: KnowledgeSkillDelivery


def wire_knowledge_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    builtin_tools: BuiltinToolRegistry,
    models: ModelSelectorPort,
    credential_resolver: Callable[[str], str],
) -> KnowledgeWiring:
    """Wire the ``knowledge`` kind into the app and return what it built."""
    service = KnowledgeService(resources=resource_svc, audit=audit)
    set_knowledge_service(service)

    ingest_service = IngestService(
        knowledge=service,
        registry=default_registry(),
        models=models,
        completion=LangchainLlmCompletion(),
        credential_resolver=credential_resolver,
    )
    set_ingest_service(ingest_service)

    async def _list_agents() -> list[Resource]:
        return await resource_svc.list(kind="agent")

    def _agent_skill_dir(r: object) -> pathlib.Path:
        # Typed as ``object`` to match the port: delivery does not care what
        # kind of record it is handed, only that this resolver knows how to
        # turn it into a directory.
        return AgentConfig.model_validate(cast("Resource", r).config).resolved_skill_dir()

    skill_delivery = KnowledgeSkillDelivery(
        service=service,
        list_agents=_list_agents,
        resolve_skill_dir=_agent_skill_dir,
    )

    register_knowledge_builtin_tools(builtin_tools, knowledge_service=service)
    app.state.kinds[KIND_KNOWLEDGE] = make_knowledge_kind(service)
    return KnowledgeWiring(
        service=service,
        ingest_service=ingest_service,
        models=models,
        skill_delivery=skill_delivery,
    )
