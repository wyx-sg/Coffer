"""Async batch re-embed for knowledge-base documents.

The slow part of KB ingest is convert+chunk+embed; this module moves the
embed-retry of EXISTING documents off the request path. A document indexed
keyword-only because the embedding provider was unavailable carries
``embed_pending=True`` (the durable, derived "embedding" status); this service
re-runs JUST that embed via the shared :class:`AsyncOpRunner` so the UI can fire
single / batch / re-embed-all without blocking and poll per-document status.

Derived list statuses are cheap (the persisted ``embed_pending`` flag); the
in-flight states (queued / running / error) are overlaid from the registry by
the surface layer. All collaborators are injected as plain callables so this
application module imports nothing from infrastructure or surfaces.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coffer.application.async_ops.registry import AsyncOpRegistry, InflightEntry, OpState
from coffer.application.async_ops.runner import AsyncOpRunner
from coffer.domain.knowledge.document import Document

#: Operation type key in the shared registry.
OP_TYPE = "kb_embed"
_SEP = "\x00"  # kb_name / document_id separator in registry keys (neither contains NUL)

#: Derived list statuses — cheap (the persisted ``embed_pending`` flag). In-flight
#: states (queued / running / error) are overlaid from the registry by the surface.
STATUS_DONE = "done"
STATUS_EMBEDDING = "embedding"


@dataclass(frozen=True)
class EnqueueResult:
    """Outcome of a batch enqueue."""

    queued: int  # newly enqueued
    skipped: int  # already embedded / not pending (nothing to do)
    total: int  # candidates considered


class KnowledgeBaseBatchService:
    """Enqueues per-document re-embed work and reports per-document status."""

    def __init__(
        self,
        *,
        runner: AsyncOpRunner,
        registry: AsyncOpRegistry,
        list_documents: Callable[[str], Awaitable[list[Document]]],
        reembed: Callable[[str, str], Awaitable[None]],
        max_select_all: int = 1000,
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._list_documents = list_documents
        self._reembed = reembed
        self._max_select_all = max_select_all

    @staticmethod
    def _key(kb_name: str, document_id: str) -> str:
        return f"{kb_name}{_SEP}{document_id}"

    def inflight(self, kb_name: str) -> dict[str, InflightEntry]:
        """In-flight entries for *kb_name*, keyed by document_id."""
        prefix = f"{kb_name}{_SEP}"
        snap = self._registry.snapshot(OP_TYPE, prefix=prefix)
        return {key[len(prefix) :]: entry for key, entry in snap.items()}

    @staticmethod
    def derived_status(doc: Document) -> str:
        """``embedding`` while the embed is pending, else ``done`` (from the flag)."""
        return STATUS_EMBEDDING if doc.embed_pending else STATUS_DONE

    async def enqueue_documents(self, kb_name: str, document_ids: list[str]) -> EnqueueResult:
        """Enqueue an explicit set of documents (skip those not pending an embed)."""
        docs = await self._list_documents(kb_name)
        wanted = set(document_ids)
        chosen = [d for d in docs if d.id in wanted]
        return self._enqueue(kb_name, chosen)

    async def enqueue_all(self, kb_name: str) -> EnqueueResult:
        """Enqueue every document still pending an embed (re-embed-all)."""
        docs = await self._list_documents(kb_name)
        return self._enqueue(kb_name, docs)

    def _enqueue(self, kb_name: str, docs: list[Document]) -> EnqueueResult:
        queued = 0
        skipped = 0
        for doc in docs:
            if not doc.embed_pending:
                skipped += 1  # already embedded — nothing to retry
                continue
            key = self._key(kb_name, doc.id)
            existing = self._registry.get(OP_TYPE, key)
            if existing is not None and existing.state in (OpState.queued, OpState.running):
                continue  # already in flight — don't double-enqueue
            self._runner.enqueue(OP_TYPE, key, self._factory(kb_name, doc.id))
            queued += 1
        return EnqueueResult(queued=queued, skipped=skipped, total=len(docs))

    def _factory(self, kb_name: str, document_id: str) -> Callable[[], Awaitable[None]]:
        async def _run() -> None:
            await self._reembed(kb_name, document_id)

        return _run
