"""Wiring for the one ``knowledge`` kind.

One service for the directory itself, plus ``SearchService`` (literal search,
FR-024..FR-027) and ``IngestService`` (document upload, FR-033..FR-037).
``SearchService`` needs nothing but the knowledge service — search is ripgrep
over the files, with no model, key or connection behind it. ``IngestService``
takes an optional ``completion`` port and so cannot fail to build either: with
no internal connection configured it falls back to the document's own opening
prose (FR-034).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.ingest import IngestService
from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.knowledge.search import SearchService
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.infrastructure.knowledge.converters.registry import default_registry
from coffer.infrastructure.llm.llm_completion import LangchainLlmCompletion
from coffer.surfaces.http.dependencies import (
    set_ingest_service,
    set_knowledge_service,
    set_search_service,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from coffer.application.audit_service import AuditService
    from coffer.application.provider.service import ProviderService
    from coffer.application.resource_service import ResourceService
    from coffer.domain.provider.config import ResolvedConnection


class _InternalModelSelector:
    """Structural ``ModelSelectorPort`` adapter over ``ProviderService``.

    ``IngestService`` (like ``TidyPass`` before it) reaches the internal
    connection through a port with one method, ``get_default``, rather than
    ``ProviderService``'s own ``resolve_internal_connection`` — the port
    belongs to this layer, not to the provider kind, and mirrors the shape
    ``application.engine_ports.ModelSelectorPort`` already declares.
    """

    def __init__(self, provider_service: ProviderService) -> None:
        self._provider_service = provider_service

    async def get_default(self) -> ResolvedConnection | None:
        return await self._provider_service.resolve_internal_connection()


def wire_knowledge_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    builtin_tools: BuiltinToolRegistry,
    provider_service: ProviderService,
    credential_resolver: Callable[[str], str],
) -> KnowledgeService:
    """Wire the ``knowledge`` kind into the app and return its one service."""
    service = KnowledgeService(resources=resource_svc, audit=audit)
    set_knowledge_service(service)

    search_service = SearchService(knowledge=service)
    set_search_service(search_service)

    ingest_service = IngestService(
        knowledge=service,
        registry=default_registry(),
        models=_InternalModelSelector(provider_service),
        completion=LangchainLlmCompletion(),
        credential_resolver=credential_resolver,
    )
    set_ingest_service(ingest_service)

    register_knowledge_builtin_tools(
        builtin_tools, knowledge_service=service, search_service=search_service
    )
    app.state.kinds[KIND_KNOWLEDGE] = make_knowledge_kind(service)
    return service
