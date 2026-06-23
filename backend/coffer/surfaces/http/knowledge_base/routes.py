"""/api/v1/knowledge_bases/* routes (spec 006 redesign).

Domain errors (`KBNotFound`, `IngestRejected`, `ReconversionBlocked`, …) are
allowed to propagate: the app-wide handler in `surfaces/http/errors.py` maps
each `CofferError` to the standard `{error: {code, message, details}}` envelope
and the right status. Routes only translate when they need a kind-specific code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Response,
    UploadFile,
    status,
)

from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import IngestRejected, KBNotFound, ResourceNotFound
from coffer.domain.knowledge.document import KIND_KNOWLEDGE_BASE
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.resource import Resource, ResourceRef
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_kb_service, get_resource_service
from coffer.surfaces.http.knowledge_base.schemas import (
    DocumentDetailOut,
    DocumentEditRequest,
    DocumentListOut,
    DocumentOut,
    GrepRequest,
    GrepResponse,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListOut,
    KnowledgeBaseMetrics,
    KnowledgeBaseOut,
    ReindexResult,
    SearchRequest,
    SearchResponse,
    SourceCheckResponse,
)
from coffer.surfaces.http.knowledge_base.state import (
    get_kb_batch_service_optional,
)

if TYPE_CHECKING:
    from coffer.application.async_ops.registry import InflightEntry
    from coffer.application.knowledge_base.batch import KnowledgeBaseBatchService
    from coffer.domain.knowledge.document import Document
    from coffer.domain.knowledge.retrieval import RetrievalMode

router = APIRouter(
    prefix="/api/v1/knowledge_bases",
    tags=["knowledge_bases"],
    dependencies=[Depends(require_token)],
)

# Hard ceiling on a single upload, matching the `max_document_bytes` upper
# bound in `KnowledgeBaseConfig`. Checked before the body is buffered so an
# oversized upload is rejected without reading it all into memory; the
# per-KB limit (which may be smaller) is still enforced by the service.
_ABSOLUTE_MAX_DOC_BYTES = 100 * 1024 * 1024


def _actor(x_coffer_actor: str | None = Header(default=None)) -> str:
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


def _to_kb_out(r: Resource, *, document_count: int = 0) -> KnowledgeBaseOut:
    return KnowledgeBaseOut(
        ref=str(r.ref),
        kind=r.kind,
        name=r.name,
        description=r.description,
        config=KnowledgeBaseConfig.model_validate(r.config),
        enabled=r.enabled,
        document_count=document_count,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("", response_model=KnowledgeBaseListOut)
async def list_kbs(
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
) -> KnowledgeBaseListOut:
    resources = await svc.list(kind=KIND_KNOWLEDGE_BASE)
    out = []
    for r in resources:
        try:
            # Cheap indexed count only (KB14): the list output discards disk_bytes,
            # so skip ``metrics()``' per-KB ``du_bytes`` disk walk.
            count = await kb_svc.document_count(kb_name=r.name)
        except Exception:
            count = 0
        out.append(_to_kb_out(r, document_count=count))
    return KnowledgeBaseListOut(knowledge_bases=out)


@router.post("", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED)
async def create_kb(
    body: KnowledgeBaseCreateRequest,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> KnowledgeBaseOut:
    created = await svc.register(
        kind=KIND_KNOWLEDGE_BASE,
        name=body.name,
        config=body.config.model_dump(mode="json"),
        actor=actor,
        description=body.description,
    )
    return _to_kb_out(created)


@router.get("/{name}", response_model=KnowledgeBaseOut)
async def get_kb(
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> KnowledgeBaseOut:
    try:
        r = await svc.get(ResourceRef(KIND_KNOWLEDGE_BASE, name))
    except ResourceNotFound as exc:
        raise KBNotFound(name) from exc
    return _to_kb_out(r)


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
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
    batch: KnowledgeBaseBatchService | None = Depends(get_kb_batch_service_optional),  # noqa: B008
    actor: str = Depends(_actor),
) -> DocumentOut:
    # When the client provides Content-Length, ``file.size`` is set; reject
    # early without buffering. When it is missing (e.g. a chunked upload
    # crafted to bypass the early check — CODE22-009), stream-read in 64 KB
    # chunks with a running counter so an oversized body is aborted before
    # exhausting memory.
    if file.size is not None and file.size > _ABSOLUTE_MAX_DOC_BYTES:
        raise IngestRejected(
            "too_large",
            f"upload size {file.size} bytes exceeds the absolute maximum "
            f"{_ABSOLUTE_MAX_DOC_BYTES} bytes",
        )
    chunks: list[bytes] = []
    total = 0
    chunk_size = 64 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > _ABSOLUTE_MAX_DOC_BYTES:
            raise IngestRejected(
                "too_large",
                f"upload size exceeds the absolute maximum {_ABSOLUTE_MAX_DOC_BYTES} bytes",
            )
        chunks.append(chunk)
    raw = b"".join(chunks)
    filename = file.filename or "unnamed"
    doc = await kb_svc.ingest_bytes(
        kb_name=name,
        filename=filename,
        raw_bytes=raw,
        actor=actor,
        replace=replace,
        source_path=source_path,
    )
    counts = await kb_svc.chunk_counts(kb_name=name)
    path, folder_path = kb_svc.doc_paths(kb_name=name, document_id=doc.id)
    inflight = batch.inflight(name) if batch is not None else {}
    return DocumentOut.from_domain(
        doc,
        chunk_count=counts.get(doc.id, 0),
        path=path,
        folder_path=folder_path,
        embed_status=_embed_status(batch, doc, inflight),
    )


@router.get("/{name}/documents", response_model=DocumentListOut)
async def list_documents(
    name: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
    batch: KnowledgeBaseBatchService | None = Depends(get_kb_batch_service_optional),  # noqa: B008
) -> DocumentListOut:
    docs, total = await kb_svc.list_documents(kb_name=name, limit=limit, offset=offset, q=q)
    counts = await kb_svc.chunk_counts(kb_name=name)
    # Status overlay is best-effort: when the batch service is not wired (minimal
    # apps / tests) rows simply carry embed_status=None.
    inflight = batch.inflight(name) if batch is not None else {}
    out = []
    for d in docs:
        path, folder_path = kb_svc.doc_paths(kb_name=name, document_id=d.id)
        out.append(
            DocumentOut.from_domain(
                d,
                chunk_count=counts.get(d.id, 0),
                path=path,
                folder_path=folder_path,
                embed_status=_embed_status(batch, d, inflight),
            )
        )
    return DocumentListOut(documents=out, total=total)


@router.get("/{name}/documents/{document_id}", response_model=DocumentDetailOut)
async def get_document(
    name: str,
    document_id: str,
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
    batch: KnowledgeBaseBatchService | None = Depends(get_kb_batch_service_optional),  # noqa: B008
) -> DocumentDetailOut:
    doc, markdown = await kb_svc.get_document_text(kb_name=name, document_id=document_id)
    counts = await kb_svc.chunk_counts(kb_name=name)
    path, folder_path = kb_svc.doc_paths(kb_name=name, document_id=doc.id)
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
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> DocumentOut:
    doc = await kb_svc.edit_document(
        kb_name=name, document_id=document_id, new_markdown=body.markdown, actor=actor
    )
    counts = await kb_svc.chunk_counts(kb_name=name)
    path, folder_path = kb_svc.doc_paths(kb_name=name, document_id=doc.id)
    return DocumentOut.from_domain(
        doc, chunk_count=counts.get(doc.id, 0), path=path, folder_path=folder_path
    )


@router.post("/{name}/documents/{document_id}/reconvert", response_model=DocumentOut)
async def reconvert_document(
    name: str,
    document_id: str,
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> DocumentOut:
    doc = await kb_svc.reconvert_document(kb_name=name, document_id=document_id, actor=actor)
    counts = await kb_svc.chunk_counts(kb_name=name)
    path, folder_path = kb_svc.doc_paths(kb_name=name, document_id=doc.id)
    return DocumentOut.from_domain(
        doc, chunk_count=counts.get(doc.id, 0), path=path, folder_path=folder_path
    )


@router.post("/{name}/documents/{document_id}/update-source", response_model=DocumentOut)
async def update_document_source(
    name: str,
    document_id: str,
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> DocumentOut:
    doc = await kb_svc.update_from_source(kb_name=name, document_id=document_id, actor=actor)
    counts = await kb_svc.chunk_counts(kb_name=name)
    path, folder_path = kb_svc.doc_paths(kb_name=name, document_id=doc.id)
    return DocumentOut.from_domain(
        doc, chunk_count=counts.get(doc.id, 0), path=path, folder_path=folder_path
    )


@router.delete(
    "/{name}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_document(
    name: str,
    document_id: str,
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await kb_svc.delete_document(kb_name=name, document_id=document_id, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{name}/reindex", response_model=ReindexResult)
async def reindex(
    name: str,
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ReindexResult:
    stats = await kb_svc.reindex(kb_name=name, actor=actor)
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
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SourceCheckResponse:
    report = await kb_svc.check_sources(kb_name=name, actor=actor)
    return SourceCheckResponse.from_report(report)


@router.post("/{name}/search", response_model=SearchResponse)
async def search_kb(
    name: str,
    body: SearchRequest,
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
) -> SearchResponse:
    result = await kb_svc.search(kb_name=name, query=body.query, top_k=body.top_k, mode=None)
    return SearchResponse.from_result(result)


@router.post("/{name}/grep", response_model=GrepResponse)
async def grep_kb(
    name: str,
    body: GrepRequest,
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
) -> GrepResponse:
    result = await kb_svc.grep(kb_name=name, pattern=body.pattern, max_matches=body.max_matches)
    return GrepResponse.from_result(result)


@router.get("/{name}/metrics", response_model=KnowledgeBaseMetrics)
async def metrics(
    name: str,
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
) -> KnowledgeBaseMetrics:
    m = await kb_svc.metrics(kb_name=name)
    return KnowledgeBaseMetrics(
        document_count=cast(int, m["document_count"]),
        chunk_count=cast(int, m["chunk_count"]),
        documents_degraded=cast(int, m["documents_degraded"]),
        indexed_modes=cast("list[RetrievalMode]", m["enabled_modes"]),
        disk_bytes=cast(int, m["disk_bytes"]),
    )
