"""Unit tests for KnowledgeBaseBatchService — enqueue logic, skip-embedded, status."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.async_ops.registry import AsyncOpRegistry, OpState
from coffer.application.async_ops.runner import AsyncOpRunner
from coffer.application.knowledge_base.batch import (
    STATUS_DONE,
    STATUS_EMBEDDING,
    KnowledgeBaseBatchService,
)
from coffer.domain.knowledge.document import KIND_KNOWLEDGE_BASE, Document

pytestmark = pytest.mark.asyncio


def _doc(doc_id: str, *, embed_pending: bool) -> Document:
    now = datetime.now(tz=UTC)
    return Document(
        id=doc_id,
        kind=KIND_KNOWLEDGE_BASE,
        resource_name="kb1",
        path=f"docs/{doc_id}.md",
        title=doc_id,
        content_sha256="sha",
        source_mode="converted",
        created_at=now,
        updated_at=now,
        embed_pending=embed_pending,
    )


class _Fixture:
    """A KnowledgeBaseBatchService wired against in-memory fakes."""

    def __init__(self, *, docs: list[tuple[str, bool]]) -> None:
        self.registry = AsyncOpRegistry()
        self.runner = AsyncOpRunner(self.registry, concurrency=1)  # not started: enqueue-only
        self._docs = [_doc(d, embed_pending=p) for d, p in docs]
        self.reembed_calls: list[tuple[str, str]] = []

        async def list_documents(_kb: str) -> list[Document]:
            return self._docs

        async def reembed(kb_name: str, document_id: str) -> None:
            self.reembed_calls.append((kb_name, document_id))

        self.svc = KnowledgeBaseBatchService(
            runner=self.runner,
            registry=self.registry,
            list_documents=list_documents,
            reembed=reembed,
        )


async def test_enqueue_documents_skips_already_embedded():
    fx = _Fixture(docs=[("a", True), ("b", False), ("c", True)])
    result = await fx.svc.enqueue_documents("kb1", ["a", "b"])
    assert result.queued == 1  # a (pending)
    assert result.skipped == 1  # b (already embedded)
    assert fx.registry.get("kb_embed", "kb1\x00a").state is OpState.queued  # type: ignore[union-attr]
    assert fx.registry.get("kb_embed", "kb1\x00b") is None


async def test_enqueue_all_enqueues_every_pending():
    fx = _Fixture(docs=[("a", True), ("b", False), ("c", True)])
    result = await fx.svc.enqueue_all("kb1")
    assert result.queued == 2  # a, c
    assert result.skipped == 1  # b
    assert result.total == 3


async def test_enqueue_does_not_double_enqueue_in_flight():
    fx = _Fixture(docs=[("a", True)])
    first = await fx.svc.enqueue_documents("kb1", ["a"])
    second = await fx.svc.enqueue_documents("kb1", ["a"])
    assert first.queued == 1
    assert second.queued == 0  # already queued — not re-enqueued


async def test_derived_status_done_vs_embedding():
    assert (
        KnowledgeBaseBatchService.derived_status(_doc("a", embed_pending=True)) == STATUS_EMBEDDING
    )
    assert KnowledgeBaseBatchService.derived_status(_doc("b", embed_pending=False)) == STATUS_DONE


async def test_inflight_maps_document_id():
    fx = _Fixture(docs=[("a", True), ("b", True)])
    await fx.svc.enqueue_all("kb1")
    inflight = fx.svc.inflight("kb1")
    assert set(inflight) == {"a", "b"}
    assert inflight["a"].state is OpState.queued


async def test_runner_invokes_reembed_factory():
    fx = _Fixture(docs=[("a", True)])
    await fx.runner.start()
    try:
        await fx.svc.enqueue_all("kb1")
        await fx.runner._queue.join()  # drain
    finally:
        await fx.runner.stop()
    assert fx.reembed_calls == [("kb1", "a")]
    # On success the registry entry is cleared (durable status takes over).
    assert fx.registry.get("kb_embed", "kb1\x00a") is None
