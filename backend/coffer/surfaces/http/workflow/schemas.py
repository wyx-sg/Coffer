"""Wire models for ``/api/v1/workflow/*`` — hand-written against the contract.

Every model here is named exactly as ``specs/workflow/contracts/api.openapi
.yaml`` names it, field for field, because ``make verify-contract`` compares
the generated schema against that document in both directions: a name that
drifts is a component the contract declares and the app does not serve.

Two deliberate typing choices:

* **Statuses come out as ``str``.** The yaml narrows them with ``enum``; the
  vocabulary lives in ``domain.workflow.run``'s ``StrEnum``s, and
  ``tests/contract/test_workflow_openapi.py`` pins the yaml's lists against
  those enums. Re-declaring the values here would make a third copy.
* **Commands come in as the domain enum** — validated at the boundary, and the
  enum IS the contract's list, so there is nothing to keep in step. Those live
  next door in ``schemas_in`` and are re-exported here.

The converters that turn the engine's rows into these models are next door in
``converters``, one module rather than five route modules, so that every route
renders a row the same way. They take the structural row Protocols the engine
already declares, never an ORM class — and keeping them out of here is also what
keeps this file under the line ceiling.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from coffer.surfaces.http.workflow.schemas_in import (
    AdhocTaskIn,
    ApprovalDecisionIn,
    AssignmentIn,
    NodeActionIn,
    PromotionIn,
    RunCreateIn,
    RunInput,
    RunInputIn,
    RunLabelIn,
    RunNoteEditIn,
    RunNoteIn,
    RunSignalIn,
    SayIn,
)

#: Re-exported so every caller keeps one import for the whole wire vocabulary;
#: which half a model lives in is this package's business, not a route's.
__all__ = [
    "AdhocTaskIn",
    "ApprovalDecisionIn",
    "ApprovalListOut",
    "ApprovalOut",
    "ArtifactListOut",
    "ArtifactOut",
    "AssignmentIn",
    "EventActorOut",
    "EventListOut",
    "EventOut",
    "InputListOut",
    "NodeActionIn",
    "NodeAttemptOut",
    "NodeOut",
    "PromotionIn",
    "PromotionOut",
    "RunCreateIn",
    "RunDetailOut",
    "RunFileOut",
    "RunInput",
    "RunInputIn",
    "RunLabelIn",
    "RunListOut",
    "RunNoteEditIn",
    "RunNoteIn",
    "RunOut",
    "RunSignalIn",
    "SayIn",
    "StageOut",
]

# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class RunOut(BaseModel):
    id: str
    title: str
    template_ref: str
    status: str
    version: int
    workdir: str
    machine_id: str
    #: False when another machine advances this run (FR-012).
    owned_here: bool
    #: What the developer called this delivery, and what it is for. Labels,
    #: not projection: neither is folded from the events (FR-070).
    description: str | None = None
    current_stage_key: str | None = None
    #: What the developer CALLED that stage, read from the run's own frozen
    #: snapshot. A key is an identity the engine reads no meaning from and the
    #: developer never typed (FR-003, FR-060); null when the snapshot no longer
    #: parses or no longer has that stage.
    current_stage_name: str | None = None
    current_node_key: str | None = None
    #: What this run has spent so far. A readout, not a cap: a run is bounded
    #: by each task's own attempt ceiling (FR-026), not by a number of tokens.
    tokens_spent: int = 0
    created_at: datetime
    updated_at: datetime | None = None


class RunListOut(BaseModel):
    items: list[RunOut]


class NodeAttemptOut(BaseModel):
    id: str
    node_key: str
    stage_key: str
    attempt: int
    #: What THIS attempt was told to run on (FR-071). Null defers to the task's
    #: own answer, whose null defers to the agent's configuration.
    agent: str | None = None
    model: str | None = None
    effort: str | None = None
    status: str
    conversation_id: str | None = None
    summary: str | None = None
    failure_reason: str | None = None
    #: What the developer wrote for THIS attempt (FR-068) — the brief it opens
    #: with, on top of whatever the template said. Readable so a task that has
    #: not started can show what it has been told it will do.
    instructions: str | None = None
    tokens: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class NodeOut(BaseModel):
    key: str
    name: str
    type: str
    skill: str | None = None
    #: What the WORKFLOW says runs this task. Null means the run's own default;
    #: an attempt may override it either way (FR-071).
    agent: str | None = None
    approval: str = "never"
    status: str
    #: How many times this node has been TRIED. 0 until the first turn starts:
    #: an attempt ROW exists before its turn does — a retry opens the next one
    #: pending, and so does briefing a task that has not started (FR-068) — and
    #: neither is a try. Claiming 1 before the first one would make "never
    #: started" and "running its first attempt" the same number.
    attempt: int
    adhoc: bool = False
    #: What this node accepts right now (FR-021), computed from
    #: ``domain.workflow.transitions.allowed_node_actions``. The web UI renders
    #: exactly these, so a wrong value here is a wrong button there.
    allowed_actions: list[str] = Field(default_factory=list)
    #: The latest attempt's conversation — what "open this task" navigates to.
    #: Duplicated out of ``latest`` on purpose: a task IS its conversation now
    #: (FR-030), so the one identifier a client always needs should not be
    #: reachable only by digging through the attempt that happens to carry it.
    #: ``None`` until the node has been started.
    conversation_id: str | None = None
    latest: NodeAttemptOut | None = None


class StageOut(BaseModel):
    key: str
    name: str
    optional: bool = False
    nodes: list[NodeOut]


class InputListOut(BaseModel):
    items: list[RunInput]


class RunDetailOut(BaseModel):
    run: RunOut
    stages: list[StageOut]
    inputs: list[RunInput] = Field(default_factory=list)


class EventActorOut(BaseModel):
    """Who an event is attributed to (``workflow_events.actor``) — inline in
    the yaml, named here because a Pydantic field needs a type."""

    actor_kind: str
    actor_id: str | None = None
    source_surface: str


class EventOut(BaseModel):
    id: str
    sequence: int
    event_type: str
    actor: EventActorOut
    stage_key: str | None = None
    node_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EventListOut(BaseModel):
    items: list[EventOut]


class ArtifactOut(BaseModel):
    name: str
    node_key: str
    attempt: int
    #: Relative to the run's artifact root; an absolute path would leak this
    #: machine's layout into a document that travels into an agent's context.
    path: str
    size: int
    modified_at: datetime


class RunFileOut(BaseModel):
    """One file under a run's directory, for the UI's preview (FR-064)."""

    path: str = Field(description="Path relative to the run's own directory.")
    name: str
    size: int = Field(description="The file's real size, not the size of `text`.")
    text: str | None = Field(
        default=None,
        description="The file's contents, or null when the bytes are not UTF-8 text.",
    )
    truncated: bool = Field(
        default=False, description="True when `text` is the head of a longer file."
    )


class ArtifactListOut(BaseModel):
    catalogue: str
    items: list[ArtifactOut]


class PromotionOut(BaseModel):
    collection: str
    copied: int


class ApprovalOut(BaseModel):
    id: str
    run_id: str
    attempt_id: str | None = None
    kind: str
    tool_name: str | None = None
    status: str
    #: The exact arguments that will execute — verbatim, never a summary
    #: (FR-033). Required, with no default: an approval whose payload was
    #: omitted would be a decision about nothing.
    payload: dict[str, Any]
    decided_by: str | None = None
    decided_surface: str | None = None
    comment: str | None = None
    expires_at: datetime
    created_at: datetime
    decided_at: datetime | None = None


class ApprovalListOut(BaseModel):
    items: list[ApprovalOut]
