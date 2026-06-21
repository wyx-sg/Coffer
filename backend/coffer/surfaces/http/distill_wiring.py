"""Composition-root helper that wires the transcript-distillation slice.

Extracted from ``wiring.py`` so that file stays under 400 LOC.  This module
is the ONLY place that imports ``agent``, ``memory``, ``chat``, and ``distill``
together — it is a composition root (surfaces), so cross-kind imports are
allowed here (Contract: surfaces may import everything).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coffer.application.chat.model_service import ModelService
from coffer.application.distill.service import TranscriptDistillationService
from coffer.application.memory.service import MemoryService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.chat.model import ModelConfig
from coffer.domain.distill.session import DistilledInsight
from coffer.domain.memory.scope import MemoryScope
from coffer.infrastructure.chat.llm_completion import LangchainLlmCompletion
from coffer.infrastructure.distill.transcript_reader import FileTranscriptReader
from coffer.surfaces.http.distill.state import set_distill_service
from coffer.surfaces.http.organize_wiring import wire_organize
from coffer.surfaces.http.reorg_wiring import wire_reorg

# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


class _MemoryInsightSink:
    """InsightSinkPort adapter: writes each distilled insight as a memory fact."""

    def __init__(self, memory_service: MemoryService) -> None:
        self._memory = memory_service

    async def _add_fact(
        self,
        *,
        scope: MemoryScope,
        cwd: str | None,
        insight: DistilledInsight,
        origin_session_id: str,
    ) -> Any:
        return await self._memory.add_fact(
            scope=scope,
            cwd=cwd,
            name=insight.name,
            description=insight.description,
            body=insight.body,
            actor="agent",
            type=insight.type.value,
            origin_session_id=origin_session_id,
        )

    async def record(
        self,
        *,
        project_path: str | None,
        insight: DistilledInsight,
        origin_session_id: str,
    ) -> str:
        from coffer.domain.errors import ScopeUnresolved

        if project_path is not None:
            try:
                fact = await self._add_fact(
                    scope=MemoryScope.PROJECT,
                    cwd=project_path,
                    insight=insight,
                    origin_session_id=origin_session_id,
                )
                return str(fact.id)
            except ScopeUnresolved:
                pass  # project_path not inside a git work-tree; fall back to global
        fact = await self._add_fact(
            scope=MemoryScope.GLOBAL,
            cwd=None,
            insight=insight,
            origin_session_id=origin_session_id,
        )
        return str(fact.id)


class _AgentResolver:
    """AgentResolverPort adapter: looks up an agent Resource and returns its type + config dir."""

    def __init__(self, agent_service: Any) -> None:
        self._agents = agent_service

    async def resolve(self, name: str) -> tuple[str, str]:
        resource = await self._agents.get(name)
        cfg = AgentConfig.model_validate(resource.config)
        return cfg.type.value, str(cfg.resolved_config_dir())


class _ModelSelector:
    """ModelSelectorPort adapter: thin passthrough to ModelService.get_default / .get."""

    def __init__(self, model_svc: ModelService) -> None:
        self._svc = model_svc

    async def get_default(self) -> ModelConfig | None:
        return await self._svc.get_default()

    async def get(self, model_id: str) -> ModelConfig | None:
        return await self._svc.get(model_id)


# ---------------------------------------------------------------------------
# Wire function
# ---------------------------------------------------------------------------


def wire_distill(
    memory_service: MemoryService,
    agent_service: Any,
    model_svc: ModelService,
    credential_resolver: Callable[[str], str],
) -> TranscriptDistillationService:
    """Construct and register the transcript-distillation service.

    Must be called AFTER ``wire_memory_kind`` (needs a live ``MemoryService``),
    ``wire_agent_and_skill_kinds`` (needs a live ``AgentService``), and
    ``wire_chat`` (needs a live ``ModelService``).

    Exposes the service via ``set_distill_service`` so Task 10's routes can
    reach it through ``get_distill_service``.
    """
    svc = TranscriptDistillationService(
        reader=FileTranscriptReader(),
        llm=LangchainLlmCompletion(),
        sink=_MemoryInsightSink(memory_service),
        agents=_AgentResolver(agent_service),
        models=_ModelSelector(model_svc),
        credential_resolver=credential_resolver,
    )
    set_distill_service(svc)
    # The memory consolidation organizer (spec 007 FR-027..031) is a sibling
    # internal-LLM consumer of the same memory + model services; wire it here so
    # the app composition root keeps a single internal-LLM call site.
    wire_organize(memory_service, model_svc, credential_resolver)
    # The agentic reorg service (spec 007 FR-033/034) — same collaborators.
    wire_reorg(memory_service, model_svc, credential_resolver)
    return svc
