"""Async KB re-embed routes (the non-blocking ingest-tail slice).

The slow part of KB ingest is convert+chunk+embed; a document indexed
keyword-only because the embedding provider was unavailable carries
``embed_pending=True``. These two endpoints move the embed-retry of EXISTING
documents off the request path: a 202 batch enqueue and a status poll backed by
the shared :class:`AsyncOpRunner`. Kept in their own router (registered before
``routes.py``'s ``/documents/{document_id}`` so the static ``/documents/status``
path is not captured as a document id) so ``routes.py`` stays under its
file-size budget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, status

from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.knowledge_base.schemas import (
    DocumentEmbedStatus,
    DocumentStatusResponse,
    ReembedBatchRequest,
    ReembedBatchResponse,
)
from coffer.surfaces.http.knowledge_base.state import get_kb_batch_service

if TYPE_CHECKING:
    from coffer.application.knowledge_base.batch import KnowledgeBaseBatchService

router = APIRouter(
    prefix="/api/v1/knowledge_bases",
    tags=["knowledge_bases"],
    dependencies=[Depends(require_token)],
)


@router.get("/{name}/documents/status", response_model=DocumentStatusResponse)
async def documents_status(
    name: str,
    batch: KnowledgeBaseBatchService = Depends(get_kb_batch_service),  # noqa: B008
) -> DocumentStatusResponse:
    """In-flight re-embed state (queued / running / error) for a KB's documents."""
    inflight = batch.inflight(name)
    return DocumentStatusResponse(
        statuses=[
            DocumentEmbedStatus(
                document_id=document_id,
                state=entry.state.value,
                message=entry.message,
            )
            for document_id, entry in inflight.items()
        ]
    )


@router.post(
    "/{name}/documents/reembed-batch",
    response_model=ReembedBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reembed_batch(
    name: str,
    body: ReembedBatchRequest,
    batch: KnowledgeBaseBatchService = Depends(get_kb_batch_service),  # noqa: B008
) -> ReembedBatchResponse:
    """Enqueue per-document re-embed off the request path (202).

    Either an explicit ``document_ids`` set, or ``all=true`` to re-embed every
    document still pending an embed. Already-embedded documents are skipped. Poll
    ``documents/status`` (and the list's ``embed_status``) for progress."""
    if body.all:
        result = await batch.enqueue_all(name)
    else:
        result = await batch.enqueue_documents(name, body.document_ids or [])
    return ReembedBatchResponse(queued=result.queued, skipped=result.skipped, total=result.total)
