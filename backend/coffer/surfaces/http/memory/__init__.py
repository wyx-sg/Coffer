"""HTTP routes for the memory kind."""

# Import for side effects: registers the Slice-7 lane read routes and the
# merge-scan/merge routes (FR-056/057) on ``router``.
from coffer.surfaces.http.memory import lane_routes as _lane_routes  # noqa: F401
from coffer.surfaces.http.memory import merge_routes as _merge_routes  # noqa: F401
from coffer.surfaces.http.memory.routes import router

__all__ = ["router"]
