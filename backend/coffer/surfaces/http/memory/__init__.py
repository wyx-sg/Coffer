"""HTTP routes for the memory kind."""

# Import for side effects: registers the Slice-7 lane read routes on ``router``.
from coffer.surfaces.http.memory import lane_routes as _lane_routes  # noqa: F401
from coffer.surfaces.http.memory.routes import router

__all__ = ["router"]
