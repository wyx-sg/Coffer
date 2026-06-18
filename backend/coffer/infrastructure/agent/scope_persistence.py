"""Persistence for per-agent MCP server scoping (spec 001/004, ADR-026).

Two tables, both FK→``resources.id`` with ``ON DELETE CASCADE`` so deleting an
agent or a server resource removes its scope rows:

* ``agent_mcp_scope`` — one row per agent carrying its mode (auto | selected).
* ``agent_mcp_scope_server`` — the allowlist used when mode = 'selected'.

The ORM models register against the shared ``Base.metadata`` (Alembic discovers
them via the ``migrations/env.py`` import). The repo deals only in resource ids;
the application service (``application/agent/scope_service.py``) translates
agent/server names ↔ ids so the rest of the system works in names.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class AgentMcpScopeModel(Base):
    __tablename__ = "agent_mcp_scope"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("agent_resource_id", name="uq_agent_mcp_scope_agent"),
        CheckConstraint("mode IN ('auto', 'selected')", name="ck_agent_mcp_scope_mode"),
    )


class AgentMcpScopeServerModel(Base):
    __tablename__ = "agent_mcp_scope_server"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="CASCADE"), nullable=False
    )
    server_resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "agent_resource_id", "server_resource_id", name="uq_agent_mcp_scope_server"
        ),
        Index("idx_agent_scope_server_agent", "agent_resource_id"),
    )


class AgentMcpScopeRepo:
    """CRUD over the two per-agent scope tables, keyed by resource id."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def get_mode(self, agent_resource_id: int) -> str | None:
        """The agent's scope mode, or ``None`` when no row exists (treated as auto)."""
        async with self._sm() as session:
            row = (
                await session.execute(
                    select(AgentMcpScopeModel).where(
                        AgentMcpScopeModel.agent_resource_id == agent_resource_id
                    )
                )
            ).scalar_one_or_none()
            return row.mode if row is not None else None

    async def get_allowed_server_ids(self, agent_resource_id: int) -> set[int]:
        async with self._sm() as session:
            rows = (
                (
                    await session.execute(
                        select(AgentMcpScopeServerModel.server_resource_id).where(
                            AgentMcpScopeServerModel.agent_resource_id == agent_resource_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            return set(rows)

    async def set(self, agent_resource_id: int, mode: str, server_ids: list[int]) -> None:
        """Upsert the mode row and replace the allowlist atomically."""
        async with self._sm() as session:
            now = datetime.now(tz=UTC)
            row = (
                await session.execute(
                    select(AgentMcpScopeModel).where(
                        AgentMcpScopeModel.agent_resource_id == agent_resource_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                session.add(
                    AgentMcpScopeModel(
                        agent_resource_id=agent_resource_id,
                        mode=mode,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.mode = mode
                row.updated_at = now
            await session.execute(
                sa_delete(AgentMcpScopeServerModel).where(
                    AgentMcpScopeServerModel.agent_resource_id == agent_resource_id
                )
            )
            for sid in dict.fromkeys(server_ids):  # dedupe, preserve order
                session.add(
                    AgentMcpScopeServerModel(
                        agent_resource_id=agent_resource_id, server_resource_id=sid
                    )
                )
            await session.commit()
