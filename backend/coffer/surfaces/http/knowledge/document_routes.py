"""``/api/v1/knowledge/{scope}/documents*`` — the ingestion half of a scope.

Registered on the shared ``knowledge`` router (imported from ``routes``) so both
halves of a scope live under one path tree. Domain errors (``DocumentNotFound``,
``IngestRejected``, ``ReconversionBlocked``, …) propagate to the app-wide handler
in ``surfaces/http/errors.py``; routes only translate when they need a
kind-specific code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import (
    Depends,
    File,
    Form,
    Header,
    Query,
    Response,
    UploadFile,
    status,
)

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.errors import IngestRejected
from coffer.surfaces.http.dependencies import get_knowledge_service
from coffer.surfaces.http.knowledge.batch_state import get_batch_service_optional
from coffer.surfaces.http.knowledge.document_schemas import (
    DocumentDetailOut,
    DocumentEditRequest,
    DocumentListOut,
    DocumentOut,
    GrepRequest,
    GrepResponse,
    ReindexResult,
    SearchRequest,
    SearchResponse,
    SourceCheckResponse,
)
from coffer.surfaces.http.knowledge.routes import _ensure_auto, router

if TYPE_CHECKING:
    from coffer.application.async_ops.registry import InflightEntry
    from coffer.application.knowledge.batch import KnowledgeBaseBatchService
    from coffer.domain.knowledge.document import Document

# Hard ceiling on a single upload, matching the ``max_document_bytes`` upper
# bound in ``KnowledgeConfig``. Checked before the body is buffered so an
# oversized upload is rejected without reading it all into memory; the
# per-scope limit (which may be smaller) is still enforced by the service.
_ABSOLUTE_MAX_DOC_BYTES = 100 * 1024 * 1024


def _doc_actor(x_coffer_actor: str | None = Header(default=None)) -> str:
    """Document writes carry a free-form actor string (``api`` when absent)."""
    return x_coffer_actor or "api"


def _embed_status(
    batch: KnowledgeBaseBatchService | None,
    doc: Document,
    inflight: dict[str, InflightEntry],
) -> str | None:
    """Per-document embed status: in-flight (queued/running/error) overlaid on the
    derived done/embedding. ``None`` when the batch service is not wired."""
    if batch is None:
        return None
    entry = inflight.get(doc.id)
    if entry is not None:
        return str(entry.state.value)
    return batch.derived_status(doc)


async def _out(
    svc: KnowledgeService,
    scope: str,
    doc: Document,
    *,
    batch: KnowledgeBaseBatchService | None = None,
    inflight: dict[str, InflightEntry] | None = None,
    counts: dict[str, int] | None = None,
) -> DocumentOut:
    """One document's wire row, with its chunk count + on-disk paths."""
    if counts is None:
        counts = await svc.chunk_counts(scope_name=scope)
    path, folder_path = svc.doc_paths(scope_name=scope, document_id=doc.id)
    return DocumentOut.from_domain(
        doc,
        chunk_count=counts.get(doc.id, 0),
        path=path,
        folder_path=folder_path,
        embed_status=_embed_status(batch, doc, inflight or {}),
    )


async def _read_upload(file: UploadFile) -> bytes:
    """Buffer an upload, refusing an oversized body before it exhausts memory.

    When the client provides Content-Length, ``file.size`` is set and the reject
    is immediate. When it is missing (e.g. a chunked upload crafted to bypass
    the early check) the stream is read in 64 KB chunks against a running
    counter."""
    if file.size is not None and file.size > _ABSOLUTE_MAX_DOC_BYTES:
        raise IngestRejected(
            "too_large",
            f"upload size {file.size} bytes exceeds the absolute maximum "
            f"{_ABSOLUTE_MAX_DOC_BYTES} bytes",
        )
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > _ABSOLUTE_MAX_DOC_BYTES:
            raise IngestRejected(
                "too_large",
                f"upload size exceeds the absolute maximum {_ABSOLUTE_MAX_DOC_BYTES} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


# --- document writes --------------------------------------------------------


@router.post(
    "/{name}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_document(
    name: str,
    file: UploadFile = File(...),  # noqa: B008
    replace: bool = Form(default=False),
    # The external original's absolute path, supplied only by trusted clients
    # (CLI / desktop picker) so source-update detection can later re-hash it.
    # The web surface merely forwards whatever the client sends; it never
    # auto-derives a server path (an untrusted upload leaves this unset).
    source_path: str | None = Form(default=None),
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    batch: KnowledgeBaseBatchService | None = Depends(get_batch_service_optional),  # noqa: B008
    actor: str = Depends(_doc_actor),
) -> DocumentOut:
    """Ingest one uploaded file into a scope (any format → Markdown on disk)."""
    await _ensure_auto(k_svc, name)
    raw = await _read_upload(file)
    doc = await k_svc.ingest_bytes(
        scope_name=name,
        filename=file.filename or "unnamed",
        raw_bytes=raw,
        actor=actor,
        replace=replace,
        source_path=source_path,
    )
    inflight = batch.inflight(name) if batch is not None else {}
    return await _out(k_svc, name, doc, batch=batch, inflight=inflight)


@router.get("/{name}/documents", response_model=DocumentListOut)
async def list_documents(
    name: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    batch: KnowledgeBaseBatchService | None = Depends(get_batch_service_optional),  # noqa: B008
) -> DocumentListOut:
    await _ensure_auto(k_svc, name)
    docs, total = await k_svc.list_documents(scope_name=name, limit=limit, offset=offset, q=q)
    counts = await k_svc.chunk_counts(scope_name=name)
    # Status overlay is best-effort: when the batch service is not wired
    # (minimal apps / tests) rows simply carry embed_status=None.
    inflight = batch.inflight(name) if batch is not None else {}
    out = [await _out(k_svc, name, d, batch=batch, inflight=inflight, counts=counts) for d in docs]
    return DocumentListOut(documents=out, total=total)


@router.get("/{name}/documents/{document_id}", response_model=DocumentDetailOut)
async def get_document(
    name: str,
    document_id: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    batch: KnowledgeBaseBatchService | None = Depends(get_batch_service_optional),  # noqa: B008
) -> DocumentDetailOut:
    doc, markdown = await k_svc.get_document_text(scope_name=name, document_id=document_id)
    counts = await k_svc.chunk_counts(scope_name=name)
    path, folder_path = k_svc.doc_paths(scope_name=name, document_id=doc.id)
    inflight = batch.inflight(name) if batch is not None else {}
    return DocumentDetailOut.from_domain_with_body(
        doc,
        markdown,
        chunk_count=counts.get(doc.id, 0),
        path=path,
        folder_path=folder_path,
        embed_status=_embed_status(batch, doc, inflight),
    )


@router.put("/{name}/documents/{document_id}", response_model=DocumentOut)
async def edit_document(
    name: str,
    document_id: str,
    body: DocumentEditRequest,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_doc_actor),
) -> DocumentOut:
    doc = await k_svc.edit_document(
        scope_name=name, document_id=document_id, new_markdown=body.markdown, actor=actor
    )
    return await _out(k_svc, name, doc)


@router.post("/{name}/documents/{document_id}/reconvert", response_model=DocumentOut)
async def reconvert_document(
    name: str,
    document_id: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_doc_actor),
) -> DocumentOut:
    """Re-run conversion from the raw original (blocked once hand-edited)."""
    doc = await k_svc.reconvert_document(scope_name=name, document_id=document_id, actor=actor)
    return await _out(k_svc, name, doc)


@router.post("/{name}/documents/{document_id}/update-source", response_model=DocumentOut)
async def update_document_source(
    name: str,
    document_id: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_doc_actor),
) -> DocumentOut:
    """Re-ingest a document from its tracked external original, in place."""
    doc = await k_svc.update_from_source(scope_name=name, document_id=document_id, actor=actor)
    return await _out(k_svc, name, doc)


@router.delete(
    "/{name}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_document(
    name: str,
    document_id: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_doc_actor),
) -> Response:
    await k_svc.delete_document(scope_name=name, document_id=document_id, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- maintenance + retrieval ------------------------------------------------


@router.post("/{name}/reindex", response_model=ReindexResult)
async def reindex(
    name: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_doc_actor),
) -> ReindexResult:
    """Rescan the scope's ingested files and rebuild the index from disk."""
    await _ensure_auto(k_svc, name)
    stats = await k_svc.reindex_documents(scope_name=name, actor=actor)
    reindexed = stats.get("reindexed", 0)
    skipped = stats.get("skipped", 0)
    return ReindexResult(
        documents_scanned=reindexed + skipped,
        documents_reindexed=reindexed,
        documents_skipped=skipped,
        documents_removed=stats.get("removed", 0),
        documents_degraded=stats.get("degraded", 0),
    )


@router.post("/{name}/check-sources", response_model=SourceCheckResponse)
async def check_sources(
    name: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_doc_actor),
) -> SourceCheckResponse:
    """Re-hash each path-tracked document's external original to classify it."""
    await _ensure_auto(k_svc, name)
    return SourceCheckResponse.from_report(await k_svc.check_sources(scope_name=name, actor=actor))


@router.post("/{name}/search", response_model=SearchResponse)
async def search(
    name: str,
    body: SearchRequest,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> SearchResponse:
    """Passage search over a scope's documents (mode stays internal)."""
    await _ensure_auto(k_svc, name)
    result = await k_svc.search(scope_name=name, query=body.query, top_k=body.top_k, mode=None)
    return SearchResponse.from_result(result)


@router.post("/{name}/grep", response_model=GrepResponse)
async def grep(
    name: str,
    body: GrepRequest,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> GrepResponse:
    """Literal/regex grep over every markdown file in a scope."""
    await _ensure_auto(k_svc, name)
    result = await k_svc.grep(scope_name=name, pattern=body.pattern, max_matches=body.max_matches)
    return GrepResponse.from_result(result)
