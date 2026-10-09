"""HTTP surface for the memory sync (spec memory "Manage memory sync in the
web UI and on the command line").

One route module, ``sync_routes``, under ``/api/v1/memory/sync``.
"""

from fastapi import APIRouter

from coffer.surfaces.http.memory.sync_routes import router as _sync_router

routers: tuple[APIRouter, ...] = (_sync_router,)

__all__ = ["routers"]
