"""Start/stop for the async-operation batch workers.

Two things run off the request path: document re-embed (the slow tail of ingest
— convert+chunk+embed). It builds its own
:class:`AsyncOpRunner` + registry and registers its service for the routes;
this module groups them behind one start/stop pair so the app lifespan stays
under the file-size limit.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from coffer.application.async_ops.registry import AsyncOpRegistry
from coffer.application.async_ops.runner import AsyncOpRunner
from coffer.application.knowledge.batch import KnowledgeBaseBatchService
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.document import DOCUMENT_SCAN_LIMIT, Document
from coffer.surfaces.http.knowledge.batch_state import set_batch_service

_DEFAULT_CONCURRENCY = 2
_MAX_SELECT_ALL = 1000


def _concurrency() -> int:
    try:
        return max(1, int(os.environ.get("COFFER_KB_BATCH_CONCURRENCY", _DEFAULT_CONCURRENCY)))
    except (TypeError, ValueError):
        return _DEFAULT_CONCURRENCY


async def start_document_batch(app: FastAPI, *, knowledge_service: KnowledgeService) -> None:
    """Wire and start the async document re-embed worker pool.

    Re-embed retries just the embedding for one already-ingested document, so a
    scope whose provider was unavailable at ingest time recovers without a
    re-upload."""
    registry = AsyncOpRegistry()
    runner = AsyncOpRunner(registry, concurrency=_concurrency())
    await runner.start()

    async def list_documents(scope_name: str) -> list[Document]:
        docs, _total = await knowledge_service.list_documents(
            scope_name=scope_name, limit=DOCUMENT_SCAN_LIMIT, offset=0
        )
        return docs

    async def reembed(scope_name: str, document_id: str) -> None:
        await knowledge_service.reembed_document(scope_name=scope_name, document_id=document_id)

    set_batch_service(
        KnowledgeBaseBatchService(
            runner=runner,
            registry=registry,
            list_documents=list_documents,
            reembed=reembed,
            max_select_all=_MAX_SELECT_ALL,
        )
    )
    app.state.document_batch_runner = runner


async def stop_document_batch(app: FastAPI) -> None:
    """Stop the document re-embed worker pool if it was started."""
    runner = getattr(app.state, "document_batch_runner", None)
    if runner is not None:
        await runner.stop()


async def start_async_batches(
    app: FastAPI,
    *,
    knowledge_service: Any,
) -> None:
    """Start every async-operation batch worker (off the request path)."""
    await start_document_batch(app, knowledge_service=knowledge_service)


async def stop_async_batches(app: FastAPI) -> None:
    """Stop every async-operation batch worker (best-effort)."""
    await stop_document_batch(app)
