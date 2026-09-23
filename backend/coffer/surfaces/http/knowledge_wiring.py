"""Wiring for the one ``knowledge`` kind.

Three things are built here: the directory service, ``IngestService`` (document
upload), and the renderer for Coffer's own skill, which carries the catalogue.

There is no ``SearchService`` any more, and no retrieval tool to register
alongside it. The layer exposes exactly one built-in, ``coffer__write``
(spec knowledge "Expose exactly one knowledge tool"); reading is the agent's
own, at the absolute paths the delivered skill carries. ``IngestService`` takes
an optional ``completion`` port and so cannot fail to build: with no internal
connection configured it falls back to the document's own opening prose ("Fill
frontmatter on converted material"). The model port is handed in rather than
built here — which connection the internal engine runs on is the engine's
question, not this kind's (spec internal-engine "Reach the engine only through
its ports").

What this module hands back is TEXT, not a delivery. The skill that carries
the catalogue is an ordinary skill resource now, written into the master store
by the skill kind (``application.skill.builtin_seed``) and delivered by the
same links as any other. Those two kinds may not import each other, so the
pairing is made one level up, in ``guide_wiring`` — a composition root is the
one place allowed to bridge kinds (Contract 5).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.engine_ports import ModelSelectorPort
from coffer.application.knowledge import guide_render
from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.ingest import IngestService
from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.knowledge.service import (
    KIND_KNOWLEDGE,
    CatalogueChanged,
    KnowledgeService,
)
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.converters.registry import default_registry
from coffer.infrastructure.llm.llm_completion import LangchainLlmCompletion
from coffer.surfaces.http.engine_config_composition import read_internal_engine_timeout
from coffer.surfaces.http.guide_wiring import GuideRenderer
from coffer.surfaces.http.knowledge.dependencies import (
    set_ingest_service,
    set_knowledge_service,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from coffer.application.audit_service import AuditService
    from coffer.application.resource_service import ResourceService


@dataclass(frozen=True)
class KnowledgeWiring:
    """What the knowledge kind hands back: the directory service and its
    consumers (the channel ``/save`` card takes the first two), the
    internal-model selector the curation pass shares, and the renderer for
    Coffer's own skill, which the pass re-runs whenever the corpus changes."""

    service: KnowledgeService
    ingest_service: IngestService
    models: ModelSelectorPort
    render_guide: GuideRenderer


def wire_knowledge_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    builtin_tools: BuiltinToolRegistry,
    models: ModelSelectorPort,
    credential_resolver: Callable[[str], str],
    on_catalogue_changed: CatalogueChanged,
) -> KnowledgeWiring:
    """Wire the ``knowledge`` kind into the app and return what it built."""

    async def _merge_available() -> bool:
        # A pass needs the internal model and nothing else to merge material;
        # without one, material is promoted to a document on the spot ("Promote
        # material directly when no model is configured").
        return await models.get_default() is not None

    service = KnowledgeService(
        resources=resource_svc,
        audit=audit,
        on_catalogue_changed=on_catalogue_changed,
        merge_available=_merge_available,
    )
    set_knowledge_service(service)

    ingest_service = IngestService(
        knowledge=service,
        registry=default_registry(),
        models=models,
        completion=LangchainLlmCompletion(),
        credential_resolver=credential_resolver,
        read_timeout=read_internal_engine_timeout,
    )
    set_ingest_service(ingest_service)

    async def _render_guide() -> str:
        # One rendering for the whole machine: the catalogue carries no
        # per-agent slice, so there is one text and every agent gets it.
        return guide_render.render(
            guide_render.display_root(paths.knowledge_root()),
            await service.catalogue(),
        )

    register_knowledge_builtin_tools(builtin_tools, knowledge_service=service)
    app.state.kinds[KIND_KNOWLEDGE] = make_knowledge_kind(service)
    return KnowledgeWiring(
        service=service,
        ingest_service=ingest_service,
        models=models,
        render_guide=_render_guide,
    )
