"""HTTP surface for the one ``knowledge`` kind."""

from coffer.surfaces.http.knowledge.change_routes import router as change_router
from coffer.surfaces.http.knowledge.routes import router as router

__all__ = ["change_router", "router"]
