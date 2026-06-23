"""HTTP routes for the knowledge_base kind.

The exported ``router`` aggregates the main KB routes with the async re-embed
routes. The re-embed router is included FIRST so its static
``/documents/status`` and ``/documents/reembed-batch`` paths win over the main
router's ``/documents/{document_id}`` path-parameter route.
"""

from fastapi import APIRouter

from coffer.surfaces.http.knowledge_base.embed_routes import router as _embed_router
from coffer.surfaces.http.knowledge_base.routes import router as _routes_router

router = APIRouter()
router.include_router(_embed_router)
router.include_router(_routes_router)

__all__ = ["router"]
