"""Synchronous Alembic migration runner + forward-compatibility guard.

Run at daemon lifespan startup (off the request path). Extracted from
``app.py`` to keep the app factory focused on wiring rather than DB plumbing.
"""

from __future__ import annotations

import pathlib

from alembic import command
from alembic.config import Config as AlembicConfig

from coffer.domain.errors import DatabaseSchemaTooNew


def _alembic_config() -> AlembicConfig:
    return AlembicConfig(
        str(
            pathlib.Path(__file__).resolve().parent.parent.parent
            / "infrastructure/persistence/migrations/alembic.ini"
        )
    )


def _guard_schema_not_newer(cfg: AlembicConfig, db_url: str) -> None:
    """Fail fast when the on-disk DB was migrated by a newer/divergent build.

    If the DB's current Alembic revision is not in this build's migration tree
    (e.g. the DB was created by a feature branch whose migrations this release
    doesn't ship), ``upgrade head`` raises an opaque "Can't locate revision
    identified by ..." and the daemon dies during lifespan startup with no
    actionable message. Detect that here and raise a clear error. A fresh DB
    (no ``alembic_version`` row) reports ``None`` and is fine.
    """
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine

    known = {rev.revision for rev in ScriptDirectory.from_config(cfg).walk_revisions()}
    sync_url = db_url.replace("sqlite+aiosqlite://", "sqlite://")
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
    if current is not None and current not in known:
        raise DatabaseSchemaTooNew(current=current, db_path=db_url)


def run_migrations(db_url: str) -> None:
    """Guard against a too-new schema, then ``alembic upgrade head``."""
    cfg = _alembic_config()
    _guard_schema_not_newer(cfg, db_url)
    command.upgrade(cfg, "head")
