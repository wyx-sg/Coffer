"""/api/v1/agents/{name}/native-memory routes (spec 004, FR-040/FR-041).

Read-only listing of a coding agent's OWN native per-project memory stores
(Claude Code's ``<config_dir>/projects/<slug>/memory``) plus a POST that ADOPTS
one such store into Coffer memory — parsing each fact file and writing it to the
project-scoped inbox, then running the internal organizer. Agents with no native
memory layout — and agents with no projects dir on disk — return an empty list;
a non-existent agent name returns 404 via the service's agent lookup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_agent_memory_import_service,
    get_agent_native_memory_service,
    get_native_import_batch_service,
    get_native_import_batch_service_optional,
)

if TYPE_CHECKING:
    from coffer.application.agent.native_import_batch import NativeImportBatchService

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
    dependencies=[Depends(require_token)],
)


# ---------- response schemas ----------


class NativeMemoryStoreOut(BaseModel):
    project: str
    path: str | None
    memory_dir: str
    item_count: int
    import_status: str | None = Field(
        default=None,
        description="Per-store import status: queued | running | error (in-flight only).",
    )


class NativeMemoryListOut(BaseModel):
    items: list[NativeMemoryStoreOut]


class ImportRequest(BaseModel):
    memory_dir: str
    # Codex's global store is shared by every row, so the chosen row's project
    # path selects which Task-Group blocks to import. Omitted/None for Claude
    # Code, where ``memory_dir`` alone identifies the project.
    project_path: str | None = None


class ImportResultOut(BaseModel):
    imported: int
    skipped: int
    store: str | None
    project_path: str | None
    organized: bool


class ImportBatchRequest(BaseModel):
    """Request body for POST /native-memory/import-batch.

    ``memory_dirs`` is the explicit set of stores to import. When omitted or
    empty the batch enqueues nothing (the UI always passes the selected rows)."""

    memory_dirs: list[str] | None = Field(
        default=None, description="Import these specific native-memory stores."
    )


class ImportBatchResponse(BaseModel):
    """Response for POST /native-memory/import-batch."""

    queued: int = Field(description="Newly enqueued stores.")
    total: int = Field(description="Candidate stores considered.")


class NativeImportStatus(BaseModel):
    """A single in-flight store's import state."""

    memory_dir: str
    state: str = Field(description="queued | running | error")
    message: str | None = Field(default=None, description="Error detail when state is error.")


class NativeImportStatusResponse(BaseModel):
    """Response for GET /native-memory/import-status.

    Only in-flight stores appear (queued / running / error); a store absent from
    the list is idle (or finished — see the list endpoint's ``import_status``)."""

    statuses: list[NativeImportStatus]


# ---------- routes ----------


@router.get("/{name}/native-memory", response_model=NativeMemoryListOut)
async def list_native_memory(
    name: str,
    svc: Any = Depends(get_agent_native_memory_service),  # noqa: B008
    batch: NativeImportBatchService | None = Depends(  # noqa: B008
        get_native_import_batch_service_optional
    ),
) -> NativeMemoryListOut:
    stores = await svc.list_stores(name)

    # Status overlay is best-effort: when the batch service is not wired (minimal
    # apps / tests) rows simply carry import_status=None.
    inflight = batch.inflight(name) if batch is not None else {}

    def _status(memory_dir: str) -> str | None:
        entry = inflight.get(memory_dir)
        return entry.state.value if entry is not None else None

    return NativeMemoryListOut(
        items=[
            NativeMemoryStoreOut(
                project=s.project_label,
                path=s.project_path,
                memory_dir=s.memory_dir,
                item_count=s.item_count,
                import_status=_status(s.memory_dir),
            )
            for s in stores
        ]
    )


@router.post("/{name}/native-memory/import", response_model=ImportResultOut)
async def import_native_memory(
    name: str,
    body: ImportRequest,
    svc: Any = Depends(get_agent_memory_import_service),  # noqa: B008
) -> ImportResultOut:
    """Adopt the native memory store at ``body.memory_dir`` into Coffer memory.

    Unknown agent → 404 (service's agent lookup). An unresolvable path or a
    non-git project yields a zero-import result, never an error — the inbox is
    never corrupted."""
    result = await svc.import_store(
        name=name, memory_dir=body.memory_dir, project_path=body.project_path
    )
    return ImportResultOut(
        imported=result.imported,
        skipped=result.skipped,
        store=result.store,
        project_path=result.project_path,
        organized=result.organized,
    )


@router.post(
    "/{name}/native-memory/import-batch",
    response_model=ImportBatchResponse,
    status_code=202,
)
async def import_native_memory_batch(
    name: str,
    body: ImportBatchRequest,
    batch: NativeImportBatchService = Depends(get_native_import_batch_service),  # noqa: B008
) -> ImportBatchResponse:
    """Enqueue native-memory adoption for many stores, off the request path (202).

    Each store's fact-writes run on the shared async worker pool so the request
    returns immediately. Stores already in flight are skipped. Poll
    ``import-status`` (and the list's ``import_status``) for progress."""
    result = batch.enqueue_imports(name, body.memory_dirs or [])
    return ImportBatchResponse(queued=result.queued, total=result.total)


@router.get(
    "/{name}/native-memory/import-status",
    response_model=NativeImportStatusResponse,
)
async def native_memory_import_status(
    name: str,
    batch: NativeImportBatchService = Depends(get_native_import_batch_service),  # noqa: B008
) -> NativeImportStatusResponse:
    """In-flight import state (queued / running / error) for an agent's stores."""
    inflight = batch.inflight(name)
    return NativeImportStatusResponse(
        statuses=[
            NativeImportStatus(
                memory_dir=memory_dir,
                state=entry.state.value,
                message=entry.message,
            )
            for memory_dir, entry in inflight.items()
        ]
    )
