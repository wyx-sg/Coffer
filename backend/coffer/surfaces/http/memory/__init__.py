"""HTTP surface for the one ``memory`` kind (spec memory "Manage memory in the
web UI and on the command line").

List partitions, notes and retirements, show one note with the entries behind
it, walk a partition's own directory and read a file out of it, run a sync (an
aggregation, then a distil pass over each partition with something to distil),
and answer a fire of the memory hook. Whether an agent carries the
delivery hook is managed with the agent's Coffer connection (spec agent-registry
"Connect an agent to Coffer in one action"), not here. Partition deletion goes
through the kind-agnostic Resource route (``DELETE /api/v1/resources/{uid}``),
exactly like knowledge's collections —
lifecycle is a Resource concern, not this kind's own.

**Everything here is addressed by uid.** A partition is ``{uid}``, and so is
the agent that fired the hook. The partition's *name* is still what
its directory under the memory root is called, so every handler reads it off
the row ``lookup.require_partition`` hands back — resolved once, from the
identity, rather than taken from the caller (ADR
identity-is-the-uid-inside-the-file). The only name a caller supplies is
``path``, inside an already-identified partition, which is a filesystem path
and nothing else.

Seven route modules, mounted in order. They are split by *subject*, not by size:
``partition_routes`` owns the list and the two passes that rewrite the tree,
``note_routes`` and ``file_routes`` are the two read families over one
partition, ``hook_routes`` (one fire of the memory hook) is the one whose
caller is an agent rather than a person,
``stats_routes`` the two delivery views of the Memory page,
``reading_routes`` when the agents' memory was last read, and
``sync_routes`` the memory sync into each agent's own memory (spec memory
"Manage memory sync in the web UI"). Each declares the
same prefix, tags and token dependency — as ``surfaces/http/mcp/``'s modules do.
"""

from fastapi import APIRouter

from coffer.surfaces.http.memory.file_routes import router as _file_router
from coffer.surfaces.http.memory.hook_routes import router as _hook_router
from coffer.surfaces.http.memory.note_routes import router as _note_router
from coffer.surfaces.http.memory.partition_routes import router as _partition_router
from coffer.surfaces.http.memory.reading_routes import router as _reading_router
from coffer.surfaces.http.memory.stats_routes import router as _stats_router
from coffer.surfaces.http.memory.sync_routes import router as _sync_router

routers: tuple[APIRouter, ...] = (
    _partition_router,
    _note_router,
    _file_router,
    _hook_router,
    _stats_router,
    _reading_router,
    _sync_router,
)

__all__ = ["routers"]
