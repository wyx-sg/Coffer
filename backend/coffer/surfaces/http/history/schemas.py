"""Pydantic wire schemas for the transcript-history routes (ADR-022)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HistorySessionSummary(BaseModel):
    agent_type: str
    session_id: str
    project_path: str | None = None
    started_at: datetime | None = None
    title: str
    message_count: int


class HistorySessionListResponse(BaseModel):
    sessions: list[HistorySessionSummary]


class HistorySearchHitOut(BaseModel):
    agent_type: str
    session_id: str
    project_path: str | None = None
    started_at: datetime | None = None
    title: str
    snippet: str
    score: float


class HistorySearchResponse(BaseModel):
    query: str
    hits: list[HistorySearchHitOut]


class HistoryTurnOut(BaseModel):
    role: str
    text: str


class HistorySessionDetailResponse(BaseModel):
    session: HistorySessionSummary
    turns: list[HistoryTurnOut]


class RebuildResponse(BaseModel):
    indexed: int
    unchanged: int
    removed: int


class ResetResponse(BaseModel):
    removed: int
