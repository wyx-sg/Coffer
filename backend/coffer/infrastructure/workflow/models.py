"""SQLAlchemy ORM models for the four workflow execution tables.

``workflow_runs`` / ``workflow_events`` / ``workflow_node_attempts`` /
``workflow_approvals``, registered against the shared ``Base.metadata`` so
Alembic sees them in one place. The template a run came from has no table —
it is a row in ``resources`` like every other kind (FR-001), and what a run
executes is the snapshot frozen into ``template_snapshot`` at creation
(FR-010), never the resource as it stands today.

The status-ish columns are plain TEXT. Their vocabularies live in
``domain/workflow/run.py`` as enums; keeping the column a string means a value
the database has never heard of is a domain error rather than a schema
migration, which is what a closed set that is still being agreed wants.

Every child table's ``run_id`` is a real foreign key with ``ON DELETE
CASCADE`` — the engine runs with ``PRAGMA foreign_keys = ON``, so "deleting a
run cascades its events, attempts and approvals" is a schema fact rather than
four DELETE statements an application-layer caller has to remember.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    TIMESTAMP,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class WorkflowRunModel(Base):
    """One run: the work in flight, not a curated asset (FR-011).

    ``status``, ``current_stage_key``, ``current_node_key`` and
    ``tokens_spent`` are **projections** of ``workflow_events`` (FR-014). They
    are stored so a list query reads one row instead of folding a log, and
    they are rebuilt from the events on daemon start — which is why nothing
    here is the record of truth.

    There is no conversation column: a run has no conversation of its own, and
    every conversation belongs to one task's attempt (FR-030).
    """

    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    #: ``workflow:<name>``. Provenance only, and deliberately not a foreign
    #: key: deleting the template is allowed and leaves this dangling, the way
    #: a deleted source leaves an artifact's provenance intact.
    template_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    template_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    #: What this delivery is, in the developer's own words. A LABEL, like the
    #: title: neither is folded from the events, and both may be corrected
    #: after the fact (FR-070).
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Absolute path every node conversation runs in (FR-019).
    workdir: Mapped[str] = mapped_column(String, nullable=False)
    #: Only this machine's daemon advances the run; elsewhere it is read-only
    #: (FR-012).
    machine_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    current_stage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    current_node_key: Mapped[str | None] = mapped_column(String, nullable=True)
    #: Optimistic lock (FR-015). Bumped by exactly one writer, in one UPDATE.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tokens_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Mounted inputs (FR-032): a JSON list of references, never file contents.
    inputs: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_workflow_runs_status", "status"),
        Index("idx_workflow_runs_updated", "updated_at"),
    )


class WorkflowEventModel(Base):
    """One entry in a run's append-only log — its record of truth (FR-014).

    No row here is ever updated or deleted while its run exists. ``sequence``
    is monotonic within a run and unique with it, so a gap or a duplicate is a
    constraint violation rather than a silent reordering of history.
    """

    __tablename__ = "workflow_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    #: ``{actor_kind, actor_id, source_surface}`` — who caused this, and where
    #: they were standing when they did.
    actor: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    stage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    node_key: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_workflow_events_run_sequence"),
        Index("idx_workflow_events_run", "run_id", "sequence"),
    )


class WorkflowNodeAttemptModel(Base):
    """One attempt at one node.

    A retry never rewrites this row — it inserts ``attempt + 1`` (FR-022), so
    the earlier attempt's conversation, summary and failure reason stay
    readable. ``node_key`` carries the ``adhoc:<slug>`` form for an unplanned
    task (FR-028); ``conversation_id`` is NULL for a ``manual`` node, which
    records a human step and opens no conversation.
    """

    __tablename__ = "workflow_node_attempts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    stage_key: Mapped[str] = mapped_column(String, nullable=False)
    node_key: Mapped[str] = mapped_column(String, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    #: An ad-hoc task's own brief, written by the developer (FR-028).
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Who runs THIS attempt, on which model, thinking how hard (FR-071).
    #: NULL means "what the template said", and the template's NULL means
    #: "what the agent's own configuration projects" — one ladder, each rung
    #: deferring to the next rather than inventing a default of its own.
    agent: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    effort: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ``interrupted`` | ``agent_error`` | ``missing_artifact`` | ``attempt_ceiling``
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "run_id", "node_key", "attempt", name="uq_workflow_attempts_run_node_attempt"
        ),
        Index("idx_workflow_attempts_run", "run_id"),
    )


class WorkflowApprovalModel(Base):
    """One held decision — a gated tool call, or a node action that needs a yes.

    ``payload`` is the arguments **verbatim** (FR-033): a decision taken on a
    summary is not a decision on what executes. Credential material never
    reaches it, because credentials are injected by the gateway at dispatch and
    are not part of a call's arguments.
    """

    __tablename__ = "workflow_approvals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    attempt_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("workflow_node_attempts.id", ondelete="CASCADE"), nullable=True
    )
    #: ``tool_call`` | ``node_action``
    kind: Mapped[str] = mapped_column(String, nullable=False)
    #: The prefixed upstream tool name, for a ``tool_call``; NULL otherwise.
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_surface: Mapped[str | None] = mapped_column(String, nullable=True)
    #: What the developer said when deciding. A rejection's reason is the one
    #: thing the held node can act on, so it is kept rather than dropped.
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (Index("idx_workflow_approvals_run", "run_id", "status"),)
