"""Synchronous Alembic migration runner + forward-compatibility guard.

Run at daemon lifespan startup (off the request path). Extracted from
``app.py`` to keep the app factory focused on wiring rather than DB plumbing.

Before a migration actually changes the schema, the on-disk database is copied
aside as ``coffer.db.pre-<revision>`` (with its ``-wal``/``-shm`` companions when
present). A migration that fails half-way, or one whose data rewrite turns out
wrong, is then a file rename away from recovery instead of a lost vault. Only
the newest few copies are kept, and nothing is copied when the schema is
already current — the normal case on every restart but the first after an
upgrade.

The URL a caller passes is the URL that gets migrated: it is pinned on the
Alembic config rather than read back out of the environment by ``env.py``, so
``run_migrations(url)`` can never touch a database other than ``url``.
"""

from __future__ import annotations

import pathlib
import shutil

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.engine import make_url

from coffer.domain.errors import DatabaseSchemaTooNew

#: How many ``coffer.db.pre-*`` copies survive; older ones are removed once a
#: newer copy lands, so an install that upgrades often does not hoard vaults.
KEEP_PRE_MIGRATION_COPIES = 3

_SIDE_FILES = ("-wal", "-shm")


def _alembic_config(db_url: str | None = None) -> AlembicConfig:
    """Alembic config for this build's migration tree.

    With ``db_url``, the URL is pinned on the config so ``env.py`` migrates
    exactly that database and never consults ``COFFER_DB_URL`` or
    ``~/.coffer/coffer.db`` (see ``env.py::_db_url`` for the precedence).
    ``set_main_option`` goes through ``ConfigParser`` interpolation, where a
    bare ``%`` is an interpolation marker, so it is doubled here; alembic's
    ``get_main_option`` folds it back to a single ``%`` on the way out.
    """
    cfg = AlembicConfig(
        str(
            pathlib.Path(__file__).resolve().parent.parent.parent
            / "infrastructure/persistence/migrations/alembic.ini"
        )
    )
    if db_url is not None:
        cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    return cfg


def _guard_schema_not_newer(cfg: AlembicConfig, db_url: str) -> str | None:
    """Fail fast when the on-disk DB was migrated by a newer/divergent build.

    If the DB's current Alembic revision is not in this build's migration tree
    (e.g. the DB was created by a feature branch whose migrations this release
    doesn't ship), ``upgrade head`` raises an opaque "Can't locate revision
    identified by ..." and the daemon dies during lifespan startup with no
    actionable message. Detect that here and raise a clear error. A fresh DB
    (no ``alembic_version`` row) reports ``None`` and is fine.

    Returns the current revision (``None`` for a fresh DB) so the caller can
    decide whether an upgrade is about to happen at all.
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
    return current


def sqlite_file(db_url: str) -> pathlib.Path | None:
    """The on-disk file behind a SQLite URL, or ``None`` for anything else —
    another dialect, an in-memory database, or a file that does not exist yet
    (a first start has nothing worth copying)."""
    try:
        url = make_url(db_url)
    except Exception:
        return None
    if not url.drivername.startswith("sqlite"):
        return None
    database = url.database
    if not database or database == ":memory:" or "mode=memory" in database:
        return None
    path = pathlib.Path(database)
    return path if path.is_file() else None


def _copies_of(db_path: pathlib.Path) -> list[pathlib.Path]:
    """Existing ``<db>.pre-*`` copies (main files only), newest first."""
    copies = [
        p
        for p in db_path.parent.glob(f"{db_path.name}.pre-*")
        if p.is_file() and not p.name.endswith(_SIDE_FILES)
    ]
    return sorted(copies, key=lambda p: p.stat().st_mtime, reverse=True)


def _prune_copies(db_path: pathlib.Path, keep: int) -> list[pathlib.Path]:
    removed: list[pathlib.Path] = []
    for stale in _copies_of(db_path)[keep:]:
        for side in ("", *_SIDE_FILES):
            victim = stale.with_name(stale.name + side)
            if victim.is_file():
                victim.unlink()
                removed.append(victim)
    return removed


def backup_before_migrate(
    db_path: pathlib.Path,
    current_revision: str | None,
    *,
    keep: int = KEEP_PRE_MIGRATION_COPIES,
) -> pathlib.Path:
    """Copy ``db_path`` (and any ``-wal``/``-shm`` companions) to
    ``<db>.pre-<revision>`` and prune older copies down to ``keep``.

    An existing copy for the same revision is never overwritten — it is the
    state from BEFORE an earlier attempt, which is the more trustworthy one if
    that attempt left the file half-migrated — so a later attempt lands beside
    it with a numeric suffix.
    """
    tag = current_revision or "base"
    dest = db_path.with_name(f"{db_path.name}.pre-{tag}")
    n = 1
    while dest.exists():
        dest = db_path.with_name(f"{db_path.name}.pre-{tag}.{n}")
        n += 1
    shutil.copy2(db_path, dest)
    for side in _SIDE_FILES:
        companion = db_path.with_name(db_path.name + side)
        if companion.is_file():
            shutil.copy2(companion, dest.with_name(dest.name + side))
    _prune_copies(db_path, keep)
    return dest


def run_migrations(db_url: str) -> pathlib.Path | None:
    """Guard against a too-new schema, back the file up if an upgrade is due,
    then ``alembic upgrade head``. Returns the backup path, or ``None`` when
    the schema was already current or the database is not a file."""
    from alembic.script import ScriptDirectory

    cfg = _alembic_config(db_url)
    current = _guard_schema_not_newer(cfg, db_url)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    backup: pathlib.Path | None = None
    db_path = sqlite_file(db_url)
    if db_path is not None and current != head:
        backup = backup_before_migrate(db_path, current)
    command.upgrade(cfg, "head")
    return backup
