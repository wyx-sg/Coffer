"""One server's calls since a moment, counted in SQL.

Spec mcp-gateway "Record invocations with redacted, bounded content".

The MCP server page's "Last 24 hours": how many calls and errors, per calling
agent, and per tool. An error is any call that did not end ``ok``. The totals
count every call; the per-tool rows count tool calls only, keyed by the
upstream's own tool name (what the capability list calls ``original_name``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker


@dataclass(frozen=True)
class CallCount:
    key: str | None
    calls: int
    errors: int
    last_call_at: datetime | None


@dataclass(frozen=True)
class InvocationSummary:
    since: datetime
    calls: int
    errors: int
    last_call_at: datetime | None
    by_agent: list[CallCount]
    by_tool: list[CallCount]


def _tz(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def summarize(
    sm: async_sessionmaker,  # type: ignore[type-arg]
    model: Any,
    *,
    resource_uid: str,
    since: datetime,
) -> InvocationSummary:
    """Count ``resource_uid``'s calls at or after ``since``; ``model`` is the invocation table."""
    errors = func.sum(case((model.status != "ok", 1), else_=0))
    window = [model.resource_uid == resource_uid, model.timestamp >= since]
    async with sm() as session:
        total = (
            await session.execute(
                select(func.count(), errors, func.max(model.timestamp)).where(*window)
            )
        ).one()
        agents = (
            await session.execute(
                select(model.agent_uid, func.count(), errors, func.max(model.timestamp))
                .where(*window)
                .group_by(model.agent_uid)
                .order_by(func.count().desc())
            )
        ).all()
        tools = (
            await session.execute(
                select(model.capability_key, func.count(), errors, func.max(model.timestamp))
                .where(*window, model.capability_type == "tool")
                .group_by(model.capability_key)
                .order_by(func.count().desc())
            )
        ).all()

    def _rows(rows: Any) -> list[CallCount]:
        return [
            CallCount(key=r[0], calls=int(r[1]), errors=int(r[2] or 0), last_call_at=_tz(r[3]))
            for r in rows
        ]

    return InvocationSummary(
        since=since,
        calls=int(total[0]),
        errors=int(total[1] or 0),
        last_call_at=_tz(total[2]),
        by_agent=_rows(agents),
        by_tool=_rows(tools),
    )


__all__ = ["CallCount", "InvocationSummary", "summarize"]
