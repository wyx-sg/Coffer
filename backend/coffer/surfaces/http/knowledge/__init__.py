"""HTTP surface for the one ``knowledge`` kind."""

from coffer.surfaces.http.knowledge.history_routes import router as history_router
from coffer.surfaces.http.knowledge.routes import router as router

__all__ = ["history_router", "router"]
