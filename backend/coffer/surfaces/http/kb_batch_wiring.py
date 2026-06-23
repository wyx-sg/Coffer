"""Composition helper for async KB document re-embed.

``start_kb_batch`` builds the shared :class:`AsyncOpRunner` + registry, wires a
:class:`KnowledgeBaseBatchService` against the live KB service (re-embed retries
just the embedding for one document — the slow ingest step moved off the request
path), starts the worker pool, and registers the service for the KB routes.
``stop_kb_batch`` tears the pool down. Both run from the app lifespan so
``app.py`` stays under the file-size budget.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from coffer.application.async_ops.registry import AsyncOpRegistry
from coffer.application.async_ops.runner import AsyncOpRunner
from coffer.application.knowledge_base.batch import KnowledgeBaseBatchService
from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.domain.knowledge.document import DOCUMENT_SCAN_LIMIT, Document
from coffer.surfaces.http.knowledge_base.state import set_kb_batch_service

_DEFAULT_CONCURRENCY = 2
_MAX_SELECT_ALL = 1000


def _concurrency() -> int:
    try:
        return max(1, int(os.environ.get("COFFER_KB_BATCH_CONCURRENCY", _DEFAULT_CONCURRENCY)))
    except (TypeError, ValueError):
        return _DEFAULT_CONCURRENCY


async def start_kb_batch(app: FastAPI, *, kb_service: KnowledgeBaseService) -> None:
    """Wire and start the async KB re-embed worker pool."""
    registry = AsyncOpRegistry()
    runner = AsyncOpRunner(registry, concurrency=_concurrency())
    await runner.start()

    async def list_documents(kb_name: str) -> list[Document]:
        docs, _total = await kb_service.list_documents(
            kb_name=kb_name, limit=DOCUMENT_SCAN_LIMIT, offset=0
        )
        return docs

    async def reembed(kb_name: str, document_id: str) -> None:
        await kb_service.reembed_document(kb_name=kb_name, document_id=document_id)

    svc = KnowledgeBaseBatchService(
        runner=runner,
        registry=registry,
        list_documents=list_documents,
        reembed=reembed,
        max_select_all=_MAX_SELECT_ALL,
    )
    set_kb_batch_service(svc)
    app.state.kb_batch_runner = runner


async def stop_kb_batch(app: FastAPI) -> None:
    """Stop the KB re-embed worker pool if it was started."""
    runner = getattr(app.state, "kb_batch_runner", None)
    if runner is not None:
        await runner.stop()
