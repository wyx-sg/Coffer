"""FastAPI dependency providers for the one ``workflow`` kind.

Same ``set_*`` / ``get_*`` singleton shape as ``surfaces.http.memory
.dependencies``, typed concretely: the composition root calls every ``set_*``
here once on startup, and the routes ask for the matching ``get_*``.

Three services rather than two: ``WorkflowInputsService`` joined when a run's
inputs became something the developer manages at any point in its life (spec
workflow "Add and remove inputs at any point in a run") rather than a field of
the creation body. Its four routes go through it exactly as the others do — the
guards, the storage of an uploaded file under the run's own directory ("Store
an uploaded input under the run's directory") and the deletion of its bytes are
all its answers, not this surface's.

The repositories appear beside the services on purpose. Three routes ask
questions no service answers — the event log (there is no ``list_events`` on
``WorkflowRunService``), the per-node attempt rows a run's detail is assembled
from, and this machine's id, which is what makes "you do not own this run"
("Advance a run only on the machine that owns it") say *which* machine does.
Each is a read-only port the engine already declares; none of them is a second
way to write.
"""

from __future__ import annotations

from coffer.application.workflow.approval_service import ApprovalService
from coffer.application.workflow.inputs_service import WorkflowInputsService
from coffer.application.workflow.node_service import WorkflowNodeService
from coffer.application.workflow.ports import (
    ArtifactStorePort,
    AttemptRepoPort,
    EventRepoPort,
    KnowledgeInputPort,
    MachineIdPort,
)
from coffer.application.workflow.run_service import WorkflowRunService

# --- services ---------------------------------------------------------------

_run_service: WorkflowRunService | None = None


def set_workflow_run_service(svc: WorkflowRunService) -> None:
    """Called by the composition root once on startup."""
    global _run_service
    _run_service = svc


def get_workflow_run_service() -> WorkflowRunService:
    """FastAPI Depends() target."""
    if _run_service is None:
        raise RuntimeError("workflow run service not initialised")
    return _run_service


_node_service: WorkflowNodeService | None = None


def set_workflow_node_service(svc: WorkflowNodeService) -> None:
    """Called by the composition root once on startup."""
    global _node_service
    _node_service = svc


def get_workflow_node_service() -> WorkflowNodeService:
    """FastAPI Depends() target."""
    if _node_service is None:
        raise RuntimeError("workflow node service not initialised")
    return _node_service


_approval_service: ApprovalService | None = None


def set_workflow_approval_service(svc: ApprovalService) -> None:
    """Called by the composition root once on startup."""
    global _approval_service
    _approval_service = svc


def get_workflow_approval_service() -> ApprovalService:
    """FastAPI Depends() target."""
    if _approval_service is None:
        raise RuntimeError("workflow approval service not initialised")
    return _approval_service


_inputs_service: WorkflowInputsService | None = None


def set_workflow_inputs_service(svc: WorkflowInputsService) -> None:
    """Called by the composition root once on startup."""
    global _inputs_service
    _inputs_service = svc


def get_workflow_inputs_service() -> WorkflowInputsService:
    """FastAPI Depends() target."""
    if _inputs_service is None:
        raise RuntimeError("workflow inputs service not initialised")
    return _inputs_service


# --- the reads that no service owns -----------------------------------------

_event_repo: EventRepoPort | None = None


def set_workflow_event_repo(repo: EventRepoPort) -> None:
    """Called by the composition root once on startup."""
    global _event_repo
    _event_repo = repo


def get_workflow_event_repo() -> EventRepoPort:
    """FastAPI Depends() target."""
    if _event_repo is None:
        raise RuntimeError("workflow event repository not initialised")
    return _event_repo


_attempt_repo: AttemptRepoPort | None = None


def set_workflow_attempt_repo(repo: AttemptRepoPort) -> None:
    """Called by the composition root once on startup."""
    global _attempt_repo
    _attempt_repo = repo


def get_workflow_attempt_repo() -> AttemptRepoPort:
    """FastAPI Depends() target."""
    if _attempt_repo is None:
        raise RuntimeError("workflow attempt repository not initialised")
    return _attempt_repo


_artifact_store: ArtifactStorePort | None = None


def set_workflow_artifact_store(store: ArtifactStorePort) -> None:
    """Called by the composition root once on startup."""
    global _artifact_store
    _artifact_store = store


def get_workflow_artifact_store() -> ArtifactStorePort:
    """FastAPI Depends() target."""
    if _artifact_store is None:
        raise RuntimeError("workflow artifact store not initialised")
    return _artifact_store


_machine: MachineIdPort | None = None


def set_workflow_machine_id(machine: MachineIdPort) -> None:
    """Called by the composition root once on startup."""
    global _machine
    _machine = machine


def get_workflow_machine_id() -> MachineIdPort:
    """FastAPI Depends() target."""
    if _machine is None:
        raise RuntimeError("workflow machine id not initialised")
    return _machine


# --- the seams to the other kinds -------------------------------------------

_knowledge_input: KnowledgeInputPort | None = None


def set_workflow_knowledge_input(port: KnowledgeInputPort) -> None:
    """Called by the composition root once on startup.

    ``create_collection`` is expected to be **idempotent**: promotion's own
    contract is "the collection to create or add to", so a second promotion
    into the same collection adds to it rather than being refused.
    """
    global _knowledge_input
    _knowledge_input = port


def get_workflow_knowledge_input() -> KnowledgeInputPort:
    """FastAPI Depends() target."""
    if _knowledge_input is None:
        raise RuntimeError("workflow knowledge input not initialised")
    return _knowledge_input
