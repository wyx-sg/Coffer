"""``/api/v1/memory/partitions/{uid}/notes`` and ``/retired``.

What a distil pass produced, read back: the index of live notes, one note
whole, and the record of what has been retired. All three are reads of files on
disk at call time — this layer keeps no cache of them, which is what makes a
note that left ``notes/`` disappear from the list rather than have to be
filtered out of it ("Record retirements so they stick").
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.memory.service import MemoryService
from coffer.application.resource_service import ResourceService
from coffer.domain.memory.note import Note
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory import store as memory_store
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.memory.dependencies import get_memory_service
from coffer.surfaces.http.memory.lookup import require_partition
from coffer.surfaces.http.memory.schemas import (
    NoteListOut,
    NoteOut,
    NoteSummaryOut,
    OriginOut,
    RetiredListOut,
    RetiredNoteOut,
)

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)


def _note_summary(note: Note) -> NoteSummaryOut:
    return NoteSummaryOut(
        key=note.key,
        slug=note.slug,
        partition=note.partition,
        title=note.title,
        description=note.description,
        type=note.type,
        search_terms=list(note.search_terms),
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _note_out(note: Note) -> NoteOut:
    return NoteOut(
        **_note_summary(note).model_dump(),
        body=note.body,
        origins=[
            OriginOut(
                agent=o.agent,
                native_path=o.native_path,
                anchor=o.anchor,
                captured_at=o.captured_at,
                source_written_at=o.source_written_at,
            )
            for o in note.origins
        ],
    )


def _retired_out(record: RetiredNote) -> RetiredNoteOut:
    """One retirement on the wire, minus ``entry_ids``.

    Those are the exclusion list the next distil pass matches on, not something
    a reader of the record needs; leaving them off keeps ``RETIRED.md``'s wire
    shape the account it is meant to be rather than an index of raw entries.
    """
    return RetiredNoteOut(
        slug=record.slug,
        title=record.title,
        reason=record.reason,
        replaced_by=record.replaced_by,
        retired_at=record.retired_at,
    )


@router.get("/partitions/{uid}/notes", response_model=NoteListOut)
async def list_notes(
    uid: str,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> NoteListOut:
    """Every note in one partition, read from ``notes/`` at call time.

    A retired note is not filtered out of this list — it is not *in* it, because
    retirement takes the file out of that directory and records it in
    ``RETIRED.md``. Reading the directory rather than a cached value is
    what keeps that true here.
    """
    partition = await require_partition(uid, resources)
    return NoteListOut(notes=[_note_summary(n) for n in await svc.list_notes(partition.name)])


@router.get("/partitions/{uid}/notes/{slug}", response_model=NoteOut)
async def get_note(
    uid: str,
    slug: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> NoteOut:
    """One note, whole. ``NoteNotFound`` (404) propagates to the app-wide
    handler, like every other ``CofferError`` on this family.

    ``slug`` stays a name because it IS the note's file name under ``notes/``,
    and a note is not a Resource — it has no identity of its own to address it
    by.
    """
    partition = await require_partition(uid, resources)
    return _note_out(memory_store.read_note(partition.name, slug))


@router.get("/partitions/{uid}/retired", response_model=RetiredListOut)
async def list_retired(
    uid: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> RetiredListOut:
    """``RETIRED.md``, read back — newest first.

    The store returns the records in the order they were written and refuses to
    sort them, because a caller appending one rewrites the whole file and a
    re-sort there would silently reorder a file a human reads. Appending means
    the file is oldest-first, so *newest first* on the wire is that order
    reversed — not a sort on ``retired_at``, which is a string a record from an
    older pass may not carry at all.
    """
    partition = await require_partition(uid, resources)
    records = memory_store.read_retired(partition.name)
    return RetiredListOut(retired=[_retired_out(r) for r in reversed(records)])
