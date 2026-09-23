"""The shapes the persistence layer hands back, described structurally.

Split out of :mod:`ports` for the file-size cap, on a real seam: everything
here describes DATA the engine reads, while ``ports`` describes BEHAVIOUR it
calls. Application code may not import the ORM, so a repository satisfies these
by having the attributes, not by inheriting anything.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

__all__ = [
    "ApprovalRow",
    "AttemptRow",
    "EventRow",
    "RunProjectionValue",
    "RunRow",
]


class RunRow(Protocol):
    id: str
    template_ref: str | None
    template_snapshot: dict[str, Any]
    title: str
    #: What the developer says this delivery is. A LABEL like the title:
    #: neither is folded from the events, and both may be corrected after the
    #: fact (spec workflow "Edit a run's title and description as labels").
    description: str | None
    workdir: str
    machine_id: str
    status: str
    current_stage_key: str | None
    current_node_key: str | None
    version: int
    tokens_spent: int
    #: ``list[Any]`` and not ``list[dict[str, Any]]``: ``list`` is invariant,
    #: so the narrower element type would stop the ORM row — whose JSON
    #: column is untyped — from satisfying this Protocol at all.
    inputs: list[Any]
    created_at: datetime
    #: Not optional: the row is stamped at creation and on every accepted
    #: command, so there is no moment at which it is absent. The wire contract
    #: still declares it nullable, which a value that is always sent satisfies.
    updated_at: datetime


class EventRow(Protocol):
    id: str
    run_id: str
    sequence: int
    event_type: str
    actor: dict[str, Any]
    stage_key: str | None
    node_key: str | None
    payload: dict[str, Any]
    created_at: datetime


class AttemptRow(Protocol):
    id: str
    run_id: str
    stage_key: str
    node_key: str
    attempt: int
    status: str
    conversation_id: str | None
    instructions: str | None
    #: Who runs this attempt, on which model, at which effort (spec
    #: workflow "Choose a task's agent, model and effort before it
    #: starts"). None defers to the template, whose None defers to the
    #: agent's own configuration.
    agent: str | None
    model: str | None
    effort: str | None
    summary: str | None
    failure_reason: str | None
    tokens: int
    started_at: datetime | None
    finished_at: datetime | None


class ApprovalRow(Protocol):
    id: str
    run_id: str
    attempt_id: str | None
    kind: str
    tool_name: str | None
    payload: dict[str, Any]
    status: str
    decided_by: str | None
    decided_surface: str | None
    comment: str | None
    expires_at: datetime
    created_at: datetime
    decided_at: datetime | None


class RunProjectionValue(Protocol):
    """The four projected columns, written together rather than patched.

    Satisfied by ``infrastructure.workflow.repository.RunProjection``.
    """

    status: str
    current_stage_key: str | None
    current_node_key: str | None
    tokens_spent: int
