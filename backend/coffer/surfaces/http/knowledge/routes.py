"""``/api/v1/knowledge/*`` — the human's side of the knowledge directory.

Create a collection, list them, walk one level of the catalogue, read a file,
write one, delete one, grep, tidy — plus ``search`` and document ``upload``
(spec knowledge FR-034).
Deleting a collection goes through the kind-agnostic Resource route, since
collection lifecycle is a Resource concern.

These routes are the *user's* surface and therefore unscoped: per-agent
authorization (FR-009) governs what an agent sees through the MCP tools, not
what the person who owns the vault sees in their own UI. ``search`` and
``upload`` follow the same rule — neither takes an ``agent``.

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``
— including ``UploadTooLarge`` (FR-026), which ``IngestService`` itself raises
before doing any conversion or write. ``UnsupportedDocument`` is the one
exception ``upload`` maps by hand: it is raised by the converter registry, a
plain-Python layer below the domain, so it is not a ``CofferError``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile, status

from coffer.application.knowledge.ingest import IngestService
from coffer.application.knowledge.search import SearchService
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.domain.knowledge.converter import EmptyConversion, UnsupportedDocument
from coffer.domain.knowledge.entry import ACTOR_AGENT, ACTOR_USER
from coffer.domain.knowledge.errors import UnsafeKnowledgePath
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.errors import error_response
from coffer.surfaces.http.knowledge.dependencies import (
    get_ingest_service,
    get_knowledge_service,
    get_search_service,
)
from coffer.surfaces.http.knowledge.schemas import (
    CollectionCreate,
    CollectionListOut,
    CollectionOut,
    DirectoryOut,
    FileOut,
    FileSummaryOut,
    FileWrite,
    GrepMatchOut,
    GrepOut,
    IngestedDocumentOut,
    SearchHitOut,
    SearchLineOut,
    SearchOut,
    SearchRequest,
    TidyOut,
    TreeOut,
)
from coffer.surfaces.http.knowledge.tidy_state import get_tidy_runner, vault_write_lock

router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(require_token)],
)

#: Neither ``UnsupportedDocument`` nor ``EmptyConversion`` is a
#: ``CofferError`` (the first never was one), so neither has a code of its own
#: in ``surfaces/http/errors.py``'s table. Both reuse the still-mapped
#: ``INGEST_REJECTED`` (400) rather than inventing new ones — the family has
#: exactly one code for "this upload is refused", ``details.reason`` says which
#: refusal, and ``details.doc_type`` says which type.
_INGEST_REJECTED = "INGEST_REJECTED"


def _actor_kind(x_coffer_actor: str | None = Header(default=None)) -> str:
    return ACTOR_AGENT if x_coffer_actor == ACTOR_AGENT else ACTOR_USER


def _file_out(file: object) -> FileOut:
    return FileOut.model_validate(file, from_attributes=True)


@router.get("/collections", response_model=CollectionListOut)
async def list_collections(
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> CollectionListOut:
    found = await svc.list_collections()
    return CollectionListOut(
        collections=[CollectionOut.model_validate(c, from_attributes=True) for c in found]
    )


@router.post("/collections", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
async def create_collection(
    body: CollectionCreate,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> CollectionOut:
    created = await svc.create_collection(body.name, actor=actor, description=body.description)
    return CollectionOut.model_validate(created, from_attributes=True)


@router.get("/tree", response_model=TreeOut)
async def read_tree(
    path: str = Query(min_length=1),
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> TreeOut:
    level = await svc.list_level(path)
    return TreeOut(
        path=level.path,
        directories=[
            DirectoryOut.model_validate(d, from_attributes=True) for d in level.directories
        ],
        files=[FileSummaryOut.model_validate(f, from_attributes=True) for f in level.files],
    )


@router.get("/file", response_model=FileOut)
async def read_file(
    path: str = Query(min_length=1),
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> FileOut:
    return _file_out(await svc.read(path))


@router.put("/file", response_model=FileOut)
async def write_file(
    body: FileWrite,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> FileOut:
    if (body.path is None) == (body.directory is None):
        raise UnsafeKnowledgePath(
            body.path or body.directory or "",
            "a write names exactly one of 'path' or 'directory'",
        )
    written = await svc.write(
        title=body.title,
        description=body.description,
        body=body.body,
        directory=body.directory,
        relpath=body.path,
        actor_kind=actor,
        actor=actor,
    )
    return _file_out(written)


@router.delete("/file", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_file(
    path: str = Query(min_length=1),
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> Response:
    await svc.delete(path, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/grep", response_model=GrepOut)
async def grep(
    pattern: str = Query(min_length=1),
    collection: str | None = Query(default=None),
    max_matches: int = Query(default=200, ge=1, le=500),
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> GrepOut:
    outcome = await svc.grep(pattern, collection=collection, max_matches=max_matches)
    return GrepOut(
        matches=[GrepMatchOut.model_validate(m, from_attributes=True) for m in outcome.matches],
        truncated=outcome.truncated,
    )


@router.post("/collections/{name}/tidy", response_model=TidyOut)
async def tidy(
    name: str,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> TidyOut:
    # Two different guards, in this order on purpose.
    #
    # The registry claim is first, and it is about THIS collection: a pass
    # takes minutes and rewrites the collection's files, so a second request
    # while one is in flight is refused (409 ``UPKEEP_ALREADY_RUNNING``)
    # rather than queued behind it — the caller asked to start a pass, and no
    # pass is going to start. Claiming before the lock is what makes that
    # refusal immediate instead of a request that blocks until the first pass
    # finishes and then runs anyway.
    #
    # The vault-write lock is second, and it is about the whole vault: a pass
    # and a converge round both rewrite vault content, and an export caught
    # half-way through a rewrite is a torn snapshot git reads as a deliberate
    # change (spec vault-sync "## Unattended rewriters").
    with UPKEEP_RUNS.guard(KIND_KNOWLEDGE, name):
        async with vault_write_lock():
            result = await get_tidy_runner()(svc, name, actor=actor)
    return TidyOut(**{"collection": name, **result})


@router.post("/search", response_model=SearchOut)
async def search(
    body: SearchRequest,
    svc: SearchService = Depends(get_search_service),  # noqa: B008
) -> SearchOut:
    outcome = await svc.search(body.query, collection=body.collection)
    return SearchOut(
        results=[
            SearchHitOut(
                path=hit.path,
                title=hit.title,
                description=hit.description,
                lines=[
                    SearchLineOut(line_number=number, line=line) for number, line in hit.excerpt
                ],
            )
            for hit in outcome.hits
        ],
    )


@router.post("/upload", response_model=IngestedDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),  # noqa: B008
    collection: str = Form(...),
    directory: str | None = Form(default=None),
    svc: IngestService = Depends(get_ingest_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> Any:
    data = await file.read()
    try:
        # A size ceiling and a refusal naming it (FR-026) both come from
        # ``IngestService.ingest`` itself — it raises ``UploadTooLarge``
        # (a ``CofferError``) before any conversion or write, so the
        # app-wide handler maps it without help from this route.
        doc = await svc.ingest(
            collection=collection,
            filename=file.filename or "upload",
            data=data,
            directory=directory,
            actor=actor,
        )
    except UnsupportedDocument as exc:
        return error_response(
            _INGEST_REJECTED,
            f"unsupported document type: {exc.doc_type!r}",
            {"reason": "unsupported_type", "doc_type": exc.doc_type},
        )
    except EmptyConversion as exc:
        # A PDF gets its own reason because the cause is knowable and the fix
        # is actionable ("run OCR"); any other format that converts to nothing
        # falls back to the family's generic message.
        reason = "scanned_pdf" if exc.doc_type == "pdf" else "empty_conversion"
        return error_response(
            _INGEST_REJECTED,
            f"no text could be extracted from this {exc.doc_type!r} document",
            {"reason": reason, "doc_type": exc.doc_type},
        )
    return IngestedDocumentOut.model_validate(doc, from_attributes=True)
