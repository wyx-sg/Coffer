# backend/coffer/infrastructure/persistence/migrations/env.py
"""Alembic environment: wires Base.metadata to the async engine factory."""

from __future__ import annotations

import asyncio
import os
import pathlib
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from coffer.infrastructure.agent import (
    projection_persistence as _agent_projection,  # noqa: F401 — projection-binding model
)
from coffer.infrastructure.knowledge import (  # noqa: F401 — unified documents/chunks ORM + FTS5 DDL
    ddl as _knowledge_ddl,
)
from coffer.infrastructure.mcp import (
    persistence as _mcp_persistence,  # noqa: F401 — kind-specific models
)
from coffer.infrastructure.memory import (
    project_root_repo as _memory_project_roots,  # noqa: F401 — store→project-root model
)
from coffer.infrastructure.persistence import models  # noqa: F401 — kind-agnostic models
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas

cfg = context.config
if cfg.config_file_name is not None:
    # disable_existing_loggers=False: fileConfig's default (True) silently
    # disables every already-imported application logger when the daemon runs
    # migrations at startup, swallowing e.g. the chat turn-error WARNING.
    fileConfig(cfg.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _db_url() -> str:
    return os.environ.get(
        "COFFER_DB_URL",
        f"sqlite+aiosqlite:///{pathlib.Path.home()}/.coffer/coffer.db",
    )


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine_with_pragmas(_db_url())
    async with engine.connect() as conn:
        await conn.run_sync(_run_migrations)
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(url=_db_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async())
