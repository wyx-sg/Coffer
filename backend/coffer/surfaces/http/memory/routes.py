"""``/api/v1/memory/*`` — the human's side of the memory layer (spec memory
FR-061).

List partitions and facts, show one fact with its origins and conflicts, walk
a partition's own directory and read a file out of it, run a sync, run an
organise pass, compose the session context, and install/inspect/remove
delivery for an agent. Partition deletion goes through the kind-agnostic
Resource route (``DELETE /api/v1/resources/memory/{name}``), exactly like
knowledge's collections — lifecycle is a Resource concern, not this kind's
own.

**The file family is read-only, and that is the design.** Everything under
``~/.coffer/memory/`` is derived (FR-023): an edit would survive exactly until
the next aggregation pass, so offering one would be offering a lie. It does
not route through ``/api/v1/fs`` either — that family browses directories and
deliberately never serves file contents — so the shape here follows
``knowledge/routes.py``'s own ``tree``/``file`` pair instead, scoped to one
partition.

Like knowledge's REST surface, these routes are the *owner's* view and are
therefore unscoped: ``list_facts``/``list_partitions`` are called with no
``agent``, so nothing here is filtered by a Resource's scope. Scope IS
enforced on the one route a real agent's own session actually reaches —
``POST /context`` composes ``MemoryService.visible_partitions(agent)``
underneath (``application.memory.context.compose_context``) — and on
``coffer__recall`` (FR-052), which this surface does not expose at all: L2
is MCP-only (FR-060).

Every organise pass is audited here (FR-063): ``organise_partition`` is a
pure layer with no ``AuditService`` of its own (by design — see
``memory_wiring.py``'s module docstring), so the record is made at this
boundary instead. Aggregation and delivery install/remove already audit
themselves inside their own services. Reads audit nothing.
"""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi import APIRouter, Depends, Query

from coffer.application.audit_service import AuditService
from coffer.application.memory.context import DEFAULT_BUDGET_TOKENS, compose_context
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.application.resource_service import ResourceService
from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.fact import Fact
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.memory import files as memory_files
from coffer.infrastructure.memory import paths as memory_paths
from coffer.infrastructure.memory.store import FactNotFound
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_actor,
    get_audit_service,
    get_resource_service,
)
from coffer.surfaces.http.memory.dependencies import (
    get_memory_delivery_service,
    get_memory_service,
)
from coffer.surfaces.http.memory.organise_state import get_organise_runner
from coffer.surfaces.http.memory.schemas import (
    AggregationResultOut,
    ComposedContextOut,
    ContextQuery,
    DeliveryStatusListOut,
    DeliveryStatusOut,
    FactListOut,
    FactOut,
    FactSummaryOut,
    FileContentOut,
    FileNodeOut,
    FileTreeOut,
    OrganiseResultOut,
    OriginOut,
    PartitionListOut,
    PartitionOut,
)

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)

_EVENT_ORGANISED = AuditEventType.MEMORY_ORGANISED.value

_actor = get_actor


async def _require_partition(name: str, resources: ResourceService) -> None:
    """404 (``RESOURCE_NOT_FOUND``) for a partition no ``memory`` Resource
    names — the generic, already-mapped error, since inventing a memory-
    specific "no such partition" code would duplicate it for no reason."""
    await resources.get(ResourceRef(KIND_MEMORY, name))


def _fact_summary(fact: Fact) -> FactSummaryOut:
    return FactSummaryOut(
        key=fact.key,
        slug=fact.slug,
        partition=fact.partition,
        title=fact.title,
        description=fact.description,
        type=fact.type,
        status=fact.status,
        superseded_by=fact.superseded_by,
        conflicts_with=list(fact.conflicts_with),
    )


def _fact_out(fact: Fact) -> FactOut:
    summary = _fact_summary(fact)
    return FactOut(
        **summary.model_dump(),
        body=fact.body,
        origins=[
            OriginOut(
                agent=o.agent,
                native_path=o.native_path,
                anchor=o.anchor,
                captured_at=o.captured_at,
                source_written_at=o.source_written_at,
            )
            for o in fact.origins
        ],
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


def _delivery_out(s: Any) -> DeliveryStatusOut:
    return DeliveryStatusOut(
        agent=s.agent,
        installed=s.installed,
        command=s.command,
        event=s.event,
    )


@router.get("/partitions", response_model=PartitionListOut)
async def list_partitions(
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> PartitionListOut:
    found = await svc.list_partitions()
    return PartitionListOut(
        partitions=[
            PartitionOut(name=p.name, project_root=p.project_root, fact_count=p.fact_count)
            for p in found
        ]
    )


@router.get("/partitions/{name}/facts", response_model=FactListOut)
async def list_facts(
    name: str,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> FactListOut:
    await _require_partition(name, resources)
    return FactListOut(facts=[_fact_summary(f) for f in await svc.list_facts(name)])


@router.get("/partitions/{name}/facts/{slug}", response_model=FactOut)
async def get_fact(
    name: str,
    slug: str,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> FactOut:
    await _require_partition(name, resources)
    facts = await svc.list_facts(name)
    fact = next((f for f in facts if f.slug == slug), None)
    if fact is None:
        raise FactNotFound(name, slug)
    return _fact_out(fact)


@router.get("/partitions/{name}/files", response_model=FileTreeOut)
async def list_partition_files(
    name: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> FileTreeOut:
    """The partition's own directory, as a read-only tree (FR-062)."""
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
    result = await svc.aggregate(actor=actor)
    return AggregationResultOut(
        partitions=list(result.partitions),
        facts_written=result.facts_written,
        sources_read=result.sources_read,
        sources_skipped=result.sources_skipped,
        failures=[f.path for f in result.failures],
    )


@router.post("/partitions/{name}/organise", response_model=OrganiseResultOut)
async def organise(
    name: str,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> OrganiseResultOut:
    await _require_partition(name, resources)
    # One pass per partition at a time. The pass takes minutes and rewrites the
    # whole partition directory, so a second request while one is in flight is
    # refused (409 ``UPKEEP_ALREADY_RUNNING``) rather than started: two of them
    # are two writers racing, not one faster pass. The registry is also what
    # `GET /api/v1/upkeep/runs` reads, so a surface that mounts mid-pass can
    # show the button as already running instead of inviting the second click.
    with UPKEEP_RUNS.guard(KIND_MEMORY, name):
        result = await get_organise_runner()(name)
    await audit.record(
        _EVENT_ORGANISED,
        ref=ResourceRef(KIND_MEMORY, name),
        actor=actor,
        details={
            "merged": result.merged,
            "superseded": result.superseded,
            "conflicts": result.conflicts,
            "model_used": result.model_used,
        },
    )
    return OrganiseResultOut(
        partition=result.partition,
        merged=result.merged,
        superseded=result.superseded,
        conflicts=result.conflicts,
        model_used=result.model_used,
    )


@router.post("/context", response_model=ComposedContextOut)
async def context(
    body: ContextQuery,
    svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    delivery: Any = Depends(get_memory_delivery_service),  # noqa: B008
) -> ComposedContextOut:
    composed = await compose_context(
        svc,
        agent=body.agent,
        cwd=body.cwd,
        budget_tokens=body.budget_tokens or DEFAULT_BUDGET_TOKENS,
    )
    if body.record_fired and body.agent:
        await delivery.record_fired(body.agent)
    return ComposedContextOut(
        text=composed.text,
        partition=composed.partition,
        facts_included=composed.facts_included,
        facts_omitted=composed.facts_omitted,
        layers=list(composed.layers),
    )


@router.get("/delivery", response_model=DeliveryStatusListOut)
async def delivery_status(
    agent: str | None = Query(default=None),
    svc: Any = Depends(get_memory_delivery_service),  # noqa: B008
) -> DeliveryStatusListOut:
    statuses = await svc.status(agent)
    return DeliveryStatusListOut(delivery=[_delivery_out(s) for s in statuses])


@router.post("/delivery/{agent}/install", response_model=DeliveryStatusOut)
async def install_delivery(
    agent: str,
    svc: Any = Depends(get_memory_delivery_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> DeliveryStatusOut:
    return _delivery_out(await svc.install(agent, actor=actor))


@router.delete("/delivery/{agent}", response_model=DeliveryStatusOut)
async def remove_delivery(
    agent: str,
    svc: Any = Depends(get_memory_delivery_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> DeliveryStatusOut:
    return _delivery_out(await svc.remove(agent, actor=actor))
