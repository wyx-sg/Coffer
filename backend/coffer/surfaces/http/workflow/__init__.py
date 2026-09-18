"""HTTP surface for the one ``workflow`` kind (spec workflow FR-044).

Five routers over one prefix, split by what they act on rather than by size:
the run, one node, what the run reads, an approval, and the files a run
produced. They are exported together because ``surfaces.http.routing`` mounts
them together.
"""

from coffer.surfaces.http.workflow.routes_approvals import router as approvals_router
from coffer.surfaces.http.workflow.routes_artifacts import router as artifacts_router
from coffer.surfaces.http.workflow.routes_inputs import router as inputs_router
from coffer.surfaces.http.workflow.routes_nodes import router as nodes_router
from coffer.surfaces.http.workflow.routes_runs import router as runs_router

__all__ = [
    "approvals_router",
    "artifacts_router",
    "inputs_router",
    "nodes_router",
    "runs_router",
]
