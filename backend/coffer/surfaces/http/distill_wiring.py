"""Composition-root helper that wires the transcript-distillation slice.

Extracted from ``wiring.py`` so that file stays under 400 LOC.  This module
is the ONLY place that imports ``agent``, ``memory``, ``chat``, and ``distill``
together — it is a composition root (surfaces), so cross-kind imports are
allowed here (Contract: surfaces may import everything).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coffer.application.distill.service import TranscriptDistillationService
from coffer.application.memory.journal import JournalService
from coffer.application.memory.service import MemoryService
from coffer.application.provider.service import ProviderService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.distill.session import DistilledInsight
from coffer.domain.provider.config import ProviderConfig
from coffer.infrastructure.chat.llm_completion import LangchainLlmCompletion
from coffer.infrastructure.distill.transcript_reader import FileTranscriptReader
from coffer.surfaces.http.distill.state import set_distill_service
from coffer.surfaces.http.memory.dependencies import get_journal_service
from coffer.surfaces.http.native_memory_import_wiring import wire_native_memory_import
from coffer.surfaces.http.organize_wiring import wire_organize
from coffer.surfaces.http.reorg_wiring import wire_reorg

# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


class _JournalInsightSink:
    """InsightSinkPort adapter: writes each distilled insight to the journal lane."""

    def __init__(self, journal_service: JournalService) -> None:
        self._journal = journal_service

    async def record(
        self,
        *,
        project_path: str | None,
        insight: DistilledInsight,
        origin_session_id: str,
    ) -> str | None:
        from coffer.domain.errors import ScopeUnresolved

        # No global journal: only sessions resolving to a git project are recorded.
        if project_path is None:
            return None
        body = "\n\n".join(
            piece
            for piece in (insight.name.strip(), insight.description.strip(), insight.body.strip())
            if piece
        )
        try:
            entry = await self._journal.append(cwd=project_path, body=body, actor="agent")
        except ScopeUnresolved:
            return None  # path not inside a git project → skip
        if entry is None:
            return None  # empty insight body → skipped, no journal entry
        return entry.timestamp.isoformat()


class _AgentResolver:
    """AgentResolverPort adapter: looks up an agent Resource and returns its type + config dir."""

    def __init__(self, agent_service: Any) -> None:
        self._agents = agent_service

    async def resolve(self, name: str) -> tuple[str, str]:
        resource = await self._agents.get(name)
        cfg = AgentConfig.model_validate(resource.config)
        return cfg.type.value, str(cfg.resolved_config_dir())


class _ModelSelector:
    """ModelSelectorPort adapter: resolves Coffer's internal-engine connection
    (the ``internal_default`` provider) for distillation."""

    def __init__(self, provider_svc: ProviderService) -> None:
        self._svc = provider_svc

    async def get_default(self) -> ProviderConfig | None:
        return await self._svc.resolve_internal_connection()


# ---------------------------------------------------------------------------
# Wire function
# ---------------------------------------------------------------------------


def wire_distill(
    memory_service: MemoryService,
    agent_service: Any,
    provider_svc: ProviderService,
    credential_resolver: Callable[[str], str],
) -> TranscriptDistillationService:
    """Construct and register the transcript-distillation service.

    Must be called AFTER ``wire_memory_kind`` (needs a live ``MemoryService``),
    ``wire_agent_and_skill_kinds`` (needs a live ``AgentService``), and
    ``wire_provider_kind`` (needs a live ``ProviderService``).

    Exposes the service via ``set_distill_service`` so Task 10's routes can
    reach it through ``get_distill_service``.
    """
    svc = TranscriptDistillationService(
        reader=FileTranscriptReader(),
        llm=LangchainLlmCompletion(),
        sink=_JournalInsightSink(get_journal_service()),
        agents=_AgentResolver(agent_service),
        models=_ModelSelector(provider_svc),
        credential_resolver=credential_resolver,
    )
    set_distill_service(svc)
    # The memory consolidation organizer (spec 007 FR-027..031) is a sibling
    # internal-LLM consumer of the same memory + provider services; wire it here
    # so the app composition root keeps a single internal-LLM call site.
    wire_organize(memory_service, provider_svc, credential_resolver)
    # The agentic reorg service (spec 007 FR-033/034) — same collaborators.
    wire_reorg(memory_service, provider_svc, credential_resolver)
    # Native-memory adoption (spec 004 FR-041): import an agent's OWN native memory
    # into Coffer memory, then organize. Wired AFTER wire_organize so the import sink's
    # organize() can reach the organizer via get_organizer_service.
    wire_native_memory_import(memory_service, agent_service)
    return svc
