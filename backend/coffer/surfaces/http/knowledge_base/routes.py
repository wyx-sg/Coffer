"""/api/v1/knowledge_bases/* routes.

Domain errors (`KBNotFound`, `IngestRejected`, …) are allowed to propagate:
the app-wide handler in `surfaces/http/errors.py` maps each `CofferError` to
the standard `{error: {code, message, details}}` envelope and the right
status. Routes only translate when they need a kind-specific code.
"""

from __future__ import annotations

from typing import Any

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
from coffer.domain.resource import Resource, ResourceRef
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_kb_service, get_resource_service
from coffer.surfaces.http.knowledge_base.schemas import (
    DocumentDetailOut,
    DocumentListOut,
    DocumentOut,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListOut,
    KnowledgeBaseMetrics,
    KnowledgeBaseOut,
    SearchHit,
    SearchRequest,
    SearchResponse,
)

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


def _to_kb_out(r: Resource) -> KnowledgeBaseOut:
    from coffer.domain.knowledge_base.config import KnowledgeBaseConfig

    return KnowledgeBaseOut(
        ref=str(r.ref),
        kind=r.kind,
        name=r.name,
        description=r.description,
        config=KnowledgeBaseConfig.model_validate(r.config),
        enabled=r.enabled,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("", response_model=KnowledgeBaseListOut)
async def list_kbs(
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> KnowledgeBaseListOut:
    resources = await svc.list(kind="knowledge_base")
    return KnowledgeBaseListOut(knowledge_bases=[_to_kb_out(r) for r in resources])


@router.post(
    "",
    response_model=KnowledgeBaseOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_kb(
    body: KnowledgeBaseCreateRequest,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> KnowledgeBaseOut:
    created = await svc.register(
        kind="knowledge_base",
        name=body.name,
        config=body.config.model_dump(),
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
        r = await svc.get(ResourceRef("knowledge_base", name))
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
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
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
    )
    return _doc_to_out(doc)


@router.get("/{name}/documents", response_model=DocumentListOut)
async def list_documents(
    name: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
) -> DocumentListOut:
    docs, total = await kb_svc.list_documents(kb_name=name, limit=limit, offset=offset)
    return DocumentListOut(documents=[_doc_to_out(d) for d in docs], total=total)


@router.get(
    "/{name}/documents/{document_id}",
    response_model=DocumentDetailOut,
)
async def get_document(
    name: str,
    document_id: str,
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
) -> DocumentDetailOut:
    doc, text = await kb_svc.get_document_text(kb_name=name, document_id=document_id)
    return DocumentDetailOut(**_doc_to_out(doc).model_dump(), text=text)


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


@router.post("/{name}/search", response_model=SearchResponse)
async def search_kb(
    name: str,
    body: SearchRequest,
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
) -> SearchResponse:
    hits = await kb_svc.search(kb_name=name, query=body.query, top_k=body.top_k)
    return SearchResponse(
        hits=[
            SearchHit(
                text=h.text,
                document_id=h.document_id,
                filename=h.filename,
                score=h.score,
                position=h.position,
            )
            for h in hits
        ]
    )


@router.get("/{name}/metrics", response_model=KnowledgeBaseMetrics)
async def metrics(
    name: str,
    kb_svc: KnowledgeBaseService = Depends(get_kb_service),  # noqa: B008
) -> KnowledgeBaseMetrics:
    count, disk = await kb_svc.metrics(kb_name=name)
    return KnowledgeBaseMetrics(document_count=count, disk_bytes=disk)


def _doc_to_out(d: Any) -> DocumentOut:
    return DocumentOut(
        id=d.id,
        kb_name=d.kb_name,
        filename=d.filename,
        extension=d.extension,
        size_bytes=d.size_bytes,
        sha256=d.sha256,
        chunk_count=d.chunk_count,
        ingested_at=d.ingested_at,
    )
