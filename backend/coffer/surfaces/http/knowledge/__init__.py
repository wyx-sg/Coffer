"""HTTP routes for the one ``knowledge`` kind.

The exported ``router`` aggregates the whole scope tree. The re-embed router is
included FIRST so its static ``/documents/status`` and
``/documents/reembed-batch`` paths win over the main router's
``/documents/{document_id}`` path-parameter route.

The sibling modules attach their routes to the SAME ``routes.router`` by import
side effect — one router, one path tree, several files only because of the
project's file-size ceiling.
"""

from fastapi import APIRouter

# Import for side effects: each module registers its routes on ``routes.router``.
from coffer.surfaces.http.knowledge import document_routes as _document_routes  # noqa: F401
from coffer.surfaces.http.knowledge import entry_routes as _entry_routes  # noqa: F401
from coffer.surfaces.http.knowledge.embed_routes import router as _embed_router
from coffer.surfaces.http.knowledge.routes import router as _routes_router

router = APIRouter()
router.include_router(_embed_router)
router.include_router(_routes_router)

__all__ = ["router"]
