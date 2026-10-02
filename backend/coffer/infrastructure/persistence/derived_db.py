"""``derived/derived.db`` — tables rebuilt from other state (ADR
storage-is-five-classes-by-nature).

Three tables are observations this machine can make again: an MCP server's
last health check, which skill copies were delivered into which agent, and
when each upstream capability was first and last seen. None of them is the
only copy of a fact, so they live under ``derived/`` in a database of their
own: no Alembic lineage, the schema created with ``create_all`` at open, and
``PRAGMA user_version`` compared with :data:`SCHEMA_VERSION` — a file at any
other version is deleted and created again rather than migrated, which is
what "derived" allows.
"""

from __future__ import annotations

import contextlib
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import TIMESTAMP, Boolean, Index, PrimaryKeyConstraint, String, Text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.vault.home import derived_root

#: Bumped whenever a table below changes shape; an older file is recreated.
SCHEMA_VERSION = 1


class DerivedBase(DeclarativeBase):
    """The metadata of ``derived.db`` only — never Alembic's."""


class MCPServerHealthModel(DerivedBase):
    """The last "test connection" result per mcp_server, keyed by its uid."""

    __tablename__ = "mcp_server_health"

    resource_uid: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class SkillAgentBindingModel(DerivedBase):
    """Whether a skill's copy is delivered into an agent, and where."""

    __tablename__ = "skill_agent_bindings"

    skill_uid: Mapped[str] = mapped_column(String, nullable=False)
    agent_uid: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_linked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_link_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_mode: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("skill_uid", "agent_uid", name="pk_skill_agent_bindings"),
        Index("idx_bindings_agent", "agent_uid", "enabled"),
    )


class MCPCapabilitySeenModel(DerivedBase):
    """When this machine first and last saw one upstream capability. The
    person's switch for it is a vault document (``state/mcp-preferences/``)."""

    __tablename__ = "mcp_capability_seen"

    server_uid: Mapped[str] = mapped_column(String, nullable=False)
    capability_type: Mapped[str] = mapped_column(String, nullable=False)
    capability_key: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint(
            "server_uid", "capability_type", "capability_key", name="pk_mcp_capability_seen"
        ),
    )


def derived_db_path(home: Path | None = None) -> Path:
    return derived_root(home) / "derived.db"


def _reset_if_stale(path: Path) -> None:
    """Delete ``path`` (and its WAL companions) unless it is at this schema."""
    if not path.exists():
        return
    version: int | None
    try:
        with contextlib.closing(sqlite3.connect(path)) as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.DatabaseError:
        version = None
    if version == SCHEMA_VERSION:
        return
    for suffix in ("", "-wal", "-shm"):
        with contextlib.suppress(FileNotFoundError):
            path.with_name(path.name + suffix).unlink()


def prepare_derived_db(path: Path) -> None:
    """Make ``path`` a ``derived.db`` at :data:`SCHEMA_VERSION` (synchronous:
    the check runs before any async engine holds the file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _reset_if_stale(path)
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()


async def open_derived_db(path: Path | None = None) -> tuple[AsyncEngine, async_sessionmaker]:  # type: ignore[type-arg]
    """An engine and session maker on ``derived.db``, its schema created."""
    target = path or derived_db_path()
    prepare_derived_db(target)
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{target}")
    async with engine.begin() as conn:
        await conn.run_sync(DerivedBase.metadata.create_all)
    return engine, session_maker(engine)


__all__ = [
    "SCHEMA_VERSION",
    "DerivedBase",
    "MCPCapabilitySeenModel",
    "MCPServerHealthModel",
    "SkillAgentBindingModel",
    "derived_db_path",
    "open_derived_db",
    "prepare_derived_db",
]
