"""``/api/v1/knowledge/*`` — the human's side of the knowledge directory.

Create a collection, list them, walk one level of a collection, read a
document, submit material, upload a document, delete a document, trigger
curation (spec knowledge "Cover collection management on REST and the CLI").
Deleting a collection goes through the
kind-agnostic Resource route, since collection lifecycle is a Resource concern.

Two properties shape every handler below.

**Nothing here retrieves.** There is no ``search`` and no ``grep``: the layer
keeps no index and exposes no retrieval anywhere, so the person reads through
``tree``/``file`` and an agent reads the files itself at the paths its
delivered skill carries ("Expose exactly one knowledge tool", invariant 4). The
one input beside a tree on the web page narrows the names already on screen,
client-side ("Present a collection as one tree in the web UI").

**New knowledge arrives as material, never as a file write.** ``POST
/material`` and ``/upload`` both submit to the collection's inbox, and a pass
merges what is new into the documents ("Submit every entrance's input as
material"). A person edits a document in
their own editor, reached from the page's open-in-editor action; there is no
write-a-document route, because that edit is live on the very next read.

**No handler here takes an agent, and neither does the service.** A collection
carries no per-agent reach: every enabled one is served to every agent and to
the person who owns the vault, so there is nothing for a caller identity to
narrow. ``enabled`` is the whole of the gate, and it is the registry's, applied
the same way on every surface.

**A collection is addressed by uid; a file is addressed by path.** ``curate``
names the collection Resource's immutable uid, because a pass takes minutes and
must keep meaning the same collection across a rename (ADR
resource-identity-is-an-immutable-uid). The file routes below are the deliberate
exception: their ``path`` and ``collection`` arguments are *filesystem* paths,
whose first segment is the collection's directory — and a directory is named by
the label, not by an identity. Converting them would mean asking a caller for a
uid and then translating it straight back into the name the disk actually uses,
which is the extra vocabulary this change exists to remove. Each of them says so
where it takes the argument.

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``
— including ``UploadTooLarge`` ("Bound uploads and leave nothing behind on
failure"), which ``IngestService`` itself raises
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
from coffer.domain.knowledge.entry import ACTOR_AGENT, ACTOR_USER, Pending
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
    IngestedDocumentOut,
    MaterialIn,
    SubmissionOut,
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
    # A path — ``shopee`` or ``shopee/account`` — so its first segment is the
    # collection's directory NAME and stays one: this addresses a place on
    # disk, and the disk knows the label. A uid here would have to be
    # translated back into that same name before anything could be opened.
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
    # A filesystem path, name-led like ``tree``'s above — see the module
    # docstring on why the file family is not addressed by uid.
    path: str = Query(min_length=1),
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> FileOut:
    # The response carries both absolute paths ("Return absolute paths on
    # reads"), which is what the
    # page's open-in-editor and reveal actions hand back to the daemon.
    return _file_out(await svc.read(path))


@router.post("/material", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
async def submit_material(
    body: MaterialIn,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> SubmissionOut:
    submitted = await svc.submit(
        collection=body.collection,
        title=body.title,
        description=body.description,
        body=body.body,
        actor_kind=actor,
        actor=actor,
    )
    return SubmissionOut(
        status="written" if submitted.document is not None else "pending",
        collection=submitted.collection,
        title=submitted.title,
        path=submitted.document.path if submitted.document is not None else None,
    )


@router.delete("/file", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_file(
    # A filesystem path, name-led like ``tree``'s above.
    path: str = Query(min_length=1),
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> Response:
    # Any document ("Let only a person delete a document"): the collection is
    # the person's as much as
    # curation's. No agent-facing tool deletes.
    await svc.delete_document(path, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/collections/{uid}/curate", response_model=CurationOut)
async def curate(
    uid: str,
    body: CurationRequest | None = None,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> CurationOut:
    # The collection is named by its uid, and the pass resolves the row itself
    # — so this route does no lookup of its own and there is no window in which
    # the label it read and the label the pass reads disagree. An unknown uid
    # reaches the client as the same 404 every other route on this family gives,
    # raised where the row is actually needed.
    #
    # Two different guards, in this order on purpose.
    #
    # The registry claim is first, and it is about THIS collection: a pass
    # takes minutes and rewrites the collection's documents, so a second
    # request while one is in flight is refused (409 ``UPKEEP_ALREADY_RUNNING``)
    # rather than queued behind it ("Run one pass per collection at a time") —
    # the caller asked to start a pass,
    # and no pass is going to start. Claiming before the lock is what makes
    # that refusal immediate instead of a request that blocks until the first
    # pass finishes and then runs anyway. The claim is keyed on the **uid**,
    # which is what the background sweep claims too (``curate_worker``): two
    # writers over one directory only collide if both name it the same way, and
    # a label either of them read moments earlier is exactly what can differ.
    #
    # The vault-write lock is second, and it is about the whole vault: a pass
    # and a converge round both rewrite vault content, and an export caught
    # half-way through a rewrite is a torn snapshot git reads as a deliberate
    # change ("Never overlap curation with a sync round", spec vault-sync
    # "Never overlap a curation pass and a round").
    with UPKEEP_RUNS.guard(KIND_KNOWLEDGE, uid):
        async with vault_write_lock():
            result = await get_curation_runner()(
                svc,
                uid,
                # Omitted, the pass picks the oldest pending item itself
                # ("Run curation on a sweep and on demand"). One item per pass
                # either way: a trigger is never a corpus-wide rewrite ("Bound a
                # pass to eight writes").
                item=Pending(document=body.document)
                if body is not None and body.document
                else None,
                actor=actor,
            )
    # ``result`` already carries ``collection`` — as the collection's NAME, put
    # there by the pass, which resolved the row anyway. It is rendered to a
    # person, so the label is the right thing to report; the uid the caller
    # sent back is the one they already hold.
    return CurationOut(**result)


@router.post("/upload", response_model=IngestedDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),  # noqa: B008
    #: The collection's directory NAME, not its uid: this value is a path
    #: segment ``IngestService`` joins under the knowledge root, exactly like
    #: ``FileWrite.collection``.
    collection: str = Form(...),
    svc: IngestService = Depends(get_ingest_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> Any:
    data = await file.read()
    try:
        # A size ceiling and a refusal naming it both come from
        # ``IngestService.ingest`` itself — it raises ``UploadTooLarge``
        # (a ``CofferError``) before any conversion or write, so the
        # app-wide handler maps it without help from this route.
        doc = await svc.ingest(
            collection=collection,
            filename=file.filename or "upload",
            data=data,
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
