"""Composition-root helper that wires the transcript-history slice (ADR-022).

Mirrors ``distill_wiring.py``. Reuses the shared knowledge substrate (the same
``DocumentRepo`` / retrieval / reindexer KB and memory share) under the
``transcript`` discriminator, plus the SAME read-only ``FileTranscriptReader``
the distill slice uses. The agent catalog adapter lists/resolves registered
agents so the reader can find each one's config dir.
"""

from __future__ import annotations

from typing import Any

from coffer.application.history.service import HistoryService
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import KnowledgeRetrieval
from coffer.domain.agent.config import AgentConfig
from coffer.infrastructure.distill.transcript_reader import FileTranscriptReader
from coffer.infrastructure.knowledge.repository import DocumentRepo
from coffer.surfaces.http.history.state import set_history_service


class _AgentCatalog:
    """AgentCatalogPort adapter over the agent ResourceService."""

    def __init__(self, agent_service: Any) -> None:
        self._agents = agent_service

    async def list_agents(self) -> list[str]:
        resources = await self._agents.list()
        return [r.name for r in resources]

    async def resolve(self, name: str) -> tuple[str, str]:
        resource = await self._agents.get(name)
        cfg = AgentConfig.model_validate(resource.config)
        return cfg.type.value, str(cfg.resolved_config_dir())


def wire_history(
    substrate: tuple[DocumentRepo, KnowledgeRetrieval, Reindexer],
    agent_service: Any,
) -> HistoryService:
    """Construct and register the transcript-history service.

    Must be called AFTER ``build_substrate`` and the agent wiring (needs a live
    ``AgentService``). Exposes the service via ``set_history_service`` so the
    ``/api/v1/history`` routes reach it through ``get_history_service``.
    """
    documents, retrieval, reindexer = substrate
    svc = HistoryService(
        reader=FileTranscriptReader(),
        catalog=_AgentCatalog(agent_service),
        documents=documents,
        retrieval=retrieval,
        reindexer=reindexer,
    )
    set_history_service(svc)
    return svc
