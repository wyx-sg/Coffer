"""``/api/v1/memory/*`` — the human's side of the memory layer (spec memory
FR-036).

List partitions, notes and retirements, show one note with the entries behind
it, walk a partition's own directory and read a file out of it, run a sync, run
a distil pass, compose the session context, and install/inspect/remove delivery
for an agent. Partition deletion goes through the kind-agnostic Resource route
(``DELETE /api/v1/resources/memory/{name}``), exactly like knowledge's
collections — lifecycle is a Resource concern, not this kind's own.

**The file family is read-only, and that is the design.** Everything under
``~/.coffer/memory/`` is derived (FR-019): an edit would survive exactly until
the next aggregation pass, so offering one would be offering a lie. It does not
route through ``/api/v1/fs`` either — that family browses directories and
deliberately never serves file contents — so the shape here follows
``knowledge/routes.py``'s own ``tree``/``file`` pair instead, scoped to one
partition.

**Nothing here is filtered by who is asking, and neither is anything
elsewhere in this layer.** A partition carries no per-agent reach (FR-013):
every enabled partition is served to every agent, so ``POST /context`` composes the
same payload whoever fired it and ``coffer__recall`` — which this surface does
not expose at all (FR-034) — scans the same corpus for whoever calls it. The
route still takes an ``agent``, because ``record_fired`` has to name the agent
whose hook fired; that name identifies the caller for the audit log and
decides nothing about the content.

**No route here records an audit event.** That is a change from the organise
pass, which was a pure function and had to be audited at this boundary.
Aggregation and distil both record their own inside ``MemoryService``, with the
actor that asked for them, and delivery install/remove record theirs inside
``DeliveryService``. A second record written here would put two rows in the log
for one pass — and they would disagree about the actor the moment the scheduled
sweep ran the same method. Reads audit nothing.
"""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends, Query

from coffer.application.memory.context import DEFAULT_CEILING_TOKENS, compose_context
from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.application.resource_service import ResourceService
from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.domain.memory.delivery import DeliveryStatus
from coffer.domain.memory.note import Note
from coffer.domain.memory.retired import RetiredNote
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.memory import files as memory_files
from coffer.infrastructure.memory import paths as memory_paths
from coffer.infrastructure.memory import store as memory_store
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_resource_service
from coffer.surfaces.http.memory.dependencies import (
    get_memory_delivery_service,
    get_memory_service,
)
from coffer.surfaces.http.memory.distil_state import get_distil_runner
from coffer.surfaces.http.memory.schemas import (
    AggregationResultOut,
    ComposedContextOut,
    ContextQuery,
    DeliveryStatusListOut,
    DeliveryStatusOut,
    DistilResultOut,
    FileContentOut,
    FileNodeOut,
    FileTreeOut,
    NoteListOut,
    NoteOut,
    NoteSummaryOut,
    OriginOut,
    PartitionListOut,
    PartitionOut,
    RetiredListOut,
    RetiredNoteOut,
)

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)

_actor = get_actor


async def _require_partition(name: str, resources: ResourceService) -> None:
    """404 (``RESOURCE_NOT_FOUND``) for a partition no ``memory`` Resource
    names — the generic, already-mapped error, since inventing a memory-
    specific "no such partition" code would duplicate it for no reason."""
    await resources.get(ResourceRef(KIND_MEMORY, name))


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


def _abs_paths(root: pathlib.Path, relpath: str) -> tuple[str, str]:
    """An entry's absolute path and that of the folder holding it.

    Both travel on every node and every read because a browser cannot resolve
    a path on the user's own disk — the open-in-editor and reveal-in-file-
    manager actions hand these back to the daemon, which can (ADR
    ``daemon-proxies-os-file-actions``).
    """
    target = root if relpath == "" else root / relpath
    return str(target), str(target.parent)


def _node_out(node: memory_files.FileNode, root: pathlib.Path) -> FileNodeOut:
    abs_path, folder_abs_path = _abs_paths(root, node.path)
    return FileNodeOut(
        name=node.name,
        path=node.path,
        abs_path=abs_path,
        folder_abs_path=folder_abs_path,
        type=node.type,
        derived=node.derived,
        size=node.size,
        truncated=node.truncated,
        children=[_node_out(child, root) for child in node.children],
    )


def _content_out(content: memory_files.FileContent, root: pathlib.Path) -> FileContentOut:
    abs_path, folder_abs_path = _abs_paths(root, content.path)
    return FileContentOut(
        path=content.path,
        abs_path=abs_path,
        folder_abs_path=folder_abs_path,
        content=content.content,
        truncated=content.truncated,
        binary=content.binary,
        size=content.size,
    )


def _delivery_out(status: DeliveryStatus) -> DeliveryStatusOut:
    return DeliveryStatusOut(
        agent=status.agent,
        installed=status.installed,
        command=status.command,
        event=status.event,
    )


@router.get("/partitions", response_model=PartitionListOut)
async def list_partitions(
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> PartitionListOut:
    found = await svc.list_partitions()
    return PartitionListOut(
        partitions=[
            PartitionOut(
                name=p.name,
                repository_key=p.repository_key,
                repository_path=p.repository_path,
                note_count=p.note_count,
                unresolvable=p.unresolvable,
            )
            for p in found
        ]
    )


@router.get("/partitions/{name}/notes", response_model=NoteListOut)
async def list_notes(
    name: str,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> NoteListOut:
    """Every note in one partition, read from ``notes/`` at call time.

    A retired note is not filtered out of this list — it is not *in* it, because
    retirement takes the file out of that directory and records it in
    ``RETIRED.md`` (FR-025). Reading the directory rather than a cached value is
    what keeps that true here.
    """
    await _require_partition(name, resources)
    return NoteListOut(notes=[_note_summary(n) for n in await svc.list_notes(name)])


@router.get("/partitions/{name}/notes/{slug}", response_model=NoteOut)
async def get_note(
    name: str,
    slug: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> NoteOut:
    """One note, whole. ``NoteNotFound`` (404) propagates to the app-wide
    handler, like every other ``CofferError`` on this family."""
    await _require_partition(name, resources)
    return _note_out(memory_store.read_note(name, slug))


@router.get("/partitions/{name}/retired", response_model=RetiredListOut)
async def list_retired(
    name: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> RetiredListOut:
    """``RETIRED.md``, read back — newest first (FR-025).

    The store returns the records in the order they were written and refuses to
    sort them, because a caller appending one rewrites the whole file and a
    re-sort there would silently reorder a file a human reads. Appending means
    the file is oldest-first, so *newest first* on the wire is that order
    reversed — not a sort on ``retired_at``, which is a string a record from an
    older pass may not carry at all.
    """
    await _require_partition(name, resources)
    records = memory_store.read_retired(name)
    return RetiredListOut(retired=[_retired_out(r) for r in reversed(records)])


@router.get("/partitions/{name}/files", response_model=FileTreeOut)
async def list_partition_files(
    name: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> FileTreeOut:
    """The partition's own directory, as a read-only tree (FR-037)."""
    await _require_partition(name, resources)
    root = memory_paths.partition_dir(name)
    return FileTreeOut(root=_node_out(memory_files.build_tree(root), root))


@router.get("/partitions/{name}/files/content", response_model=FileContentOut)
async def read_partition_file(
    name: str,
    path: str = Query(min_length=1),
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> FileContentOut:
    """One file out of the partition's directory.

    ``UnsafeMemoryPath`` (400) and ``MemoryFileNotFound`` (404) both propagate
    to the app-wide handler in ``surfaces/http/errors.py``, which already maps
    every ``CofferError`` — the same way knowledge's own file read reports an
    escape or a miss, rather than each route inventing an ``HTTPException``.
    """
    await _require_partition(name, resources)
    root = memory_paths.partition_dir(name)
    return _content_out(memory_files.read_file(name, root, path), root)


@router.post("/sync", response_model=AggregationResultOut)
async def sync(
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> AggregationResultOut:
    """Run aggregation over every registered, enabled agent's native memory.

    The actor travels in so the ``memory_aggregated`` event the service records
    distinguishes this requested pass from the worker's scheduled one.
    """
    result = await svc.aggregate(actor=actor)
    return AggregationResultOut(
        partitions=list(result.partitions),
        entries_written=result.entries_written,
        sources_read=result.sources_read,
        sources_skipped=result.sources_skipped,
        failures=[f.path for f in result.failures],
    )


@router.post("/partitions/{name}/distil", response_model=DistilResultOut)
async def distil(
    name: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> DistilResultOut:
    """Turn one partition's raw entries into notes, and rewrite its index."""
    await _require_partition(name, resources)
    # One pass per partition at a time. The pass takes minutes and rewrites the
    # whole partition directory, so a second request while one is in flight is
    # refused (409 ``UPKEEP_ALREADY_RUNNING``) rather than started: two of them
    # are two writers racing, not one faster pass. The registry is also what
    # `GET /api/v1/upkeep/runs` reads, so a surface that mounts mid-pass can
    # show the button as already running instead of inviting the second click.
    with UPKEEP_RUNS.guard(KIND_MEMORY, name):
        result = await get_distil_runner()(name, actor=actor)
    return DistilResultOut(
        partition=result.partition,
        merged=result.merged,
        opened=result.opened,
        retired=result.retired,
        dropped=result.dropped,
        model_used=result.model_used,
    )


@router.post("/context", response_model=ComposedContextOut)
async def context(
    body: ContextQuery,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    delivery: DeliveryService = Depends(get_memory_delivery_service),  # noqa: B008
) -> ComposedContextOut:
    """Compose the session-start payload for one directory.

    The one route a real agent's own session reaches. ``body.agent`` names who
    fired and nothing more: it does not reach ``compose_context``, which has no
    caller identity to narrow by, and exists here for ``record_fired`` — the
    audited "this agent's hook fired" event. ``record_fired`` is what the
    installed hook sets; a management surface previewing the payload leaves it
    false so it never records a fire that did not happen (FR-033).
    """
    composed = await compose_context(
        svc,
        cwd=body.cwd,
        ceiling_tokens=body.ceiling_tokens or DEFAULT_CEILING_TOKENS,
    )
    if body.record_fired and body.agent:
        await delivery.record_fired(body.agent)
    return ComposedContextOut(
        text=composed.text,
        partition=composed.partition,
        notes_included=composed.notes_included,
        notes_omitted=composed.notes_omitted,
    )


@router.get("/delivery", response_model=DeliveryStatusListOut)
async def delivery_status(
    agent: str | None = Query(default=None),
    svc: DeliveryService = Depends(get_memory_delivery_service),  # noqa: B008
) -> DeliveryStatusListOut:
    statuses = await svc.status(agent)
    return DeliveryStatusListOut(delivery=[_delivery_out(s) for s in statuses])


@router.post("/delivery/{agent}/install", response_model=DeliveryStatusOut)
async def install_delivery(
    agent: str,
    svc: DeliveryService = Depends(get_memory_delivery_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> DeliveryStatusOut:
    return _delivery_out(await svc.install(agent, actor=actor))


@router.delete("/delivery/{agent}", response_model=DeliveryStatusOut)
async def remove_delivery(
    agent: str,
    svc: DeliveryService = Depends(get_memory_delivery_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> DeliveryStatusOut:
    return _delivery_out(await svc.remove(agent, actor=actor))
