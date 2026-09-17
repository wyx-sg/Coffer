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
  enum IS the contract's list, so there is nothing to keep in step.

The converters that turn the engine's rows into these models are next door in
``converters``, one module rather than five route modules, so that every route
renders a row the same way. They take the structural row Protocols the engine
already declares, never an ORM class — and keeping them out of here is also what
keeps this file under the line ceiling.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from coffer.domain.workflow.run import NodeAction, RunInputKind, RunSignal

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class RunInput(BaseModel):
    """One mounted input — a knowledge collection, a file or a link (FR-032).

    ``size`` is bytes, and only an uploaded file has one: a collection's size is
    the collection's business and a link has none. It is on the same model in
    both directions because the contract has one ``RunInput`` — a client that
    sends one simply leaves it out, and the store answers with what it wrote.
    """

    kind: RunInputKind
    ref: str
    label: str | None = None
    size: int | None = None
    #: Where the run can reach it, relative to the run's working directory —
    #: set for a file and a repo, absent for a collection or a link.
    path: str | None = None
    #: What a ``link`` points at — ``confluence``, ``jira``, ``google_docs``
    #: … — or null when nothing is known beyond the address (FR-065). DERIVED
    #: on every read rather than stored, so a link mounted before a provider
    #: was recognised is recognised now, with no migration. Never sent by a
    #: client: `RunInputIn` does not carry it.
    provider: str | None = None
    #: How a repo was given to the run: ``worktree`` (its own checkout on its
    #: own branch) or ``link`` (the source directory itself, which is what
    #: happens when the path is not a git repository). A node is TOLD which,
    #: because implying isolation it does not have is the one thing this must
    #: never do.
    mount: str | None = None


class RunInputIn(BaseModel):
    """What a client may say when mounting an input.

    Narrower than :class:`RunInput` on purpose: ``size``, ``path`` and ``mount``
    are what the server made of the request, not things a caller gets to assert
    about its own upload.
    """

    kind: RunInputKind
    ref: str
    label: str | None = None


class RunCreateIn(BaseModel):
    """A template and a title, and nothing else (FR-011).

    Two fields that were here are gone. ``workdir`` went because Coffer makes
    and owns a working directory per run (FR-053) — it is reported on ``RunOut``
    and never asked for. ``inputs`` went because they are mounted through
    ``/runs/{run_id}/inputs`` at any point in the run's life (FR-050), and a
    creation body that also accepted them would be a second way to do the same
    thing, available for one moment only.
    """

    template: str
    title: str
    agent: str | None = None


class RunSignalIn(BaseModel):
    version: int
    signal: RunSignal
    reason: str | None = None


class NodeActionIn(BaseModel):
    version: int
    action: NodeAction
    #: Required for ``feedback``; the node service refuses an empty one, which
    #: is where that rule belongs — it is the same rule for the CLI.
    feedback: str | None = None
    waive_artifacts: bool = False


class AdhocTaskIn(BaseModel):
    version: int
    stage_key: str
    name: str
    instructions: str
    agent: str | None = None
    #: Overrides the run's working directory — how a task that touches a second
    #: repository is expressed.
    workdir: str | None = None


class PromotionIn(BaseModel):
    collection: str


class ApprovalDecisionIn(BaseModel):
    #: Narrowed to the two a person can make: ``expired`` and ``superseded``
    #: are outcomes the system reaches on its own, and a surface that accepted
    #: them could forge one.
    decision: Literal["approved", "rejected"]
    comment: str | None = None
    remember_tool_class: Literal["read", "write"] | None = None


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
    current_stage_key: str | None = None
    current_node_key: str | None = None
    tokens_spent: int = 0
    token_budget: int | None = None
    created_at: datetime
    updated_at: datetime | None = None


class RunListOut(BaseModel):
    items: list[RunOut]


class NodeAttemptOut(BaseModel):
    id: str
    node_key: str
    stage_key: str
    attempt: int
    status: str
    conversation_id: str | None = None
    summary: str | None = None
    failure_reason: str | None = None
    tokens: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class NodeOut(BaseModel):
    key: str
    name: str
    type: str
    skill: str | None = None
    approval: str = "never"
    status: str
    #: 0 until the node has been tried — an attempt number is a count of tries,
    #: and claiming 1 before the first one would make "never started" and
    #: "running its first attempt" the same number.
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
