"""HTTP surface for the one ``memory`` kind (spec memory FR-036).

List partitions, notes and retirements, show one note with the entries behind
it, walk a partition's own directory and read a file out of it, run a sync, run
a distil pass, compose the session context, and install/inspect/remove delivery
for an agent. Partition deletion goes through the kind-agnostic Resource route
(``DELETE /api/v1/resources/{uid}``), exactly like knowledge's collections —
lifecycle is a Resource concern, not this kind's own.

**Everything here is addressed by uid.** A partition is ``{uid}``, and so is
the agent a delivery route installs into. The partition's *name* is still what
its directory under the memory root is called, so every handler reads it off
the row ``lookup.require_partition`` hands back — resolved once, from the
identity, rather than taken from the caller (ADR
resource-identity-is-an-immutable-uid). The only name a caller supplies is
``path``, inside an already-identified partition, which is a filesystem path
and nothing else.

Four route modules, one router. They are split by *subject*, not by size:
``partition_routes`` owns the list and the two passes that rewrite the tree,
``note_routes`` and ``file_routes`` are the two read families over one
partition, and ``delivery_routes`` is the only one whose subject is an agent
rather than a partition. Each declares the same prefix, tags and token
dependency — as ``surfaces/http/mcp/``'s modules do — and the aggregate below
carries none of its own, so no path moves by being mounted here.
"""

from fastapi import APIRouter

from coffer.surfaces.http.memory.delivery_routes import router as _delivery_router
from coffer.surfaces.http.memory.file_routes import router as _file_router
from coffer.surfaces.http.memory.note_routes import router as _note_router
from coffer.surfaces.http.memory.partition_routes import router as _partition_router

router = APIRouter()
router.include_router(_partition_router)
router.include_router(_note_router)
router.include_router(_file_router)
router.include_router(_delivery_router)

__all__ = ["router"]
