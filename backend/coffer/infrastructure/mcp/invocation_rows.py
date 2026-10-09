"""The MCP invocation log's table and the row ↔ domain mapping (no I/O).

Split from ``invocation_writer`` (the buffered writer and the readers) for the
400-line guideline; ``persistence`` re-exports the public names.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Index, Integer, Select, String, Text, or_
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.mcp.capability import MCPInvocation
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.textsearch import contains_any


class MCPInvocationModel(Base):
    __tablename__ = "mcp_invocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    #: WHICH server, by identity. The log is history, so it has
    #: to survive the rename that a name-keyed column would have split it across.
    #: Not a foreign key: a deleted server's invocations stay readable, and two
    #: reserved non-uid values live here — see ``domain.mcp.capability``.
    resource_uid: Mapped[str] = mapped_column(String, nullable=False)
    capability_type: Mapped[str] = mapped_column(String, nullable=False)
    capability_key: Mapped[str] = mapped_column(String, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    #: The calling agent's uid, as its session reported it.
    #: Not a foreign key, for the same reason ``resource_uid`` is not one: a
    #: deleted agent's calls stay in the history.
    agent_uid: Mapped[str | None] = mapped_column(String, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    #: A custom-tool call's environment (migration 0151); null otherwise.
    environment: Mapped[str | None] = mapped_column(String, nullable=True)
    #: The call's redacted, bounded content as JSON (migration 0152); null when
    #: recording was off. Deferred by every list read.
    content_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_invocations_trace", "trace_id"),
        Index("idx_invocations_resource", "resource_uid", "timestamp"),
        Index("idx_invocations_time", "timestamp"),
        Index("idx_invocations_session", "session_id", "timestamp"),
        Index("idx_invocations_agent", "agent_uid", "timestamp"),
    )


def tz(dt: datetime) -> datetime:
    """Re-attach UTC if SQLite stripped the tzinfo on read-back."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


#: A status filter that is every outcome but ``ok`` — an error, a timeout or a denial.
FAILED = "failed"


def filtered(
    stmt: Select[Any],
    *,
    resource_uid: str | None,
    status: str | None,
    since: datetime | None,
    agent_uid: str | None,
    trace_id: str | None = None,
    q: str | None = None,
    q_resource_uids: Sequence[str] = (),
) -> Select[Any]:
    """The one WHERE both the page and its count read, so they cannot disagree."""
    if trace_id is not None:
        stmt = stmt.where(MCPInvocationModel.trace_id == trace_id)
    if resource_uid is not None:
        stmt = stmt.where(MCPInvocationModel.resource_uid == resource_uid)
    if status == FAILED:
        stmt = stmt.where(MCPInvocationModel.status != "ok")
    elif status is not None:
        stmt = stmt.where(MCPInvocationModel.status == status)
    if since is not None:
        stmt = stmt.where(MCPInvocationModel.timestamp >= since)
    if agent_uid is not None:
        stmt = stmt.where(MCPInvocationModel.agent_uid == agent_uid)
    if q:
        # Free text: the tool, the failure, the session and the outcome — plus
        # the servers whose current name matched (``q_resource_uids``: the log
        # stores the uid, the label is resolved at read time).
        match = contains_any(
            (
                MCPInvocationModel.capability_key,
                MCPInvocationModel.error_message,
                MCPInvocationModel.session_id,
                MCPInvocationModel.status,
            ),
            q,
        )
        stmt = stmt.where(
            or_(match, MCPInvocationModel.resource_uid.in_(q_resource_uids))
            if q_resource_uids
            else match
        )
    return stmt


def inv_to_domain(row: MCPInvocationModel, *, with_content: bool = False) -> MCPInvocation:
    """The domain row; ``with_content`` reads the (deferred) content column."""
    content = json.loads(row.content_json) if with_content and row.content_json else None
    return MCPInvocation(
        id=row.id,
        timestamp=tz(row.timestamp),
        resource_uid=row.resource_uid,
        capability_type=row.capability_type,  # type: ignore[arg-type]
        capability_key=row.capability_key,
        duration_ms=row.duration_ms,
        status=row.status,  # type: ignore[arg-type]
        error_message=row.error_message,
        session_id=row.session_id,
        agent_uid=row.agent_uid,
        trace_id=row.trace_id,
        environment=row.environment,
        content=content,
    )


def inv_to_model(inv: MCPInvocation) -> MCPInvocationModel:
    return MCPInvocationModel(
        timestamp=inv.timestamp,
        resource_uid=inv.resource_uid,
        capability_type=inv.capability_type,
        capability_key=inv.capability_key,
        duration_ms=inv.duration_ms,
        status=inv.status,
        error_message=inv.error_message,
        session_id=inv.session_id,
        agent_uid=inv.agent_uid,
        environment=inv.environment,
        trace_id=inv.trace_id,
        content_json=json.dumps(inv.content, ensure_ascii=False) if inv.content else None,
    )
