"""Pydantic schemas matching specs/007-memory/contracts/transcripts.openapi.yaml.

Hand-written to mirror the OpenAPI wire contract (wire-contract rule).
All models use full type hints with ``from __future__ import annotations``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TranscriptSessionSummary(BaseModel):
    """Summary of a single transcript session (list view)."""

    session_id: str
    title: str | None = None
    project_path: str | None = None
    message_count: int
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    source_path: str
    distill_status: str | None = Field(
        default=None,
        description="Per-session distill status: done | never | queued | running | error.",
    )


class TranscriptSessionListResponse(BaseModel):
    """Response for GET /api/v1/agents/{name}/transcripts.

    ``sessions`` is one page (most-recent first); ``total`` is the count of all
    sessions on disk so the UI can show "showing N of total".
    """

    sessions: list[TranscriptSessionSummary]
    total: int
    limit: int
    offset: int


class DistillRequest(BaseModel):
    """Request body for POST /api/v1/agents/{name}/transcripts/distill."""

    session_id: str | None = Field(default=None, description="Distil a specific session.")
    project_path: str | None = Field(
        default=None,
        description="Distil the most-recent session for this project path.",
    )
    dry_run: bool = Field(
        default=False,
        description="If true, return insights without writing journal entries.",
    )


class InsightOut(BaseModel):
    """A single distilled insight returned by the distill endpoint."""

    name: str
    description: str
    body: str


class DistillResponse(BaseModel):
    """Response for POST /api/v1/agents/{name}/transcripts/distill."""

    insights: list[InsightOut]
    journal_entries: list[str]


class DistillBatchRequest(BaseModel):
    """Request body for POST /api/v1/agents/{name}/transcripts/distill-batch.

    Either distil an explicit ``session_ids`` set, or set ``all`` to distil every
    session matching the current list filters (select-all across pages).
    """

    session_ids: list[str] | None = Field(
        default=None, description="Distil these specific sessions."
    )
    all: bool = Field(
        default=False,
        description="Distil every session matching the filters below (select-all).",
    )
    q: str | None = Field(default=None, description="Search filter (with all=true).")
    project: str | None = Field(default=None, description="Project filter (with all=true).")
    started_after: datetime | None = Field(default=None)
    started_before: datetime | None = Field(default=None)


class DistillBatchResponse(BaseModel):
    """Response for POST /api/v1/agents/{name}/transcripts/distill-batch."""

    queued: int = Field(description="Newly enqueued sessions.")
    skipped: int = Field(description="Skipped — already distilled at current content.")
    total: int = Field(description="Candidate sessions considered.")


class DistillSessionStatus(BaseModel):
    """A single in-flight session's distill state."""

    session_id: str
    state: str = Field(description="queued | running | error")
    message: str | None = Field(default=None, description="Error detail when state is error.")


class DistillStatusResponse(BaseModel):
    """Response for GET /api/v1/agents/{name}/transcripts/distill-status.

    Only in-flight sessions appear (queued / running / error); a session absent
    from the list is either done or never-distilled (see the list endpoint's
    ``distill_status``)."""

    statuses: list[DistillSessionStatus]
