"""``/api/v1/knowledge/*`` — the human's side of the knowledge directory.

Create a collection, list them, walk one level of a lane, read a file, write a
source, upload a document, delete a source, trigger curation (spec knowledge
FR-039). Deleting a collection goes through the kind-agnostic Resource route,
since collection lifecycle is a Resource concern.

Two properties shape every handler below.

**Nothing here retrieves.** There is no ``search`` and no ``grep``: the layer
keeps no index and exposes no retrieval anywhere, so the person reads through
``tree``/``file`` and an agent reads the files itself at the paths its
delivered skill carries (FR-033, invariant 4). The one input beside a tree on
the web page narrows the names already on screen, client-side (FR-040).

**Writing is split by lane.** ``PUT`` and ``DELETE`` reach ``sources/`` and
only ``sources/`` — ``topics/`` is curation's to write and no one else's
(FR-013, FR-021), so a request aiming at a topic path is refused by the
path layer rather than by a check each handler remembers to make.

**No handler here takes an agent, and neither does the service.** A collection
carries no per-agent reach: every enabled one is served to every agent and to
the person who owns the vault, so there is nothing for a caller identity to
narrow. ``enabled`` is the whole of the gate, and it is the registry's, applied
the same way on every surface.

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``
— including ``UploadTooLarge`` (FR-019), which ``IngestService`` itself raises
before doing any conversion or write. ``UnsupportedDocument`` is the one
exception ``upload`` maps by hand: it is raised by the converter registry, a
plain-Python layer below the domain, so it is not a ``CofferError``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile, status

from coffer.application.knowledge.ingest import IngestService
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.domain.knowledge.converter import EmptyConversion, UnsupportedDocument
from coffer.domain.knowledge.entry import ACTOR_AGENT, ACTOR_USER
from coffer.domain.knowledge.errors import UnsafeKnowledgePath
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.errors import error_response
from coffer.surfaces.http.knowledge.curation_state import get_curation_runner, vault_write_lock
from coffer.surfaces.http.knowledge.dependencies import (
    get_ingest_service,
    get_knowledge_service,
)
from coffer.surfaces.http.knowledge.schemas import (
    CollectionCreate,
    CollectionListOut,
    CollectionOut,
    CurationOut,
    CurationRequest,
    DirectoryOut,
    FileOut,
    FileSummaryOut,
    FileWrite,
    IngestedDocumentOut,
    TreeOut,
)

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
    # The lane is part of the path — ``shopee/sources`` or ``shopee/topics``.
    # The page asks twice, once per tree (FR-040), rather than this route
    # inventing a lane parameter the path already carries.
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
    # Reading is lane-agnostic on purpose: the page previews a topic document
    # exactly as it previews a source, and refuses to *edit* it instead
    # (FR-040). The response carries both absolute paths (FR-041).
    return _file_out(await svc.read(path))


@router.put("/file", response_model=FileOut)
async def write_file(
    body: FileWrite,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> FileOut:
    if (body.path is None) == (body.collection is None):
        raise UnsafeKnowledgePath(
            body.path or body.collection or "",
            "a write names exactly one of 'path' or 'collection'",
        )
    # ``write_source`` adds the ``sources/`` segment itself and, for a replace,
    # asserts the target is in that lane — a ``path`` under ``topics/`` raises
    # ``UnsafeKnowledgePath`` there and reaches the client as 400
    # ``KNOWLEDGE_PATH_UNSAFE``. That is the only guard this route needs: the
    # rule belongs to path construction, which is the one place it cannot be
    # forgotten (FR-006, FR-013).
    written = await svc.write_source(
        title=body.title,
        description=body.description,
        body=body.body,
        collection=body.collection,
        folder=body.folder,
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
    # A source only (FR-020). A topic document is derived and is deleted by
    # being retired in a pass, never from here — so this refuses a ``topics/``
    # path rather than offering a delete the next pass would undo.
    await svc.delete_source(path, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/collections/{name}/curate", response_model=CurationOut)
async def curate(
    name: str,
    body: CurationRequest | None = None,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> CurationOut:
    # Two different guards, in this order on purpose.
    #
    # The registry claim is first, and it is about THIS collection: a pass
    # takes minutes and rewrites the collection's topic documents, so a second
    # request while one is in flight is refused (409 ``UPKEEP_ALREADY_RUNNING``)
    # rather than queued behind it (FR-030) — the caller asked to start a pass,
    # and no pass is going to start. Claiming before the lock is what makes
    # that refusal immediate instead of a request that blocks until the first
    # pass finishes and then runs anyway.
    #
    # The vault-write lock is second, and it is about the whole vault: a pass
    # and a converge round both rewrite vault content, and an export caught
    # half-way through a rewrite is a torn snapshot git reads as a deliberate
    # change (FR-031, spec vault-sync "## Unattended rewriters").
    with UPKEEP_RUNS.guard(KIND_KNOWLEDGE, name):
        async with vault_write_lock():
            result = await get_curation_runner()(
                svc,
                name,
                # Omitted, the pass picks the oldest pending source itself
                # (FR-022). One source per pass either way: a trigger is never
                # a corpus-wide rewrite (FR-025).
                source_relpath=body.source if body is not None else None,
                actor=actor,
            )
    return CurationOut(**{"collection": name, **result})


@router.post("/upload", response_model=IngestedDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),  # noqa: B008
    collection: str = Form(...),
    #: A subdirectory inside the collection's ``sources/``, never the lane
    #: itself: an upload is a source like any other and cannot be aimed at
    #: ``topics/`` (FR-013, FR-016).
    folder: str | None = Form(default=None),
    svc: IngestService = Depends(get_ingest_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> Any:
    data = await file.read()
    try:
        # A size ceiling and a refusal naming it (FR-019) both come from
        # ``IngestService.ingest`` itself — it raises ``UploadTooLarge``
        # (a ``CofferError``) before any conversion or write, so the
        # app-wide handler maps it without help from this route.
        doc = await svc.ingest(
            collection=collection,
            filename=file.filename or "upload",
            data=data,
            folder=folder,
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
