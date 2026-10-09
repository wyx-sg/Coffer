"""``/api/v1/knowledge/*`` — the human's side of the knowledge directory.

Create a collection, list them, check one, walk one level of a collection,
read a file, upload a source, delete a file and fetch the prompt that hands a
tidy to the person's agent (spec knowledge
"Manage knowledge in the web UI and on the command line"). These routes
are the web UI's own: one the page does not call does not exist. Deleting a
collection goes through the kind-agnostic Resource route, since collection
lifecycle is a Resource concern.

Three properties shape every handler below.

**Nothing here retrieves.** There is no ``search`` and no ``grep``: the layer
keeps no index and exposes no retrieval anywhere, so the person reads through
``tree``/``file`` and an agent reads the files itself at the paths its
delivered skill carries ("Expose no knowledge tool", invariant 4).
A collection's hidden ``.inbox`` is not listed and not readable ("Hide
dot-prefixed entries except the inbox").

**New knowledge arrives as material; a person's edit is the editor's.**
``/upload`` submits material, which becomes a source under ``sources/``
("Promote submitted material at once"). There is no route that creates or saves
a document at a path: a person edits in their own editor, from the page's
open-in-editor action, live on the very next read ("Treat a direct file edit as
a complete change").

**No handler here takes an agent, and neither does the service.** A collection
carries no per-agent reach and no enabled switch: every one is served to every
agent and to the person who owns the vault ("Serve every collection to every
agent"), so there is nothing for a caller identity to narrow.

**A collection is addressed by uid; a file is addressed by path.** The
collection routes name the collection Resource's immutable uid (ADR
identity-is-the-uid-inside-the-file). The file routes below are the deliberate
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
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.tidy_handoff import all_tidy_prompt
from coffer.domain.knowledge.converter import EmptyConversion, UnsupportedDocument
from coffer.domain.knowledge.entry import ACTOR_AGENT, ACTOR_USER
from coffer.infrastructure.knowledge import paths
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.errors import error_response
from coffer.surfaces.http.handoff_schemas import HandoffOut
from coffer.surfaces.http.knowledge.dependencies import (
    get_ingest_service,
    get_knowledge_service,
)
from coffer.surfaces.http.knowledge.schemas import (
    CheckOut,
    CollectionCreate,
    CollectionListOut,
    CollectionOut,
    DirectoryOut,
    FileOut,
    FileSummaryOut,
    IngestedDocumentOut,
    TreeOut,
    check_out,
    collection_out,
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
    return CollectionListOut(collections=[collection_out(c) for c in found])


@router.post("/collections", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
async def create_collection(
    body: CollectionCreate,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> CollectionOut:
    created = await svc.create_collection(body.name, actor=actor, description=body.description)
    return collection_out(created)


@router.get("/collections/{uid}/check", response_model=CheckOut)
async def check_collection(
    uid: str,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> CheckOut:
    """One collection's mechanical findings, computed now from its files and
    fixed by nothing here ("Check a collection mechanically on every read")."""
    return check_out(await svc.check(uid))


@router.get("/tidy-handoff", response_model=HandoffOut)
async def tidy_all_handoff(
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> HandoffOut:
    """The prompt that hands tidying every collection to the person's agent."""
    entries = await svc.list_collections()
    return HandoffOut(prompt=all_tidy_prompt(str(paths.knowledge_root()), entries))


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


@router.delete("/file", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_file(
    # A filesystem path, name-led like ``tree``'s above.
    path: str = Query(min_length=1),
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> Response:
    # Any document ("Let only a person delete a document"): the collection is
    # the person's. No agent-facing tool deletes.
    await svc.delete_document(path, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
