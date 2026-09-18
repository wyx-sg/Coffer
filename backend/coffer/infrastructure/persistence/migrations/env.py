# backend/coffer/infrastructure/persistence/migrations/env.py
"""Alembic environment: wires Base.metadata to the async engine factory."""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import sys

from alembic import context
from sqlalchemy.engine import Connection

from coffer.infrastructure.channel import (
    persistence as _channel_persistence,  # noqa: F401 — channel_peers model
)
from coffer.infrastructure.mcp import (
    persistence as _mcp_persistence,  # noqa: F401 — kind-specific models
)
from coffer.infrastructure.persistence import models  # noqa: F401 — kind-agnostic models
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas

cfg = context.config

# Alembic's generated env.py calls ``logging.config.fileConfig`` here. Coffer's
# deliberately does not, and ``alembic.ini`` carries no logging sections for it
# to read.
#
# fileConfig *replaces* the root logger's handlers. When the daemon runs
# migrations at startup (``surfaces.http.migrations_runner``), that tore out the
# rotating ``daemon.log`` handler and the JSON formatter
# ``infrastructure.logging.setup`` had installed seconds earlier and put
# alembic's own ``%(levelname)-5.5s [%(name)s] %(message)s`` console handler in
# their place — so the daemon's log format silently depended on whether a
# migration had run yet this boot, and every line written afterwards lost its
# timestamp. Logging belongs to whoever owns the process; for the daemon that is
# ``configure_logging``, and a library called from inside it does not get to
# decide.
#
# Alembic's own records need no configuration to be seen: they are ordinary
# stdlib records on the ``alembic.*`` loggers, so they propagate to the root
# logger the daemon already configured and land in ``daemon.log`` as JSON with
# ``logger: alembic.runtime.migration`` — which is what "Context impl
# SQLiteImpl." and "Will assume non-transactional DDL." are.
#
# The one caller that owns no logging configuration is the bare ``alembic``
# CLI. It gets a plain stderr handler, so a developer running a migration by
# hand still watches "Running upgrade …" go by.
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

target_metadata = Base.metadata


#: The value ``alembic.ini`` ships for ``sqlalchemy.url``. It is a marker, not
#: a URL: the real one is supplied at run time by whichever of the two paths
#: below is in use.
_INI_PLACEHOLDER = "driver://overridden-in-env"


def _db_url() -> str:
    """Resolve the database URL — the same way in offline and online mode.

    Precedence:

    1. ``sqlalchemy.url`` on the Alembic ``Config``, when a caller set it to a
       real value (``surfaces.http.migrations_runner.run_migrations`` passes
       the daemon's own URL this way). A caller that names a database must
       get exactly that database; reading the environment instead would let
       a test, or a daemon started with an explicit URL, silently migrate
       whatever ``COFFER_DB_URL`` / ``~/.coffer/coffer.db`` points at — the
       developer's real vault.
    2. ``COFFER_DB_URL`` from the environment — the plain ``alembic`` CLI
       path (``cd backend && alembic -c .../alembic.ini upgrade head``), where
       the ini carries only the placeholder and nobody set the option.
    3. ``~/.coffer/coffer.db``, the daemon's default location.
    """
    configured = cfg.get_main_option("sqlalchemy.url")
    if configured and configured != _INI_PLACEHOLDER:
        return configured
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
