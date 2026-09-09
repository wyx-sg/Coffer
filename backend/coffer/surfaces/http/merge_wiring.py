"""Composition-root helper that wires the AI-assisted store merge (FR-056-059).

Clones ``organize_wiring.py``: the langchain one-shot completion adapter and a
``ProviderService`` wrapper are injected here; ``application/memory`` reaches
the LLM only through the memory-local ``LlmCompletionPort``. The evidence
gatherer closes over the memory service + binding repos, and the merge itself
reuses the SAME ``StoreConsolidator`` instance as resolve-time adoption
(handed over by ``wire_memory_kind`` via ``merge_state``) so both serialize on
one lock.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from coffer.application.memory.merge import StoreMergeService
from coffer.application.memory.merge_prompt import (
    MAX_SAMPLE_SLUGS,
    MAX_SAMPLE_TITLES,
    StoreEvidence,
)
from coffer.application.memory.scope import GLOBAL_STORE_NAME, KIND_MEMORY
from coffer.application.memory.service import MemoryService
from coffer.application.provider.service import ProviderService
from coffer.application.resource_service import ResourceService
from coffer.domain.provider.config import ResolvedConnection
from coffer.infrastructure.chat.llm_completion import LangchainLlmCompletion
from coffer.infrastructure.memory.scope_fs import normalize_remote_url, origin_remote_url
from coffer.surfaces.http.dependencies import get_audit_service, get_resource_service
from coffer.surfaces.http.memory.dependencies import get_project_root_repo, get_store_label_repo
from coffer.surfaces.http.memory.merge_state import (
    get_store_consolidator,
    set_merge_service,
)
from coffer.surfaces.http.memory.reorg_state import get_reorg_service


class _ModelSelector:
    """ModelSelectorPort adapter: resolves Coffer's internal-engine connection."""

    def __init__(self, provider_svc: ProviderService) -> None:
        self._svc = provider_svc

    async def get_default(self) -> ResolvedConnection | None:
        return await self._svc.resolve_internal_connection()


def _normalized_remote(root: str) -> str | None:
    if not Path(root).is_dir():
        return None
    url = origin_remote_url(root)
    return normalize_remote_url(url) if url else None


def wire_merge(
    memory_service: MemoryService,
    provider_svc: ProviderService,
    credential_resolver: Callable[[str], str],
) -> StoreMergeService:
    """Construct and register the StoreMergeService.

    Must be called AFTER ``wire_memory_kind`` (needs the shared consolidator +
    binding repos), ``wire_provider_kind`` (internal-engine resolution), and
    ``wire_reorg`` (the FR-059 post-merge pass reaches the reorg service) —
    ``wire_distill`` is the single internal-LLM call site that satisfies all
    three.
    """
    resources: ResourceService = get_resource_service()
    audit = get_audit_service()
    roots = get_project_root_repo()
    labels = get_store_label_repo()

    async def list_project_stores() -> list[str]:
        rs = await resources.list(kind=KIND_MEMORY)
        return [r.name for r in rs if r.name != GLOBAL_STORE_NAME]

    async def evidence(store_name: str) -> StoreEvidence:
        label = await labels.get(store_name)
        root = await roots.get(store_name)
        remote = _normalized_remote(root) if root else None
        try:
            facts = await memory_service.fact_count(store_name=store_name)
        except Exception:
            facts = 0
        titles: list[str] = []
        try:
            fact_list, _total = await memory_service.list_facts(
                store_name=store_name, limit=MAX_SAMPLE_TITLES
            )
            titles = [f.title for f in fact_list]
        except Exception:
            pass
        slugs: list[str] = []
        try:
            store_dir = (await memory_service.resolved_store(store_name)).store_dir
            knowledge = store_dir / "knowledge"
            slugs = sorted(p.stem for p in knowledge.glob("*.md") if p.stem != "INDEX")[
                :MAX_SAMPLE_SLUGS
            ]
        except Exception:
            pass
        return StoreEvidence(
            store=store_name,
            label=label,
            root=root,
            remote=remote,
            facts=facts,
            fact_titles=titles,
            topic_slugs=slugs,
        )

    async def run_reorg(store_name: str) -> str:
        result = await get_reorg_service().reorg(store_name=store_name)
        return str(result.status)

    svc = StoreMergeService(
        list_project_stores=list_project_stores,
        evidence=evidence,
        root_exists=lambda p: Path(p).is_dir(),
        llm=LangchainLlmCompletion(),
        models=_ModelSelector(provider_svc),
        credential_resolver=credential_resolver,
        consolidator=get_store_consolidator(),
        reorg=run_reorg,
        audit=audit,
    )
    set_merge_service(svc)
    return svc
