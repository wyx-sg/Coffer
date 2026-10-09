"""Wiring for the one ``knowledge`` kind.

Three things are built here: the directory service, ``IngestService`` (document
upload), and the renderer for Coffer's own skill, which carries the catalogue.

There is no ``SearchService`` any more, and no retrieval tool to register
alongside it. The layer exposes no built-in tool (spec knowledge "Expose no
knowledge tool"); reading and writing are the agent's own, at the absolute paths
the delivered skill carries. ``IngestService`` describes an upload from its own
opening prose ("Fill frontmatter on converted material"); no model is involved.

What this module hands back is TEXT, not a delivery. The skill that carries
the catalogue is an ordinary skill resource now, written into the master store
by the skill kind (``application.skill.builtin_seed``) and delivered by the
same links as any other. Those two kinds may not import each other, so the
pairing is made one level up, in ``guide_wiring`` — a composition root is the
one place allowed to bridge kinds (Contract 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING

from coffer.application.builtin_tools import AgentDirectory, BuiltinToolRegistry
from coffer.application.knowledge import guide_render
from coffer.application.knowledge.change_service import KnowledgeChangeService
from coffer.application.knowledge.ingest import IngestService
from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.knowledge.service import (
    KIND_KNOWLEDGE,
    CatalogueChanged,
    KnowledgeService,
)
from coffer.domain.features import KNOWLEDGE
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.converters.registry import default_registry
from coffer.infrastructure.knowledge.history import KNOWLEDGE_HISTORY
from coffer.infrastructure.platform.host import machine_label
from coffer.surfaces.http.event_dependencies import announce_change
from coffer.surfaces.http.guide_wiring import GuideRenderer
from coffer.surfaces.http.knowledge.dependencies import (
    set_change_service,
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
    its upload ingest, and the renderer for
    Coffer's own skill, which the sweep re-runs whenever the corpus changes."""

    service: KnowledgeService
    ingest_service: IngestService
    render_guide: GuideRenderer


def wire_knowledge_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    builtin_tools: BuiltinToolRegistry,
    on_catalogue_changed: CatalogueChanged,
) -> KnowledgeWiring:
    """Wire the ``knowledge`` kind into the app and return what it built."""

    service = KnowledgeService(
        resources=resource_svc,
        audit=audit,
        on_catalogue_changed=on_catalogue_changed,
        # Every write a commit naming its writer (spec knowledge "Commit every
        # knowledge write naming its writer"), in the vault's repository.
        history=KNOWLEDGE_HISTORY,
        announce=lambda uid: announce_change(KIND_KNOWLEDGE, uid),
    )
    set_knowledge_service(service)
    set_change_service(
        KnowledgeChangeService(
            knowledge=service,
            history=KNOWLEDGE_HISTORY,
            audit=audit,
            # The OS and architecture do not change while the daemon runs.
            machine=cache(machine_label),
        )
    )

    ingest_service = IngestService(
        knowledge=service,
        registry=default_registry(),
    )
    set_ingest_service(ingest_service)

    features = app.state.feature_service

    async def _render_guide() -> str:
        # One rendering for the whole machine: the catalogue carries no
        # per-agent slice, so there is one text and every agent gets it.
        # While the ``knowledge`` feature is off the skill carries no catalogue,
        # and documents no knowledge tool (spec experimental-features);
        # nothing the feature holds moves.
        on = features.is_enabled(KNOWLEDGE)
        return guide_render.render(
            guide_render.display_root(paths.knowledge_root()),
            await service.catalogue() if on else None,
        )

    # No tool: knowledge is plain files an agent reads and writes with its own
    # tools; the directory entry is how the handshake learns the layer is on.
    builtin_tools.register_directory(
        AgentDirectory(
            name="knowledge", path=lambda: str(paths.knowledge_root()), feature=KNOWLEDGE
        )
    )
    app.state.kinds[KIND_KNOWLEDGE] = make_knowledge_kind(service)
    return KnowledgeWiring(
        service=service,
        ingest_service=ingest_service,
        render_guide=_render_guide,
    )
